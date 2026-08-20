"""Transport-neutral, result-free Snowglobe control plane."""

import secrets
from datetime import timedelta
from typing import Protocol

from snowglobe.broker import RequestUnavailable, RequestView
from snowglobe.contracts import (
    QueryLifecycleStatus,
    QueryReceipt,
    QueryStatusReceipt,
    ReasonCode,
    ReceiptStatus,
)
from snowglobe.executor import BackgroundQueryExecutor
from snowglobe.sql_policy import QueryPolicyRejected


class ControlBroker(Protocol):
    def get_request(self, request_id: str) -> RequestView: ...


class ControlPlane:
    """Submit governed work and expose only closed lifecycle receipts."""

    def __init__(
        self,
        *,
        broker: ControlBroker,
        executor: BackgroundQueryExecutor | None,
    ) -> None:
        self._broker = broker
        self._executor = executor

    async def submit(
        self,
        *,
        sql: str,
        requested_ttl: timedelta,
    ) -> QueryReceipt:
        if self._executor is None:
            return rejected_receipt(ReasonCode.SERVICE_UNAVAILABLE)
        try:
            request = await self._executor.submit(
                sql=sql,
                requested_ttl=requested_ttl,
            )
        except QueryPolicyRejected:
            return rejected_receipt(ReasonCode.POLICY_REJECTED)
        except Exception:
            return rejected_receipt(ReasonCode.SERVICE_UNAVAILABLE)
        return QueryReceipt(
            status=ReceiptStatus.ACCEPTED,
            request_id=request.request_id,
            reason_code=ReasonCode.NONE,
        )

    def status(self, request_id: str) -> QueryStatusReceipt:
        try:
            item = self._broker.get_request(request_id)
        except RequestUnavailable:
            return QueryStatusReceipt(
                request_id=request_id,
                status=QueryLifecycleStatus.NOT_FOUND,
            )
        except Exception:
            return QueryStatusReceipt(
                request_id=request_id,
                status=QueryLifecycleStatus.SERVICE_UNAVAILABLE,
            )
        return QueryStatusReceipt(
            request_id=request_id,
            status=QueryLifecycleStatus(item.status.value),
        )

    async def close(self) -> None:
        if self._executor is not None:
            await self._executor.close()


def rejected_receipt(reason_code: ReasonCode) -> QueryReceipt:
    return QueryReceipt(
        status=ReceiptStatus.REJECTED,
        request_id=secrets.token_urlsafe(18),
        reason_code=reason_code,
    )


def invalid_status_receipt() -> QueryStatusReceipt:
    return QueryStatusReceipt(
        request_id=secrets.token_urlsafe(18),
        status=QueryLifecycleStatus.NOT_FOUND,
    )
