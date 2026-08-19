from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pyarrow as pa
import pytest

from snowglobe.broker import (
    InProcessBroker,
    RequestStatus,
    RequestUnavailable,
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


class Cursor:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.cancel_count = 0
        self._error = error

    def cancel(self) -> None:
        self.cancel_count += 1
        if self._error is not None:
            raise self._error


def test_pending_submission_can_be_published_atomically() -> None:
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    broker = InProcessBroker(maximum_ttl=timedelta(minutes=15), clock=clock)

    request = broker.submit(requested_ttl=timedelta(hours=1))

    assert request.status is RequestStatus.PENDING
    assert request.expires_at == clock.now + timedelta(minutes=15)
    assert 20 <= len(request.request_id) <= 32
    assert broker.list_requests() == (request,)
    with pytest.raises(RequestUnavailable, match=r"^$"):
        broker.open_source(request.request_id)

    source = Source()
    published = broker.publish(request.request_id, source)

    assert published.status is RequestStatus.COMPLETE
    assert broker.open_source(request.request_id) is source


def test_completed_synthetic_source_can_be_registered_in_one_step() -> None:
    broker = InProcessBroker()
    source = Source()

    request = broker.submit(requested_ttl=timedelta(minutes=5), source=source)

    assert request.status is RequestStatus.COMPLETE
    assert broker.open_source(request.request_id) is source


def test_requests_are_listed_most_recent_first() -> None:
    broker = InProcessBroker()
    first = broker.submit(requested_ttl=timedelta(minutes=5))
    second = broker.submit(requested_ttl=timedelta(minutes=5))

    assert broker.list_requests() == (second, first)


def test_failed_cancelled_and_expired_requests_have_no_result_source() -> None:
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    broker = InProcessBroker(clock=clock)
    failed = broker.submit(requested_ttl=timedelta(minutes=5))
    cancelled = broker.submit(requested_ttl=timedelta(minutes=5), source=Source())
    expired = broker.submit(requested_ttl=timedelta(minutes=1), source=Source())

    assert broker.fail(failed.request_id).status is RequestStatus.FAILED
    assert broker.cancel(cancelled.request_id).status is RequestStatus.CANCELLED
    clock.now += timedelta(minutes=2)
    assert broker.get_request(expired.request_id).status is RequestStatus.EXPIRED

    for request_id in (failed.request_id, cancelled.request_id, expired.request_id):
        with pytest.raises(RequestUnavailable, match=r"^$"):
            broker.open_source(request_id)


def test_cancellation_targets_only_the_registered_request_cursor_and_is_idempotent() -> None:
    broker = InProcessBroker()
    first = broker.submit(requested_ttl=timedelta(minutes=5))
    second = broker.submit(requested_ttl=timedelta(minutes=5))
    first_cursor = Cursor()
    second_cursor = Cursor()
    broker.register_cursor(first.request_id, first_cursor)
    broker.register_cursor(second.request_id, second_cursor)

    assert broker.cancel(first.request_id).status is RequestStatus.CANCELLED
    assert broker.cancel(first.request_id).status is RequestStatus.CANCELLED

    assert first_cursor.cancel_count == 1
    assert second_cursor.cancel_count == 0
    assert broker.get_request(second.request_id).status is RequestStatus.PENDING


def test_cursor_created_after_cancellation_is_immediately_cancelled() -> None:
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    cursor = Cursor()
    broker.cancel(request.request_id)

    with pytest.raises(RequestUnavailable, match=r"^$"):
        broker.register_cursor(request.request_id, cursor)

    assert cursor.cancel_count == 1


def test_cursor_cancellation_failure_is_private_and_remains_idempotent() -> None:
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    cursor = Cursor(error=RuntimeError("DRIVER_ERROR_CANARY"))
    broker.register_cursor(request.request_id, cursor)

    assert broker.cancel(request.request_id).status is RequestStatus.CANCELLED
    assert broker.cancel(request.request_id).status is RequestStatus.CANCELLED
    assert cursor.cancel_count == 1


def test_unknown_request_failure_does_not_reflect_identifier() -> None:
    broker = InProcessBroker()
    canary = "REQUEST_ID_CANARY"

    with pytest.raises(RequestUnavailable, match=r"^$") as failure:
        broker.get_request(canary)

    assert canary not in str(failure.value)
