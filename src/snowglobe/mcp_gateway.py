"""Model-facing Snowglobe MCP control plane."""

import secrets
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from snowglobe.contracts import QueryReceipt, ReasonCode, ReceiptStatus

mcp = MCPServer("Snowglobe")


@mcp.tool(structured_output=True)
async def submit_read_query(
    sql: Annotated[str, Field(description="One governed Snowflake read query.")],
    purpose: Annotated[str, Field(description="Why the human needs this result.")],
    requested_ttl: Annotated[int, Field(description="Requested lifetime in seconds.")],
) -> QueryReceipt:
    """Submit a read query without returning result-derived information.

    The initial scaffold deliberately rejects every submission until the synthetic
    broker, ownership binding, and policy service exist.
    """

    del sql, purpose, requested_ttl
    return QueryReceipt(
        status=ReceiptStatus.REJECTED,
        request_id=secrets.token_urlsafe(18),
        reason_code=ReasonCode.SERVICE_UNAVAILABLE,
    )


app = mcp.streamable_http_app()
