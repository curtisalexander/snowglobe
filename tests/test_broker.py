from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

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


def test_pending_request_capacity_is_atomic_and_reopens_after_terminal_state() -> None:
    broker = InProcessBroker(maximum_pending_requests=1)
    first = broker.submit(requested_ttl=timedelta(minutes=5))

    with pytest.raises(RequestUnavailable, match=r"^$"):
        broker.submit(requested_ttl=timedelta(minutes=5))

    broker.fail(first.request_id)
    second = broker.submit(requested_ttl=timedelta(minutes=5))

    assert second.status is RequestStatus.PENDING


def test_completed_synthetic_source_does_not_consume_pending_capacity() -> None:
    broker = InProcessBroker(maximum_pending_requests=1)
    pending = broker.submit(requested_ttl=timedelta(minutes=5))

    complete = broker.submit(requested_ttl=timedelta(minutes=5), source=Source())

    assert pending.status is RequestStatus.PENDING
    assert complete.status is RequestStatus.COMPLETE


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


def test_cursor_created_after_expiry_is_immediately_cancelled() -> None:
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    broker = InProcessBroker(clock=clock)
    request = broker.submit(requested_ttl=timedelta(minutes=1))
    cursor = Cursor()
    clock.now += timedelta(minutes=1)

    with pytest.raises(RequestUnavailable, match=r"^$"):
        broker.register_cursor(request.request_id, cursor)

    assert cursor.cancel_count == 1


def test_only_the_exact_registered_cursor_can_be_released() -> None:
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    cursor = Cursor()
    broker.register_cursor(request.request_id, cursor)

    broker.release_cursor(request.request_id, Cursor())
    broker.cancel(request.request_id)

    assert cursor.cancel_count == 1


def test_released_cursor_is_not_cancelled_after_execution_finishes() -> None:
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    cursor = Cursor()
    broker.register_cursor(request.request_id, cursor)

    broker.release_cursor(request.request_id, cursor)
    broker.fail(request.request_id)

    assert cursor.cancel_count == 0


def test_cursor_cancellation_failure_is_private_and_remains_idempotent() -> None:
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    cursor = Cursor(error=RuntimeError("DRIVER_ERROR_CANARY"))
    broker.register_cursor(request.request_id, cursor)

    assert broker.cancel(request.request_id).status is RequestStatus.CANCELLED
    assert broker.cancel(request.request_id).status is RequestStatus.CANCELLED
    assert cursor.cancel_count == 1


def test_cancelling_a_failed_request_preserves_its_terminal_state() -> None:
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    broker.fail(request.request_id)

    assert broker.cancel(request.request_id).status is RequestStatus.FAILED
    assert broker.get_request(request.request_id).status is RequestStatus.FAILED


def test_failure_cancels_and_removes_the_private_cursor() -> None:
    broker = InProcessBroker()
    request = broker.submit(requested_ttl=timedelta(minutes=5))
    cursor = Cursor()
    broker.register_cursor(request.request_id, cursor)

    assert broker.fail(request.request_id).status is RequestStatus.FAILED
    assert cursor.cancel_count == 1
    with pytest.raises(RequestUnavailable, match=r"^$"):
        broker.register_cursor(request.request_id, Cursor())


def test_expiry_cancels_and_removes_the_private_cursor() -> None:
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    broker = InProcessBroker(clock=clock)
    request = broker.submit(requested_ttl=timedelta(minutes=1))
    cursor = Cursor()
    broker.register_cursor(request.request_id, cursor)

    clock.now += timedelta(minutes=1)

    assert broker.get_request(request.request_id).status is RequestStatus.EXPIRED
    assert cursor.cancel_count == 1


def test_expiry_cancels_driver_cursor_after_releasing_the_broker_lock() -> None:
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    broker = InProcessBroker(clock=clock)
    expiring = broker.submit(requested_ttl=timedelta(minutes=1))
    other = broker.submit(requested_ttl=timedelta(minutes=5), source=Source())
    cancellation_started = Event()
    cancellation_release = Event()
    other_accessed = Event()

    class BlockingCursor:
        def cancel(self) -> None:
            cancellation_started.set()
            cancellation_release.wait(timeout=2)

    broker.register_cursor(expiring.request_id, BlockingCursor())
    clock.now += timedelta(minutes=1)

    expiry_thread = Thread(target=broker.get_request, args=(expiring.request_id,))
    expiry_thread.start()
    assert cancellation_started.wait(timeout=1)

    def access_other() -> None:
        broker.get_request(other.request_id)
        other_accessed.set()

    access_thread = Thread(target=access_other)
    access_thread.start()
    assert other_accessed.wait(timeout=1)

    cancellation_release.set()
    expiry_thread.join(timeout=1)
    access_thread.join(timeout=1)
    assert not expiry_thread.is_alive()
    assert not access_thread.is_alive()


def test_unknown_request_failure_does_not_reflect_identifier() -> None:
    broker = InProcessBroker()
    canary = "REQUEST_ID_CANARY"

    with pytest.raises(RequestUnavailable, match=r"^$") as failure:
        broker.get_request(canary)

    assert canary not in str(failure.value)
