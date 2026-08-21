import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Never

import pyarrow as pa
from mcp import Client
from mcp.types import TextContent
from starlette.testclient import TestClient

from snowglobe.arrow_stream import ArrowBatchSource
from snowglobe.broker import InProcessBroker, RequestStatus
from snowglobe.control import ControlPlane
from snowglobe.executor import BackgroundQueryExecutor
from snowglobe.mcp_gateway import create_server
from snowglobe.mvp_limits import MVP_ARROW_LIMITS
from snowglobe.result_api import ARROW_FRAME, FRAME_HEADER, STREAM_MAGIC, create_app


class CanarySource:
    schema = pa.schema(
        [
            pa.field("UNICODE_COLUMN_雪", pa.string()),
            pa.field("BINARY_COLUMN_CANARY", pa.binary()),
        ]
    )

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        yield pa.record_batch(
            [pa.array(["VIEWER_VALUE_雪"]), pa.array([b"BINARY_VALUE_CANARY\x00\xff"])],
            schema=self.schema,
        )
        yield pa.record_batch(
            [pa.array(["SECOND_BATCH_CANARY"]), pa.array([b"SECOND_BINARY_CANARY"])],
            schema=self.schema,
        )


def _arrow_payload(body: bytes) -> bytes:
    assert body.startswith(STREAM_MAGIC)
    chunks: list[bytes] = []
    offset = len(STREAM_MAGIC)
    while offset < len(body):
        frame_type, length = FRAME_HEADER.unpack_from(body, offset)
        offset += FRAME_HEADER.size
        payload = body[offset : offset + length]
        offset += length
        if frame_type == ARROW_FRAME:
            chunks.append(payload)
    return b"".join(chunks)


def test_result_canaries_stay_out_of_mcp_and_exist_in_the_viewer_data_path() -> None:
    broker = InProcessBroker(maximum_pending_requests=1)
    source = CanarySource()
    sql_canary = "SQL_INPUT_CANARY"
    failed_sql_canary = "FAILED_SQL_INPUT_CANARY"
    driver_error_canary = "INTERNAL_DRIVER_ERROR_CANARY"

    def admit(sql: str):
        async def work(
            _request_id: str,
            mark_started,
        ) -> ArrowBatchSource:
            mark_started(None)
            if failed_sql_canary in sql:
                raise RuntimeError(driver_error_canary)
            assert sql_canary in sql
            return source

        return sql, work

    mcp_server = create_server(
        ControlPlane(
            broker=broker,
            executor=BackgroundQueryExecutor(broker=broker, admit=admit),
        )
    )

    async def exercise_mcp() -> tuple[str, str]:
        async with Client(mcp_server) as client:
            accepted = await client.call_tool(
                "submit_read_query",
                {
                    "sql": f"select '{sql_canary}'",
                    "requested_ttl": 60,
                },
            )
            assert accepted.structured_content is not None
            request_id = accepted.structured_content["request_id"]
            assert accepted.structured_content["governed_sql"] == f"select '{sql_canary}'"
            while broker.get_request(request_id).status is RequestStatus.PENDING:
                await asyncio.sleep(0)
            complete = await client.call_tool("get_query_status", {"request_id": request_id})
            assert complete.structured_content == {
                "request_id": request_id,
                "status": "complete",
            }

            failed_submission = await client.call_tool(
                "submit_read_query",
                {
                    "sql": f"select '{failed_sql_canary}'",
                    "requested_ttl": 60,
                },
            )
            assert failed_submission.structured_content is not None
            failed_id = failed_submission.structured_content["request_id"]
            assert failed_submission.structured_content["governed_sql"] == (
                f"select '{failed_sql_canary}'"
            )
            while broker.get_request(failed_id).status is RequestStatus.PENDING:
                await asyncio.sleep(0)
            failed = await client.call_tool("get_query_status", {"request_id": failed_id})
            assert failed.structured_content == {
                "request_id": failed_id,
                "status": "failed",
            }

            model_visible = accepted.model_dump_json() + complete.model_dump_json()
            model_visible += failed_submission.model_dump_json() + failed.model_dump_json()
            return request_id, model_visible

    request_id, model_visible = asyncio.run(exercise_mcp())
    result_canaries = (
        "UNICODE_COLUMN_雪",
        "BINARY_COLUMN_CANARY",
        "VIEWER_VALUE_雪",
        "BINARY_VALUE_CANARY",
        "SECOND_BATCH_CANARY",
        "SECOND_BINARY_CANARY",
    )
    for canary in result_canaries:
        assert canary not in model_visible
    assert sql_canary in model_visible
    assert failed_sql_canary in model_visible
    assert driver_error_canary not in model_visible

    viewer = TestClient(create_app(broker=broker, admission_limits=MVP_ARROW_LIMITS))
    listed = viewer.get("/v1/requests")
    opened = viewer.get(f"/v1/requests/{request_id}")
    streamed = viewer.get(f"/v1/requests/{request_id}/stream")
    public_error = viewer.get("/v1/requests/abcdefghijklmnopqrstuvwx")

    assert public_error.json() == {"error": "not_found"}
    public_metadata = listed.content + opened.content + public_error.content
    private_canaries = (*result_canaries, sql_canary, failed_sql_canary, driver_error_canary)
    for canary in private_canaries:
        assert canary.encode() not in public_metadata
        assert canary not in str(listed.request.url)
        assert canary not in str(opened.request.url)
        assert canary not in str(streamed.request.url)

    reader = pa.ipc.open_stream(_arrow_payload(streamed.content))
    first = reader.read_next_batch()
    second = reader.read_next_batch()
    assert first.schema.names == ["UNICODE_COLUMN_雪", "BINARY_COLUMN_CANARY"]
    assert first.column(0)[0].as_py() == "VIEWER_VALUE_雪"
    assert first.column(1)[0].as_py() == b"BINARY_VALUE_CANARY\x00\xff"
    assert second.column(0)[0].as_py() == "SECOND_BATCH_CANARY"

    assert json.loads(public_error.content) == {"error": "not_found"}


