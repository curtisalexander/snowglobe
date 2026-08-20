import asyncio
from collections.abc import Iterable, Sequence
from datetime import timedelta
from threading import Event

import pyarrow as pa
import pytest

from snowglobe.broker import InProcessBroker, RequestStatus
from snowglobe.executor import BackgroundQueryExecutor
from snowglobe.snowflake_executor import SnowflakeQueryAdmission
from snowglobe.sql_policy import QueryPolicyRejected, SnowflakeSqlPolicy

ALLOWED_VIEW = "GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"


class FakeResultBatch:
    def __init__(self, table: pa.Table, *, rowcount: int = 0) -> None:
        self.rowcount = rowcount
        self._table = table

    def to_arrow(self) -> pa.Table:
        return self._table


class FakeCursor:
    def __init__(
        self,
        events: list[str],
        *,
        tables: Iterable[pa.Table] = (),
        result_batches: Sequence[FakeResultBatch] | None = None,
        execute_started: Event | None = None,
        execute_release: Event | None = None,
        execute_error: Exception | None = None,
    ) -> None:
        self._events = events
        self._tables = tables
        self._result_batches = result_batches
        self._execute_started = execute_started
        self._execute_release = execute_release
        self._execute_error = execute_error
        self.cancel_count = 0
        self.executed_sql = ""
        self.execute_timeout: int | None = None

    def execute(self, command: str, *, timeout: int | None = None) -> object:
        self._events.append("cursor.execute")
        self.executed_sql = command
        self.execute_timeout = timeout
        if self._execute_started is not None:
            self._execute_started.set()
        if self._execute_release is not None:
            self._execute_release.wait(timeout=2)
        if self._execute_error is not None:
            raise self._execute_error
        return self

    def fetch_arrow_batches(self) -> Iterable[pa.Table]:
        self._events.append("cursor.fetch_arrow_batches")
        return iter(self._tables)

    def get_result_batches(self) -> Sequence[FakeResultBatch] | None:
        self._events.append("cursor.get_result_batches")
        return self._result_batches

    def cancel(self) -> None:
        self._events.append("cursor.cancel")
        self.cancel_count += 1
        if self._execute_release is not None:
            self._execute_release.set()

    def close(self) -> None:
        self._events.append("cursor.close")


class FakeConnection:
    def __init__(
        self,
        events: list[str],
        cursor: FakeCursor,
        *,
        close_error: Exception | None = None,
    ) -> None:
        self._events = events
        self._cursor = cursor
        self._close_error = close_error

    def cursor(self) -> FakeCursor:
        self._events.append("connection.cursor")
        return self._cursor

    def close(self) -> None:
        self._events.append("connection.close")
        if self._close_error is not None:
            raise self._close_error


def _executor(
    broker: InProcessBroker,
    cursor: FakeCursor,
    events: list[str],
    *,
    connection_close_error: Exception | None = None,
) -> BackgroundQueryExecutor:
    def connect(**arguments: object) -> FakeConnection:
        assert arguments == {"configured": True}
        events.append("connect")
        return FakeConnection(events, cursor, close_error=connection_close_error)

    admission = SnowflakeQueryAdmission(
        policy=SnowflakeSqlPolicy.from_view_names((ALLOWED_VIEW,)),
        connector_arguments={"configured": True},
        connect=connect,
    )
    return BackgroundQueryExecutor(broker=broker, admit=admission)


def test_acceptance_waits_for_cursor_registration_then_retrieves_incrementally() -> None:
    async def exercise() -> None:
        events: list[str] = []
        execute_started = Event()
        execute_release = Event()
        first = pa.table({"VALUE": [1, 2]})
        second = pa.table({"VALUE": [3]})
        cursor = FakeCursor(
            events,
            tables=(first, second),
            execute_started=execute_started,
            execute_release=execute_release,
        )
        broker = InProcessBroker(maximum_pending_requests=1)
        executor = _executor(broker, cursor, events)

        request = await executor.submit(
            sql=f"select VALUE from {ALLOWED_VIEW}",
            requested_ttl=timedelta(minutes=5),
        )

        assert broker.get_request(request.request_id).status is RequestStatus.PENDING
        assert await asyncio.to_thread(execute_started.wait, 1)
        assert cursor.executed_sql.endswith("LIMIT 51")
        assert cursor.execute_timeout == 60

        execute_release.set()
        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)

        source = broker.open_source(request.request_id)
        batches = [batch async for batch in source.open()]
        assert batches == [*first.to_batches(), *second.to_batches()]
        assert events == [
            "connect",
            "connection.cursor",
            "cursor.execute",
            "cursor.fetch_arrow_batches",
            "cursor.close",
            "connection.close",
        ]

    asyncio.run(exercise())


