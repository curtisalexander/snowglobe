"""Model-facing Snowglobe MCP control plane."""

import json
import secrets
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from snowglobe.contracts import QueryReceipt, ReasonCode, ReceiptStatus

TOOL_NAME = "submit_read_query"
INPUT_FIELDS = frozenset({"sql", "purpose", "requested_ttl"})

SUBMIT_READ_QUERY = Tool(
    name=TOOL_NAME,
    description=(
        "Submit one governed Snowflake read query. Returns only an opaque receipt; "
        "query results are never returned through MCP."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sql": {"type": "string", "minLength": 1},
            "purpose": {"type": "string", "minLength": 1},
            "requested_ttl": {"type": "integer", "minimum": 1},
        },
        "required": ["sql", "purpose", "requested_ttl"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["accepted", "rejected"]},
            "request_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{20,32}$"},
            "reason_code": {
                "type": "string",
                "enum": [
                    "NONE",
                    "INVALID_REQUEST",
                    "POLICY_REJECTED",
                    "SERVICE_UNAVAILABLE",
                ],
            },
        },
        "required": ["status", "request_id", "reason_code"],
        "additionalProperties": False,
    },
)


async def list_tools(
    _context: ServerRequestContext[Any],
    _params: PaginatedRequestParams | None,
) -> ListToolsResult:
    """Advertise Snowglobe's complete model-facing surface."""

    return ListToolsResult(tools=[SUBMIT_READ_QUERY])


async def call_tool(
    _context: ServerRequestContext[Any],
    params: CallToolRequestParams,
) -> CallToolResult:
    """Validate and dispatch a tool call without framework-generated output."""

    try:
        if params.name != TOOL_NAME:
            return CallToolResult(
                content=[TextContent(type="text", text="Tool unavailable.")],
                is_error=True,
            )

        if not _valid_arguments(params.arguments):
            return _receipt(ReasonCode.INVALID_REQUEST)

        # The scaffold remains fail-closed until the synthetic broker, authenticated
        # ownership binding, and policy service are implemented together.
        return _receipt(ReasonCode.SERVICE_UNAVAILABLE)
    except Exception:
        return _receipt(ReasonCode.SERVICE_UNAVAILABLE)


def _valid_arguments(arguments: dict[str, Any] | None) -> bool:
    if arguments is None or set(arguments) != INPUT_FIELDS:
        return False
    return (
        isinstance(arguments["sql"], str)
        and bool(arguments["sql"])
        and isinstance(arguments["purpose"], str)
        and bool(arguments["purpose"])
        and type(arguments["requested_ttl"]) is int
        and arguments["requested_ttl"] >= 1
    )


def _receipt(reason_code: ReasonCode) -> CallToolResult:
    receipt = QueryReceipt(
        status=ReceiptStatus.REJECTED,
        request_id=secrets.token_urlsafe(18),
        reason_code=reason_code,
    )
    structured_content = receipt.model_dump(mode="json")
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(structured_content, separators=(",", ":")),
            )
        ],
        structured_content=structured_content,
    )


server = Server(
    "Snowglobe",
    version="0.1.0",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)

# This is a complete, separately deployable Starlette application. Stateless JSON
# responses retain the standard MCP Streamable HTTP transport without SSE sessions.
app = server.streamable_http_app(stateless_http=True, json_response=True, debug=False)
