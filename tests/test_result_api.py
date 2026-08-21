import asyncio
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import timedelta

import pyarrow as pa
import pytest
from httpx2 import Response
from starlette.applications import Starlette
from starlette.testclient import TestClient

from snowglobe.arrow_stream import ArrowAdmissionLimits, ArrowBatchSource
from snowglobe.broker import InProcessBroker, RequestView
from snowglobe.result_api import (
    ARROW_FRAME,
    COMPLETE_FRAME,
    FRAME_HEADER,
    RESPONSE_HEADERS,
    STREAM_CONTENT_TYPE,
    STREAM_MAGIC,
    _framed_stream,
    create_app,
)

TEST_LIMITS = ArrowAdmissionLimits(
    maximum_rows=100,
    maximum_columns=10,
    maximum_cell_bytes=1024,
    maximum_arrow_bytes=1024 * 1024,
    maximum_decoded_bytes=1024 * 1024,
)


@dataclass
class Source:
    batches: tuple[pa.RecordBatch, ...]
    failure: Exception | None = None
    source_schema: pa.Schema | None = None

    @property
    def schema(self) -> pa.Schema:
        if self.source_schema is not None:
            return self.source_schema
        if self.batches:
            return self.batches[0].schema
        return pa.schema([])

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        for item in self.batches:
            yield item
        if self.failure is not None:
            raise self.failure


def submitted(
    broker: InProcessBroker,
    source: ArrowBatchSource | None = None,
) -> RequestView:
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    return broker.publish(
        request.request_id,
        source if source is not None else Source((batch(["arrow"]),)),
    )


def assert_response_headers(response: Response) -> None:
    for name, value in RESPONSE_HEADERS.items():
        assert response.headers[name] == value


def result_app(
    broker: InProcessBroker,
    admission_limits: ArrowAdmissionLimits = TEST_LIMITS,
) -> Starlette:
    return create_app(broker=broker, admission_limits=admission_limits)


def parse_frames(body: bytes) -> list[tuple[int, bytes]]:
    assert body.startswith(STREAM_MAGIC)
    frames = []
    offset = len(STREAM_MAGIC)
    while offset < len(body):
        frame_type, length = FRAME_HEADER.unpack_from(body, offset)
        offset += FRAME_HEADER.size
        payload = body[offset : offset + length]
        assert len(payload) == length
        frames.append((frame_type, payload))
        offset += length
    return frames


def batch(values: list[str]) -> pa.RecordBatch:
    return pa.record_batch([pa.array(values)], names=["value"])


def test_health_is_value_free_and_not_cached() -> None:
    response = TestClient(result_app(InProcessBroker())).get("/healthz")

    assert response.json() == {"status": "ok"}
    assert_response_headers(response)


def test_default_local_api_lists_no_requests() -> None:
    response = TestClient(result_app(InProcessBroker())).get("/v1/requests")

    assert response.status_code == 200
    assert response.json() == {"requests": []}
    assert_response_headers(response)


def test_list_and_open_local_requests() -> None:
    broker = InProcessBroker()
    item = submitted(broker)
    client = TestClient(result_app(broker))

    listed = client.get("/v1/requests")
    opened = client.get(f"/v1/requests/{item.request_id}")

    assert listed.status_code == 200
    assert listed.json() == {"requests": [opened.json()]}
    assert opened.json() == {
        "request_id": item.request_id,
        "status": "complete",
        "expires_at": item.expires_at.isoformat(),
    }
    for response in (listed, opened):
        assert_response_headers(response)
    assert client.post(f"/v1/requests/{item.request_id}/cancel").status_code == 404


