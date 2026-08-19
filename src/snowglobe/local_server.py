"""Single-process, loopback-only Snowglobe application."""

import uvicorn

from snowglobe.mcp_gateway import server
from snowglobe.result_api import create_app as create_result_api
from snowglobe.runtime import broker


def create_app():
    """Serve MCP and viewer routes from the runtime that owns the local broker."""

    result_api = create_result_api(broker=broker)
    application = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        debug=False,
    )
    application.router.routes[0:0] = result_api.router.routes
    application.state.broker = result_api.state.broker
    application.state.admission_limits = result_api.state.admission_limits
    return application


app = create_app()


def main() -> None:
    """Run one local analyst service without exposing it to the network."""

    uvicorn.run(app, host="127.0.0.1", port=8000)
