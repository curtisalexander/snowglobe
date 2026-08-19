"""Request-scoped Snowflake connection and cursor ownership."""

import importlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Protocol, cast


class SnowflakeCursor(Protocol):
    def cancel(self) -> None: ...

    def close(self) -> None: ...


class SnowflakeConnection(Protocol):
    def cursor(self) -> SnowflakeCursor: ...

    def close(self) -> None: ...


SnowflakeConnect = Callable[..., SnowflakeConnection]


@contextmanager
def request_cursor(
    connector_arguments: Mapping[str, object],
    *,
    connect: SnowflakeConnect | None = None,
) -> Iterator[SnowflakeCursor]:
    """Own exactly one connection and cursor for the duration of one request."""

    connection = (connect or _connect)(**connector_arguments)
    try:
        cursor = connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
    finally:
        connection.close()


def _connect(**connector_arguments: object) -> SnowflakeConnection:
    connector = importlib.import_module("snowflake.connector")
    return cast(SnowflakeConnection, connector.connect(**connector_arguments))
