"""Single-analyst in-process request broker."""

import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import RLock
from typing import Protocol

from snowglobe.arrow_stream import ArrowBatchSource


class RequestStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RequestUnavailable(Exception):
    """A deliberately detail-free unavailable-request failure."""


class CancellableCursor(Protocol):
    """The private cancellation surface retained for one pending request."""

    def cancel(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RequestView:
    """Value-free lifecycle metadata for MCP status and the local viewer."""

    request_id: str
    status: RequestStatus
    expires_at: datetime


@dataclass(slots=True)
class _RequestRecord:
    request_id: str
    status: RequestStatus
    expires_at: datetime
    source: ArrowBatchSource | None = None
    cursor: CancellableCursor | None = None

    def view(self) -> RequestView:
        return RequestView(
            request_id=self.request_id,
            status=self.status,
            expires_at=self.expires_at,
        )


class InProcessBroker:
    """Local broker for one analyst and one Snowglobe runtime."""

    def __init__(
        self,
        *,
        maximum_ttl: timedelta = timedelta(minutes=15),
        maximum_pending_requests: int | None = None,
        maximum_requests: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if maximum_ttl <= timedelta(0):
            raise ValueError("maximum_ttl must be positive")
        if maximum_pending_requests is not None and maximum_pending_requests <= 0:
            raise ValueError("maximum_pending_requests must be positive")
        if maximum_requests is not None and maximum_requests <= 0:
            raise ValueError("maximum_requests must be positive")
        self._maximum_ttl = maximum_ttl
        self._maximum_pending_requests = maximum_pending_requests
        self._maximum_requests = maximum_requests
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[str, _RequestRecord] = {}
        self._lock = RLock()

    def submit(
        self,
        *,
        requested_ttl: timedelta,
    ) -> RequestView:
        """Register pending work."""

        if requested_ttl <= timedelta(0):
            raise ValueError("requested_ttl must be positive")

        with self._locked_records():
            if self._at_pending_capacity():
                raise RequestUnavailable
            self._make_room()
            request_id = self._new_request_id()
            record = _RequestRecord(
                request_id=request_id,
                status=RequestStatus.PENDING,
                expires_at=self._now() + min(requested_ttl, self._maximum_ttl),
            )
            self._records[request_id] = record
            return record.view()

    def register_cursor(self, request_id: str, cursor: CancellableCursor) -> RequestView:
        """Attach exactly one private cursor to pending work.

        If another terminal transition won the startup race, cancel the newly created
        cursor before reporting that the request is unavailable.
        """

        try:
            with self._locked_record(request_id) as record:
                if record.status is RequestStatus.PENDING and record.cursor is None:
                    record.cursor = cursor
                    return record.view()
        except RequestUnavailable:
            self._cancel_quietly(cursor)
            raise
        self._cancel_quietly(cursor)
        raise RequestUnavailable

    def release_cursor(self, request_id: str, cursor: CancellableCursor) -> None:
        """Remove a request's exact cursor after connector cleanup starts."""

        with self._locked_record(request_id) as record:
            if record.status is RequestStatus.PENDING and record.cursor is cursor:
                record.cursor = None

    def publish(self, request_id: str, source: ArrowBatchSource) -> RequestView:
        """Atomically attach a result source and mark pending work complete."""

        with self._locked_record(request_id) as record:
            if record.status is not RequestStatus.PENDING:
                raise RequestUnavailable
            record.source = source
            record.cursor = None
            record.status = RequestStatus.COMPLETE
            return record.view()

    def fail(self, request_id: str) -> RequestView:
        cursor: CancellableCursor | None
        with self._locked_record(request_id) as record:
            if record.status is not RequestStatus.PENDING:
                raise RequestUnavailable
            cursor = record.cursor
            record.cursor = None
            record.status = RequestStatus.FAILED
            view = record.view()

        if cursor is not None:
            self._cancel_quietly(cursor)
        return view

    def list_requests(self) -> tuple[RequestView, ...]:
        with self._locked_records():
            return tuple(record.view() for record in reversed(self._records.values()))

    def get_request(self, request_id: str) -> RequestView:
        with self._locked_record(request_id) as record:
            return record.view()

    def open_source(self, request_id: str) -> ArrowBatchSource:
        with self._locked_record(request_id) as record:
            if record.status is not RequestStatus.COMPLETE or record.source is None:
                raise RequestUnavailable
            return record.source

    def cancel(self, request_id: str) -> RequestView:
        cursor: CancellableCursor | None
        with self._locked_record(request_id) as record:
            if record.status is RequestStatus.CANCELLED:
                return record.view()
            if record.status is RequestStatus.EXPIRED:
                raise RequestUnavailable
            if record.status is RequestStatus.FAILED:
                return record.view()
            record.status = RequestStatus.CANCELLED
            record.source = None
            cursor = record.cursor
            record.cursor = None
            view = record.view()

        if cursor is not None:
            self._cancel_quietly(cursor)
        return view

    @contextmanager
    def _locked_record(self, request_id: str) -> Iterator[_RequestRecord]:
        expired_cursor: CancellableCursor | None = None
        try:
            with self._lock:
                record = self._records.get(request_id)
                if record is None:
                    raise RequestUnavailable
                expired_cursor = self._expire(record)
                yield record
        finally:
            if expired_cursor is not None:
                self._cancel_quietly(expired_cursor)

    @contextmanager
    def _locked_records(self) -> Iterator[None]:
        expired_cursors: list[CancellableCursor] = []
        try:
            with self._lock:
                expired_cursors = [
                    cursor
                    for record in self._records.values()
                    if (cursor := self._expire(record)) is not None
                ]
                yield
        finally:
            for cursor in expired_cursors:
                self._cancel_quietly(cursor)

    def _expire(self, record: _RequestRecord) -> CancellableCursor | None:
        if (
            record.status
            in {
                RequestStatus.PENDING,
                RequestStatus.COMPLETE,
            }
            and self._now() >= record.expires_at
        ):
            cursor = record.cursor
            record.status = RequestStatus.EXPIRED
            record.source = None
            record.cursor = None
            return cursor
        return None

    def _new_request_id(self) -> str:
        while (request_id := secrets.token_urlsafe(18)) in self._records:
            pass
        return request_id

    def _at_pending_capacity(self) -> bool:
        if self._maximum_pending_requests is None:
            return False
        pending = sum(record.status is RequestStatus.PENDING for record in self._records.values())
        return pending >= self._maximum_pending_requests

    def _make_room(self) -> None:
        if self._maximum_requests is None or len(self._records) < self._maximum_requests:
            return
        for request_id, record in self._records.items():
            if record.status in {
                RequestStatus.FAILED,
                RequestStatus.CANCELLED,
                RequestStatus.EXPIRED,
            }:
                del self._records[request_id]
                return
        raise RequestUnavailable

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now

    @staticmethod
    def _cancel_quietly(cursor: CancellableCursor) -> None:
        # Cancellation is best-effort and its private driver failure must not alter
        # the closed lifecycle state or escape through the local API.
        with suppress(Exception):
            cursor.cancel()
