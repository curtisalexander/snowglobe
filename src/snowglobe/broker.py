"""Test-only in-process request broker for the synthetic boundary proof."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from snowglobe.arrow_stream import ArrowBatchSource

AGENT_AUDIENCE = "snowglobe-mcp"
VIEWER_AUDIENCE = "snowglobe-viewer"


class RequestStatus(StrEnum):
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RequestAccessDenied(Exception):
    """A deliberately detail-free authorization failure."""


@dataclass(frozen=True, slots=True)
class AgentClaims:
    """Claims produced by the control plane's authentication adapter."""

    subject: str
    human_subject: str
    audience: str


@dataclass(frozen=True, slots=True)
class ViewerClaims:
    """Claims produced by the data plane's authentication adapter."""

    subject: str
    audience: str


@dataclass(frozen=True, slots=True)
class RequestView:
    """Value-free request metadata safe for the authenticated human viewer."""

    request_id: str
    status: RequestStatus
    expires_at: datetime


@dataclass(slots=True)
class _RequestRecord:
    request_id: str
    owner_subject: str
    status: RequestStatus
    expires_at: datetime
    source: ArrowBatchSource

    def view(self) -> RequestView:
        return RequestView(
            request_id=self.request_id,
            status=self.status,
            expires_at=self.expires_at,
        )


class InProcessBroker:
    """Single-process broker used only to prove ownership and expiry semantics."""

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
        claims: AgentClaims,
        *,
        requested_ttl: timedelta,
        source: ArrowBatchSource,
    ) -> RequestView:
        """Atomically associate a synthetic source before returning its receipt data."""

        self._authorize_agent(claims)
        if requested_ttl <= timedelta(0):
            raise ValueError("requested_ttl must be positive")

        request_id = self._new_request_id()
        record = _RequestRecord(
            request_id=request_id,
            owner_subject=claims.human_subject,
            status=RequestStatus.COMPLETE,
            expires_at=self._now() + min(requested_ttl, self._maximum_ttl),
            source=source,
        )
        self._records[request_id] = record
        return record.view()

    def list_requests(self, claims: ViewerClaims) -> tuple[RequestView, ...]:
        self._authorize_viewer(claims)
        return tuple(
            self._refresh_expiry(record).view()
            for record in self._records.values()
            if record.owner_subject == claims.subject
        )

    def get_request(self, claims: ViewerClaims, request_id: str) -> RequestView:
        return self._owned_record(claims, request_id).view()

    def open_source(self, claims: ViewerClaims, request_id: str) -> ArrowBatchSource:
        record = self._owned_record(claims, request_id)
        if record.status is not RequestStatus.COMPLETE:
            raise RequestAccessDenied
        return record.source

    def cancel(self, claims: ViewerClaims, request_id: str) -> RequestView:
        record = self._owned_record(claims, request_id)
        if record.status is RequestStatus.EXPIRED:
            raise RequestAccessDenied
        record.status = RequestStatus.CANCELLED
        return record.view()

    def _owned_record(self, claims: ViewerClaims, request_id: str) -> _RequestRecord:
        self._authorize_viewer(claims)
        record = self._records.get(request_id)
        if record is None or record.owner_subject != claims.subject:
            raise RequestAccessDenied
        return self._refresh_expiry(record)

    @staticmethod
    def _authorize_agent(claims: AgentClaims) -> None:
        if claims.audience != AGENT_AUDIENCE or not claims.subject or not claims.human_subject:
            raise RequestAccessDenied

    @staticmethod
    def _authorize_viewer(claims: ViewerClaims) -> None:
        if claims.audience != VIEWER_AUDIENCE or not claims.subject:
            raise RequestAccessDenied

    def _refresh_expiry(self, record: _RequestRecord) -> _RequestRecord:
        if record.status is RequestStatus.COMPLETE and self._now() >= record.expires_at:
            record.status = RequestStatus.EXPIRED
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
