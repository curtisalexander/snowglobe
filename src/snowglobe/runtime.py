"""Process-local composition shared by the control and viewer adapters."""

from dataclasses import dataclass
from pathlib import Path

from snowglobe.broker import InProcessBroker
from snowglobe.control import ControlPlane
from snowglobe.mvp_limits import MVP_MAXIMUM_PENDING_REQUESTS, MVP_MAXIMUM_TTL
from snowglobe.snowflake import SnowflakeConnect
from snowglobe.snowflake_executor import create_snowflake_executor


@dataclass(frozen=True, slots=True)
class Runtime:
    broker: InProcessBroker
    control: ControlPlane

    async def close(self) -> None:
        await self.control.close()


def create_runtime(
    *,
    config_path: Path | None = None,
    profile_name: str = "default",
    connect: SnowflakeConnect | None = None,
) -> Runtime:
    broker = InProcessBroker(
        maximum_ttl=MVP_MAXIMUM_TTL,
        maximum_pending_requests=MVP_MAXIMUM_PENDING_REQUESTS,
    )
    executor = None
    if config_path is not None:
        executor = create_snowflake_executor(
            broker=broker,
            config_path=config_path,
            profile_name=profile_name,
            connect=connect,
        )
    return Runtime(
        broker=broker,
        control=ControlPlane(broker=broker, executor=executor),
    )


runtime = create_runtime()
broker = runtime.broker
