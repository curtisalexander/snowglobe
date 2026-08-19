"""Fail-closed background execution seam for governed query work."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta

from snowglobe.arrow_stream import ArrowBatchSource
from snowglobe.broker import InProcessBroker, RequestUnavailable, RequestView

AdmittedWork = Callable[[str], Awaitable[ArrowBatchSource]]
QueryAdmission = Callable[[str, str], AdmittedWork]


class BackgroundQueryExecutor:
    """Admit work synchronously, then run it behind one pending broker record."""

    def __init__(self, *, broker: InProcessBroker, admit: QueryAdmission) -> None:
        self._broker = broker
        self._admit = admit
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(
        self,
        *,
        sql: str,
        purpose: str,
        requested_ttl: timedelta,
    ) -> RequestView:
        """Return only after admission, pending registration, and task startup succeed."""

        work = self._admit(sql, purpose)
        request = self._broker.submit(requested_ttl=requested_ttl)
        coroutine = self._run(request.request_id, work)
        try:
            task = asyncio.get_running_loop().create_task(coroutine)
        except Exception:
            coroutine.close()
            with suppress(RequestUnavailable):
                self._broker.fail(request.request_id)
            raise
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return request

    async def _run(self, request_id: str, work: AdmittedWork) -> None:
        try:
            source = await work(request_id)
            self._broker.publish(request_id, source)
        except Exception:
            with suppress(RequestUnavailable):
                self._broker.fail(request_id)
