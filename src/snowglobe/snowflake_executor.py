"""Configured asynchronous Snowflake execution behind the value-free MCP seam."""

import asyncio
from collections.abc import Iterable, Iterator, Sequence
from itertools import chain
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

import pyarrow as pa

from snowglobe.arrow_stream import (
    ArrowAdmissionError,
    InMemoryArrowBatchSource,
    admit_record_batches,
)
from snowglobe.broker import InProcessBroker, RequestUnavailable
from snowglobe.configuration import (
    build_connector_arguments,
    load_snowflake_profile,
    load_snowglobe_profile,
)
from snowglobe.executor import BackgroundQueryExecutor, ExecutionStarted
from snowglobe.mvp_limits import MVP_ARROW_LIMITS, MVP_STATEMENT_TIMEOUT_SECONDS
from snowglobe.snowflake import SnowflakeConnect, SnowflakeCursor, request_cursor
from snowglobe.sql_policy import SnowflakeSqlPolicy


class _SnowflakeResultBatch(Protocol):
    @property
    def rowcount(self) -> int: ...

    def to_arrow(self) -> pa.Table: ...


class _ExecutingSnowflakeCursor(SnowflakeCursor, Protocol):
    def execute(self, command: str, *, timeout: int | None = None) -> object: ...

    def fetch_arrow_batches(self) -> Iterable[pa.Table]: ...

    def get_result_batches(self) -> Sequence[_SnowflakeResultBatch] | None: ...


class SnowflakeQueryAdmission:
    """Authorize configured SQL and produce one bounded, replayable Arrow source."""

    def __init__(
        self,
        *,
        policy: SnowflakeSqlPolicy,
        connector_arguments: dict[str, object],
        connect: SnowflakeConnect | None = None,
    ) -> None:
        self._policy = policy
        self._connector_arguments = connector_arguments
        self._connect = connect
        self._active = Lock()

    def __call__(self, sql: str):
        governed_sql = self._policy.authorize(sql)

        async def work(
            _request_id: str,
            mark_started: ExecutionStarted,
        ) -> InMemoryArrowBatchSource:
            return await asyncio.to_thread(self._execute, governed_sql, mark_started)

        return work

    def _execute(
        self,
        governed_sql: str,
        mark_started: ExecutionStarted,
    ) -> InMemoryArrowBatchSource:
        if not self._active.acquire(blocking=False):
            raise RequestUnavailable
        try:
            with request_cursor(self._connector_arguments, connect=self._connect) as cursor:
                release_cursor = mark_started(cursor)
                try:
                    executing_cursor = cast(_ExecutingSnowflakeCursor, cursor)
                    executing_cursor.execute(governed_sql, timeout=MVP_STATEMENT_TIMEOUT_SECONDS)
                    return _fetch_admitted_result(executing_cursor)
                finally:
                    release_cursor()
        finally:
            self._active.release()


def create_snowflake_executor(
    *,
    broker: InProcessBroker,
    connections_path: Path,
    snowglobe_config_path: Path,
    profile_name: str,
    connect: SnowflakeConnect | None = None,
) -> BackgroundQueryExecutor:
    """Load one fixed profile and construct the configured background executor."""

    connection = load_snowflake_profile(connections_path, profile_name)
    snowglobe_profile = load_snowglobe_profile(snowglobe_config_path, profile_name)
    admission = SnowflakeQueryAdmission(
        policy=SnowflakeSqlPolicy.from_view_names(snowglobe_profile.allowed_views),
        connector_arguments=build_connector_arguments(connection),
        connect=connect,
    )
    return BackgroundQueryExecutor(broker=broker, admit=admission)


def _fetch_admitted_result(cursor: _ExecutingSnowflakeCursor) -> InMemoryArrowBatchSource:
    tables = iter(cursor.fetch_arrow_batches())
    first = next(tables, None)
    if first is None:
        first = _empty_result_table(cursor)
    if not isinstance(first, pa.Table):
        raise ArrowAdmissionError

    schema = first.schema
    return admit_record_batches(
        schema,
        _record_batches(schema, chain((first,), tables)),
        MVP_ARROW_LIMITS,
    )


def _record_batches(schema: pa.Schema, tables: Iterable[pa.Table]) -> Iterator[pa.RecordBatch]:
    for table in tables:
        if not isinstance(table, pa.Table) or not table.schema.equals(schema, check_metadata=True):
            raise ArrowAdmissionError
        yield from table.to_batches()


def _empty_result_table(cursor: _ExecutingSnowflakeCursor) -> pa.Table:
    """Recover the connector-owned schema when batch iteration yields no rows."""

    result_batches = cursor.get_result_batches()
    if not result_batches or any(batch.rowcount != 0 for batch in result_batches):
        raise ArrowAdmissionError
    table = result_batches[0].to_arrow()
    if not isinstance(table, pa.Table) or table.num_rows != 0:
        raise ArrowAdmissionError
    return table
