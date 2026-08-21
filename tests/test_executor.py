import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pyarrow as pa
import pytest

from snowglobe.broker import InProcessBroker, RequestStatus, RequestUnavailable
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

        def admit(sql: str):
            assert sql == "select 1"

            async def work(request_id: str, mark_started) -> Source:
                assert broker.get_request(request_id).status is RequestStatus.PENDING
                mark_started(None)
                started.set()
                await release.wait()
                return source

            return sql, work

        executor = BackgroundQueryExecutor(broker=broker, admit=admit)
        submission = await executor.submit(
            sql="select 1",
            requested_ttl=timedelta(minutes=5),
        )
        request = submission.request

        assert submission.governed_sql == "select 1"
        assert request.status is RequestStatus.PENDING
        await started.wait()
        assert broker.get_request(request.request_id).status is RequestStatus.PENDING

        release.set()
        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)
        assert broker.open_source(request.request_id) is source

    asyncio.run(exercise())


def test_policy_rejection_creates_no_request() -> None:
    async def exercise() -> None:
        broker = InProcessBroker()

        def reject(_sql: str):
            raise QueryPolicyRejected

        executor = BackgroundQueryExecutor(broker=broker, admit=reject)

        with pytest.raises(QueryPolicyRejected, match=r"^$"):
            await executor.submit(
                sql="select 1",
                requested_ttl=timedelta(minutes=5),
            )

        assert broker.list_requests() == ()

    asyncio.run(exercise())


def test_background_failure_becomes_failed_state() -> None:
    canary = "BACKGROUND_ERROR_CANARY"

    async def exercise() -> None:
        broker = InProcessBroker()

        def admit(_sql: str):
            async def work(_request_id: str, mark_started) -> Source:
                mark_started(None)
                raise RuntimeError(canary)

            return "SELECT 1", work

        executor = BackgroundQueryExecutor(broker=broker, admit=admit)
        submission = await executor.submit(
            sql="select 1",
            requested_ttl=timedelta(minutes=5),
        )
        request = submission.request

        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)
        assert broker.get_request(request.request_id).status is RequestStatus.FAILED

    asyncio.run(exercise())


def test_close_rejects_later_submissions() -> None:
    async def exercise() -> None:
        broker = InProcessBroker()

        def admit(_sql: str):
            async def work(_request_id: str, mark_started) -> Source:
                mark_started(None)
                return Source()

            return "SELECT 1", work

        executor = BackgroundQueryExecutor(broker=broker, admit=admit)
        await executor.close()

        with pytest.raises(RequestUnavailable, match=r"^$"):
            await executor.submit(
                sql="select 1",
                requested_ttl=timedelta(minutes=5),
            )
        assert broker.list_requests() == ()

    asyncio.run(exercise())
