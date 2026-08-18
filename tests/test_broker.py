from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pyarrow as pa
import pytest

from snowglobe.broker import (
    AGENT_AUDIENCE,
    VIEWER_AUDIENCE,
    AgentClaims,
    InProcessBroker,
    RequestAccessDenied,
    RequestStatus,
    ViewerClaims,
)


@dataclass
class Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


class Source:
    schema = pa.schema([])

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        if False:
            yield pa.record_batch([], schema=self.schema)


def agent(owner: str = "human-a", audience: str = AGENT_AUDIENCE) -> AgentClaims:
    return AgentClaims(subject="agent-session", human_subject=owner, audience=audience)


def viewer(subject: str = "human-a", audience: str = VIEWER_AUDIENCE) -> ViewerClaims:
    return ViewerClaims(subject=subject, audience=audience)


def test_submission_is_associated_with_owner_status_expiry_and_source() -> None:
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    broker = InProcessBroker(maximum_ttl=timedelta(minutes=15), clock=clock)
    source = Source()

    request = broker.submit(agent(), requested_ttl=timedelta(hours=1), source=source)

    assert request.status is RequestStatus.COMPLETE
    assert request.expires_at == clock.now + timedelta(minutes=15)
    assert 20 <= len(request.request_id) <= 32
    assert broker.list_requests(viewer()) == (request,)
    assert broker.open_source(viewer(), request.request_id) is source


def test_request_id_is_not_authorization() -> None:
    broker = InProcessBroker()
    request = broker.submit(agent(), requested_ttl=timedelta(minutes=5), source=Source())

    assert broker.list_requests(viewer("human-b")) == ()
    with pytest.raises(RequestAccessDenied, match=r"^$"):
        broker.get_request(viewer("human-b"), request.request_id)
    with pytest.raises(RequestAccessDenied, match=r"^$"):
        broker.open_source(viewer("human-b"), request.request_id)
    with pytest.raises(RequestAccessDenied, match=r"^$"):
        broker.cancel(viewer("human-b"), request.request_id)


def test_control_and_data_plane_audiences_are_not_interchangeable() -> None:
    broker = InProcessBroker()

    with pytest.raises(RequestAccessDenied, match=r"^$"):
        broker.submit(
            agent(audience=VIEWER_AUDIENCE),
            requested_ttl=timedelta(minutes=5),
            source=Source(),
        )
    with pytest.raises(RequestAccessDenied, match=r"^$"):
        broker.list_requests(viewer(audience=AGENT_AUDIENCE))


def test_cancelled_and_expired_requests_cannot_be_opened() -> None:
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    broker = InProcessBroker(clock=clock)
    cancelled = broker.submit(agent(), requested_ttl=timedelta(minutes=5), source=Source())
    expired = broker.submit(agent(), requested_ttl=timedelta(minutes=1), source=Source())

    assert broker.cancel(viewer(), cancelled.request_id).status is RequestStatus.CANCELLED
    clock.now += timedelta(minutes=2)
    assert broker.get_request(viewer(), expired.request_id).status is RequestStatus.EXPIRED

    for request_id in (cancelled.request_id, expired.request_id):
        with pytest.raises(RequestAccessDenied, match=r"^$"):
            broker.open_source(viewer(), request_id)


def test_unknown_request_failure_does_not_reflect_identifier() -> None:
    broker = InProcessBroker()
    canary = "REQUEST_ID_CANARY"

    with pytest.raises(RequestAccessDenied, match=r"^$") as failure:
        broker.get_request(viewer(), canary)

    assert canary not in str(failure.value)
