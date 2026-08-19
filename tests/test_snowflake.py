import pytest

from snowglobe.snowflake import request_cursor


class FakeCursor:
    def __init__(self, events: list[str], *, close_error: Exception | None = None) -> None:
        self._events = events
        self._close_error = close_error

    def close(self) -> None:
        self._events.append("cursor.close")
        if self._close_error is not None:
            raise self._close_error


class FakeConnection:
    def __init__(
        self,
        events: list[str],
        *,
        cursor_error: Exception | None = None,
        cursor_close_error: Exception | None = None,
    ) -> None:
        self._events = events
        self._cursor_error = cursor_error
        self._cursor_close_error = cursor_close_error

    def cursor(self) -> FakeCursor:
        self._events.append("connection.cursor")
        if self._cursor_error is not None:
            raise self._cursor_error
        return FakeCursor(self._events, close_error=self._cursor_close_error)

    def close(self) -> None:
        self._events.append("connection.close")


def test_owns_one_connection_and_cursor_for_request() -> None:
    events: list[str] = []
    arguments = {"account": "configured-account", "private_key": b"private-key"}

    def connect(**received: object) -> FakeConnection:
        assert received == arguments
        events.append("connect")
        return FakeConnection(events)

    with request_cursor(arguments, connect=connect) as cursor:
        assert isinstance(cursor, FakeCursor)
        events.append("request")

    assert events == ["connect", "connection.cursor", "request", "cursor.close", "connection.close"]


def test_closes_connection_when_cursor_creation_fails() -> None:
    events: list[str] = []

    def connect(**_arguments: object) -> FakeConnection:
        events.append("connect")
        return FakeConnection(events, cursor_error=RuntimeError("cursor canary"))

    with pytest.raises(RuntimeError, match="cursor canary"), request_cursor({}, connect=connect):
        raise AssertionError("request body must not run")

    assert events == ["connect", "connection.cursor", "connection.close"]


def test_closes_cursor_and_connection_when_request_fails() -> None:
    events: list[str] = []

    def connect(**_arguments: object) -> FakeConnection:
        events.append("connect")
        return FakeConnection(events)

    with pytest.raises(RuntimeError, match="request canary"), request_cursor({}, connect=connect):
        events.append("request")
        raise RuntimeError("request canary")

    assert events == ["connect", "connection.cursor", "request", "cursor.close", "connection.close"]


def test_closes_connection_when_cursor_close_fails() -> None:
    events: list[str] = []

    def connect(**_arguments: object) -> FakeConnection:
        events.append("connect")
        return FakeConnection(events, cursor_close_error=RuntimeError("close canary"))

    with pytest.raises(RuntimeError, match="close canary"), request_cursor({}, connect=connect):
        events.append("request")

    assert events == ["connect", "connection.cursor", "request", "cursor.close", "connection.close"]
