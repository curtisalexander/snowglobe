"""Single-analyst in-process request broker for the synthetic proof."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from snowglobe.arrow_stream import ArrowBatchSource


class RequestStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RequestUnavailable(Exception):
    """A deliberately detail-free unavailable-request failure."""


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
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if maximum_ttl <= timedelta(0):
            raise ValueError("maximum_ttl must be positive")
        self._maximum_ttl = maximum_ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[str, _RequestRecord] = {}

    def submit(
        self,
        *,
        requested_ttl: timedelta,
        source: ArrowBatchSource | None = None,
    ) -> RequestView:
        """Register pending work, or a completed synthetic source for tests."""

        if requested_ttl <= timedelta(0):
            raise ValueError("requested_ttl must be positive")

        request_id = self._new_request_id()
        record = _RequestRecord(
            request_id=request_id,
            status=RequestStatus.COMPLETE if source is not None else RequestStatus.PENDING,
            expires_at=self._now() + min(requested_ttl, self._maximum_ttl),
            source=source,
        )
        self._records[request_id] = record
        return record.view()

    def publish(self, request_id: str, source: ArrowBatchSource) -> RequestView:
        """Atomically attach a result source and mark pending work complete."""

        record = self._record(request_id)
        if record.status is not RequestStatus.PENDING:
            raise RequestUnavailable
        record.source = source
        record.status = RequestStatus.COMPLETE
        return record.view()

    def fail(self, request_id: str) -> RequestView:
        record = self._record(request_id)
        if record.status is not RequestStatus.PENDING:
            raise RequestUnavailable
        record.status = RequestStatus.FAILED
        return record.view()

    def list_requests(self) -> tuple[RequestView, ...]:
        return tuple(
            self._refresh_expiry(record).view() for record in reversed(self._records.values())
        )

    def get_request(self, request_id: str) -> RequestView:
        return self._record(request_id).view()

    def open_source(self, request_id: str) -> ArrowBatchSource:
        record = self._record(request_id)
        if record.status is not RequestStatus.COMPLETE or record.source is None:
            raise RequestUnavailable
        return record.source

    def cancel(self, request_id: str) -> RequestView:
        record = self._record(request_id)
        if record.status in {RequestStatus.EXPIRED, RequestStatus.CANCELLED}:
            raise RequestUnavailable
        record.status = RequestStatus.CANCELLED
        record.source = None
        return record.view()

    def _record(self, request_id: str) -> _RequestRecord:
        record = self._records.get(request_id)
        if record is None:
            raise RequestUnavailable
        return self._refresh_expiry(record)

    def _refresh_expiry(self, record: _RequestRecord) -> _RequestRecord:
        if (
            record.status
            in {
                RequestStatus.PENDING,
                RequestStatus.COMPLETE,
            }
            and self._now() >= record.expires_at
        ):
            record.status = RequestStatus.EXPIRED
            record.source = None
        return record

    def _new_request_id(self) -> str:
        while (request_id := secrets.token_urlsafe(18)) in self._records:
            pass
        return request_id

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now