def test_empty_result_preserves_the_connector_arrow_schema() -> None:
    async def exercise() -> None:
        events: list[str] = []
        empty = pa.table({"EMPTY_COLUMN": pa.array([], type=pa.timestamp("ns"))})
        cursor = FakeCursor(events, result_batches=(FakeResultBatch(empty),))
        broker = InProcessBroker()
        executor = _executor(broker, cursor, events)

        request = await executor.submit(
            sql=f"select * from {ALLOWED_VIEW}",
            requested_ttl=timedelta(minutes=5),
        )
        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)

        source = broker.open_source(request.request_id)
        assert source.schema == empty.schema
        assert [batch async for batch in source.open()] == []
        assert "cursor.get_result_batches" in events

    asyncio.run(exercise())


def test_oversized_result_fails_before_publication_and_closes_resources() -> None:
    async def exercise() -> None:
        events: list[str] = []
        cursor = FakeCursor(events, tables=(pa.table({"VALUE": range(51)}),))
        broker = InProcessBroker()
        executor = _executor(broker, cursor, events)

        request = await executor.submit(
            sql=f"select VALUE from {ALLOWED_VIEW}",
            requested_ttl=timedelta(minutes=5),
        )
        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)

        assert broker.get_request(request.request_id).status is RequestStatus.FAILED
        assert cursor.cancel_count == 0
        assert events[-2:] == ["cursor.close", "connection.close"]

    asyncio.run(exercise())


def test_cleanup_failure_does_not_publish_an_otherwise_admitted_result() -> None:
    async def exercise() -> None:
        events: list[str] = []
        cursor = FakeCursor(events, tables=(pa.table({"VALUE": [1]}),))
        broker = InProcessBroker()
        executor = _executor(
            broker,
            cursor,
            events,
            connection_close_error=RuntimeError("CLEANUP_ERROR_CANARY"),
        )

        request = await executor.submit(
            sql=f"select VALUE from {ALLOWED_VIEW}",
            requested_ttl=timedelta(minutes=5),
        )
        while broker.get_request(request.request_id).status is RequestStatus.PENDING:
            await asyncio.sleep(0)

        assert broker.get_request(request.request_id).status is RequestStatus.FAILED
        assert events[-2:] == ["cursor.close", "connection.close"]

    asyncio.run(exercise())


def test_cancellation_targets_active_cursor_and_remains_cancelled() -> None:
    async def exercise() -> None:
        events: list[str] = []
        release = Event()
        cursor = FakeCursor(
            events,
            execute_release=release,
            execute_error=RuntimeError("DRIVER_CANARY"),
        )
        broker = InProcessBroker()
        executor = _executor(broker, cursor, events)

        request = await executor.submit(
            sql=f"select VALUE from {ALLOWED_VIEW}",
            requested_ttl=timedelta(minutes=5),
        )
        assert broker.cancel(request.request_id).status is RequestStatus.CANCELLED
        await executor.close()

        assert broker.get_request(request.request_id).status is RequestStatus.CANCELLED
        assert cursor.cancel_count == 1
        assert events[-2:] == ["cursor.close", "connection.close"]

    asyncio.run(exercise())


def test_policy_rejection_never_opens_a_connection() -> None:
    events: list[str] = []
    broker = InProcessBroker()
    executor = _executor(broker, FakeCursor(events), events)

    async def exercise() -> None:
        with pytest.raises(QueryPolicyRejected, match=r"^$"):
            await executor.submit(
                sql="delete from unsafe",
                requested_ttl=timedelta(minutes=5),
            )

    asyncio.run(exercise())
    assert events == []
    assert broker.list_requests() == ()