def test_unknown_request_is_not_reflected() -> None:
    broker = InProcessBroker()
    canary = "UNKNOWN_REQUEST_CANARY"
    client = TestClient(result_app(broker))

    responses = [
        client.get(f"/v1/requests/{canary}"),
        client.get(f"/v1/requests/{canary}/stream"),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.json() == {"error": "not_found"}
        assert canary.encode() not in response.content


def test_pending_request_is_visible_but_has_no_stream() -> None:
    broker = InProcessBroker()
    item = broker.submit(requested_ttl=timedelta(minutes=5))
    client = TestClient(result_app(broker))

    opened = client.get(f"/v1/requests/{item.request_id}")
    streamed = client.get(f"/v1/requests/{item.request_id}/stream")

    assert opened.json()["status"] == "pending"
    assert streamed.status_code == 404


def test_stream_frames_arrow_and_emits_terminal_completion() -> None:
    broker = InProcessBroker()
    source = Source((batch(["first"]), batch(["second"])))
    item = submitted(broker, source)
    client = TestClient(result_app(broker))

    response = client.get(f"/v1/requests/{item.request_id}/stream")

    assert response.status_code == 200
    assert response.headers["content-type"] == STREAM_CONTENT_TYPE
    frames = parse_frames(response.content)
    assert frames[-1] == (COMPLETE_FRAME, b"")
    ipc = b"".join(payload for kind, payload in frames if kind == ARROW_FRAME)
    reader = pa.ipc.open_stream(ipc)
    assert reader.read_next_batch().column(0)[0].as_py() == "first"
    assert reader.read_next_batch().column(0)[0].as_py() == "second"
    assert_response_headers(response)


@pytest.mark.parametrize(
    ("source", "maximum_arrow_bytes", "expected_arrow"),
    [
        (Source((batch(["first"]),), RuntimeError("RESULT_CANARY")), 10_000, True),
        (Source((batch(["too-large"]),)), 1, False),
    ],
)
def test_incomplete_or_overflowing_stream_omits_completion_without_leaking_errors(
    source: Source,
    maximum_arrow_bytes: int,
    expected_arrow: bool,
) -> None:
    broker = InProcessBroker()
    item = submitted(broker, source)
    client = TestClient(
        result_app(
            broker,
            replace(TEST_LIMITS, maximum_arrow_bytes=maximum_arrow_bytes),
        )
    )

    response = client.get(f"/v1/requests/{item.request_id}/stream")
    frames = parse_frames(response.content)

    assert any(kind == ARROW_FRAME for kind, _payload in frames) is expected_arrow
    assert all(kind != COMPLETE_FRAME for kind, _payload in frames)
    assert b"RESULT_CANARY" not in response.content


def test_cancellation_during_stream_omits_later_bytes_and_completion() -> None:
    broker = InProcessBroker()

    class CancellingSource:
        request_id = ""
        schema = batch([""]).schema

        async def open(self) -> AsyncIterator[pa.RecordBatch]:
            yield batch(["first"])
            broker.cancel(self.request_id)
            yield batch(["must-not-be-released"])

    source = CancellingSource()
    item = broker.submit(requested_ttl=timedelta(minutes=5))
    broker.publish(item.request_id, source)
    source.request_id = item.request_id
    client = TestClient(result_app(broker))

    response = client.get(f"/v1/requests/{item.request_id}/stream")

    frames = parse_frames(response.content)
    assert len(frames) == 1
    assert frames[0][0] == ARROW_FRAME
    assert b"must-not-be-released" not in response.content


def test_stream_yields_each_arrow_header_and_payload_atomically() -> None:
    async def exercise() -> None:
        broker = InProcessBroker()
        source = Source((batch(["arrow"]),))
        item = submitted(broker, source)
        stream = _framed_stream(
            broker=broker,
            request_id=item.request_id,
            source=source,
            admission_limits=TEST_LIMITS,
        )

        assert await anext(stream) == STREAM_MAGIC
        framed_chunk = await anext(stream)
        frame_type, payload_length = FRAME_HEADER.unpack_from(framed_chunk)
        assert frame_type == ARROW_FRAME
        assert len(framed_chunk) == FRAME_HEADER.size + payload_length

        broker.cancel(item.request_id)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(exercise())


def test_frame_header_is_fixed_width_network_byte_order() -> None:
    assert FRAME_HEADER.size == 9
    assert FRAME_HEADER.pack(ARROW_FRAME, 256) == struct.pack(">BQ", ARROW_FRAME, 256)
