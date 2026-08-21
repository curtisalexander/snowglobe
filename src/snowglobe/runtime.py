"""Process-local composition shared by the control and viewer adapters."""

from dataclasses import dataclass
from pathlib import Path

from snowglobe.broker import InProcessBroker
from snowglobe.control import ControlPlane
from snowglobe.mvp_limits import (
    MVP_MAXIMUM_PENDING_REQUESTS,
    MVP_MAXIMUM_REQUESTS,
    MVP_MAXIMUM_TTL,
)
from snowglobe.snowflake_executor import create_snowflake_executor


@dataclass(frozen=True, slots=True)
class Runtime:
    broker: InProcessBroker
    control: ControlPlane

    async def close(self) -> None:
        await self.control.close()


def create_runtime(
    *,
    connections_path: Path | None = None,
    snowglobe_config_path: Path | None = None,
    profile_name: str = "default",
) -> Runtime:
    broker = InProcessBroker(
        maximum_ttl=MVP_MAXIMUM_TTL,
        maximum_pending_requests=MVP_MAXIMUM_PENDING_REQUESTS,
        maximum_requests=MVP_MAXIMUM_REQUESTS,
    )
    if (connections_path is None) != (snowglobe_config_path is None):
        raise ValueError("--connections and --snowglobe-config must be supplied together")
    executor = None
    if connections_path is not None and snowglobe_config_path is not None:
        executor = create_snowflake_executor(
            broker=broker,
            connections_path=connections_path,
            snowglobe_config_path=snowglobe_config_path,
            profile_name=profile_name,
        )
    return Runtime(
        broker=broker,
        control=ControlPlane(broker=broker, executor=executor),
    )
