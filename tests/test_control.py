import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pyarrow as pa

from snowglobe.broker import InProcessBroker
from snowglobe.control import ControlPlane
from snowglobe.executor import BackgroundQueryExecutor
from snowglobe.sql_policy import QueryPolicyRejected


class Source:
    schema = pa.schema([("PRIVATE_RESULT_COLUMN", pa.string())])

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        if False:
            yield pa.record_batch([], schema=self.schema)


def test_control_plane_submits_and_polls_without_result_data() -> None:
    broker = InProcessBroker()

    def admit(_sql: str, _purpose: str):
        async def work(_request_id: str, mark_started) -> Source:
            mark_started(None)
            return Source()

        return work

    control = ControlPlane(
        broker=broker,
        executor=BackgroundQueryExecutor(broker=broker, admit=admit),
    )

    async def exercise() -> None:
        submitted = await control.submit(
            sql="select 'PRIVATE_RESULT_VALUE'",
            purpose="PRIVATE_PURPOSE",
            requested_ttl=timedelta(minutes=1),
        )
        while control.status(submitted.request_id).status == "pending":
            await asyncio.sleep(0)
        status = control.status(submitted.request_id)

        assert submitted.model_dump(mode="json") == {
            "status": "accepted",
            "request_id": submitted.request_id,
            "reason_code": "NONE",
        }
        assert status.model_dump(mode="json") == {
            "request_id": submitted.request_id,
            "status": "complete",
        }

    asyncio.run(exercise())


def test_control_plane_maps_policy_and_service_failures_to_fixed_receipts() -> None:
    broker = InProcessBroker()

    def reject(_sql: str, _purpose: str):
        raise QueryPolicyRejected

    policy_control = ControlPlane(
        broker=broker,
        executor=BackgroundQueryExecutor(broker=broker, admit=reject),
    )
    unavailable_control = ControlPlane(broker=broker, executor=None)

    async def exercise() -> None:
        policy = await policy_control.submit(
            sql="PRIVATE_SQL",
            purpose="PRIVATE_PURPOSE",
            requested_ttl=timedelta(minutes=1),
        )
        unavailable = await unavailable_control.submit(
            sql="PRIVATE_SQL",
            purpose="PRIVATE_PURPOSE",
            requested_ttl=timedelta(minutes=1),
        )
        assert policy.reason_code == "POLICY_REJECTED"
        assert unavailable.reason_code == "SERVICE_UNAVAILABLE"

    asyncio.run(exercise())
