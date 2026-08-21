"""Single-process, loopback-only Snowglobe application."""

import argparse
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from starlette.applications import Starlette

from snowglobe.mcp_gateway import create_server
from snowglobe.mvp_limits import MVP_ARROW_LIMITS
from snowglobe.result_api import create_app as create_result_api
from snowglobe.runtime import Runtime, create_runtime


def create_app(runtime: Runtime):
    """Serve MCP and viewer routes from the runtime that owns the local broker."""

    result_api = create_result_api(broker=runtime.broker, admission_limits=MVP_ARROW_LIMITS)
    application = create_server(runtime.control).streamable_http_app(
        stateless_http=True,
        json_response=True,
        debug=False,
    )
    application.router.routes[0:0] = result_api.router.routes
    application.state.broker = result_api.state.broker
    application.state.admission_limits = result_api.state.admission_limits
    original_lifespan = application.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with original_lifespan(app):
            try:
                yield
            finally:
                await runtime.close()

    application.router.lifespan_context = lifespan
    application.state.runtime = runtime
    return application


def main(argv: Sequence[str] | None = None) -> int:
    """Run one local analyst service without exposing it to the network."""

    parser = argparse.ArgumentParser(description="Run the local Snowglobe service.")
    parser.add_argument(
        "--connections",
        type=Path,
        help="native Snowflake connections.toml file",
    )
    parser.add_argument("--snowglobe-config", type=Path, help="Snowglobe policy file")
    parser.add_argument("--profile", default="default")
    arguments = parser.parse_args(argv)

    try:
        runtime = create_runtime(
            connections_path=arguments.connections,
            snowglobe_config_path=arguments.snowglobe_config,
            profile_name=arguments.profile,
        )
        application = create_app(runtime)
    except Exception as error:
        print(f"Snowglobe startup failed: {error}", file=sys.stderr)
        return 1

    uvicorn.run(application, host="127.0.0.1", port=8000)
    return 0
