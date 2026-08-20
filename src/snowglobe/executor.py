"""Fail-closed background execution seam for governed query work."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from snowglobe.arrow_stream import ArrowBatchSource
from snowglobe.broker import CancellableCursor, InProcessBroker, RequestUnavailable, RequestView

ExecutionStarted = Callable[[CancellableCursor | None], Callable[[], None]]
AdmittedWork = Callable[[str, ExecutionStarted], Awaitable[ArrowBatchSource]]
QueryAdmission = Callable[[str], AdmittedWork]


class BackgroundQueryExecutor:
    """Admit work synchronously, then run it behind one pending broker record."""

    def __init__(self, *, broker: InProcessBroker, admit: QueryAdmission) -> None:
        self._broker = broker
        self._admit = admit
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit(
        self,
        *,
        sql: str,
        requested_ttl: timedelta,
    ) -> RequestView:
        """Return after admission, pending registration, and task scheduling succeed."""

        work = self._admit(sql)
        request = self._broker.submit(requested_ttl=requested_ttl)
        loop = asyncio.get_running_loop()
        coroutine = self._run(request, work)
        try:
            task = loop.create_task(coroutine)
        except Exception:
            coroutine.close()
            with suppress(RequestUnavailable):
                self._broker.fail(request.request_id)
            raise
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return request

    async def close(self) -> None:
        """Cancel pending work and wait for request-scoped cleanup during shutdown."""

        for request in self._broker.list_requests():
            if request.status.value == "pending":
                with suppress(RequestUnavailable):
                    self._broker.cancel(request.request_id)
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def _run(
        self,
        request: RequestView,
        work: AdmittedWork,
    ) -> None:
        def mark_started(cursor: CancellableCursor | None) -> Callable[[], None]:
            if cursor is not None:
                self._broker.register_cursor(request.request_id, cursor)

            def release() -> None:
                if cursor is not None:
                    with suppress(RequestUnavailable):
                        self._broker.release_cursor(request.request_id, cursor)

            return release

        expiry_task: asyncio.Task[None] | None = None
        try:
            work_task = asyncio.ensure_future(work(request.request_id, mark_started))
            expiry_delay = max((request.expires_at - datetime.now(UTC)).total_seconds(), 0)
            expiry_task = asyncio.create_task(asyncio.sleep(expiry_delay))
            done, _pending = await asyncio.wait(
                {work_task, expiry_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if expiry_task in done and not work_task.done():
                with suppress(RequestUnavailable):
                    self._broker.get_request(request.request_id)
            source = await work_task
            expiry_task.cancel()
            with suppress(asyncio.CancelledError):
                await expiry_task
            self._broker.publish(request.request_id, source)
        except BaseException:
            with suppress(RequestUnavailable):
                self._broker.fail(request.request_id)
        finally:
            if expiry_task is not None and not expiry_task.done():
                expiry_task.cancel()