def test_empty_result_preserves_schema_without_a_value_channel() -> None:
    schema = pa.schema([pa.field("EMPTY_COLUMN_CANARY", pa.string())])

    class EmptySource:
        @property
        def schema(self) -> pa.Schema:
            return schema

        async def open(self) -> AsyncIterator[pa.RecordBatch]:
            if False:
                yield pa.record_batch([], schema=schema)

    source = EmptySource()
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    broker.publish(request.request_id, source)
    response = TestClient(create_app(broker=broker, admission_limits=MVP_ARROW_LIMITS)).get(
        f"/v1/requests/{request.request_id}/stream"
    )

    reader = pa.ipc.open_stream(_arrow_payload(response.content))
    assert reader.schema.names == ["EMPTY_COLUMN_CANARY"]
    assert list(reader) == []


def test_every_mcp_lifecycle_response_remains_schema_closed() -> None:
    now = datetime(2026, 8, 19, tzinfo=UTC)

    async def status_for(status: RequestStatus) -> None:
        nonlocal now
        broker = InProcessBroker(clock=lambda: now)
        request = broker.submit(requested_ttl=timedelta(minutes=5))
        if status is RequestStatus.COMPLETE:
            broker.publish(request.request_id, CanarySource())
        else:
            if status is RequestStatus.FAILED:
                broker.fail(request.request_id)
            elif status is RequestStatus.CANCELLED:
                broker.cancel(request.request_id)
            elif status is RequestStatus.EXPIRED:
                now += timedelta(minutes=5)
                broker.get_request(request.request_id)
        mcp_server = create_server(ControlPlane(broker=broker, executor=None))

        async with Client(mcp_server) as client:
            result = await client.call_tool(
                "get_query_status",
                {"request_id": request.request_id},
            )

        assert result.structured_content == {
            "request_id": request.request_id,
            "status": status.value,
        }
        assert isinstance(result.content[0], TextContent)
        assert json.loads(result.content[0].text) == result.structured_content
        assert set(result.structured_content) == {"request_id", "status"}

    async def exercise() -> None:
        for status in RequestStatus:
            await status_for(status)

        class UnavailableBroker:
            def get_request(self, request_id: str) -> Never:
                raise RuntimeError("STATUS_ERROR_CANARY")

        control = ControlPlane(broker=UnavailableBroker(), executor=None)
        request_id = "abcdefghijklmnopqrstuvwx"
        async with Client(create_server(control)) as client:
            unavailable = await client.call_tool(
                "get_query_status",
                {"request_id": request_id},
            )
        assert unavailable.structured_content == {
            "request_id": request_id,
            "status": "service_unavailable",
        }
        assert "STATUS_ERROR_CANARY" not in unavailable.model_dump_json()

    asyncio.run(exercise())
