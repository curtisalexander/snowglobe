import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pyarrow as pa
import pytest

from snowglobe.broker import InProcessBroker, RequestStatus
from snowglobe.executor import BackgroundQueryExecutor
from snowglobe.sql_policy import QueryPolicyRejected


class Source:
    schema = pa.schema([])

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        if False:
            yield pa.record_batch([], schema=self.schema)


def test_admits_before_registering_pending_work_and_completes_in_background() -> None:
    async def exercise() -> None:
        broker = InProcessBroker()
        started = asyncio.Event()
        release = asyncio.Event()
        source = Source()

        def admit(sql: str, purpose: str):
            assert (sql, purpose) == ("select 1", "synthetic proof")

            async def work(request_id: str) -> Source:
                assert broker.get_request(request_id).status is RequestStatus.PENDING
                started.set()
                await release.wait()
                return source

            return work

        executor = BackgroundQueryExecutor(broker=broker, admit=admit)
        request = executor.submit(
            sql="select 1",
            purpose="synthetic proof",
            requested_ttl=timedelta(minutes=5),
        )

        assert request.status is RequestStatus.PENDING
        await started.wait()
        assert broker.get_request(request.request_id).status is RequestStatus.PENDING

        release.set()
        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)
        assert broker.open_source(request.request_id) is source

    asyncio.run(exercise())


def test_policy_rejection_creates_no_request() -> None:
    broker = InProcessBroker()

    def reject(_sql: str, _purpose: str):
        raise QueryPolicyRejected

    executor = BackgroundQueryExecutor(broker=broker, admit=reject)

    with pytest.raises(QueryPolicyRejected, match=r"^$"):
        executor.submit(
            sql="select 1",
            purpose="rejected",
            requested_ttl=timedelta(minutes=5),
        )

    assert broker.list_requests() == ()


def test_background_failure_becomes_detail_free_failed_state(
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "BACKGROUND_ERROR_CANARY"

    async def exercise() -> None:
        broker = InProcessBroker()

        def admit(_sql: str, _purpose: str):
            async def work(_request_id: str) -> Source:
                raise RuntimeError(canary)

            return work

        executor = BackgroundQueryExecutor(broker=broker, admit=admit)
        request = executor.submit(
            sql="select 1",
            purpose="failure proof",
            requested_ttl=timedelta(minutes=5),
        )

        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)
        assert broker.get_request(request.request_id).status is RequestStatus.FAILED

    asyncio.run(exercise())
    captured = capsys.readouterr()
    assert canary not in captured.out
    assert canary not in captured.err
