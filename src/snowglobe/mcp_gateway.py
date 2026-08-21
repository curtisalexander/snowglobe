"""Model-facing Snowglobe MCP control plane."""

import json
from datetime import timedelta
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

from snowglobe.contracts import (
    QueryLifecycleStatus,
    QueryReceipt,
    QueryStatusReceipt,
    ReasonCode,
)
from snowglobe.control import ControlPlane, invalid_status_receipt, rejected_receipt

SUBMIT_TOOL_NAME = "submit_read_query"
STATUS_TOOL_NAME = "get_query_status"
INPUT_FIELDS = frozenset({"sql", "requested_ttl"})
STATUS_INPUT_FIELDS = frozenset({"request_id"})
REQUEST_ID_PATTERN = "^[A-Za-z0-9_-]{20,32}$"

SUBMIT_READ_QUERY = Tool(
    name=SUBMIT_TOOL_NAME,
    description=(
        "Submit one governed Snowflake read query. An accepted receipt includes the "
        "opaque request ID and exact governed SQL; query results are never returned "
        "through MCP."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sql": {"type": "string", "minLength": 1},
            "requested_ttl": {"type": "integer", "minimum": 1},
        },
        "required": ["sql", "requested_ttl"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["accepted", "rejected"]},
            "request_id": {"type": "string", "pattern": REQUEST_ID_PATTERN},
            "reason_code": {
                "type": "string",
                "enum": [
                    "NONE",
                    "INVALID_REQUEST",
                    "POLICY_REJECTED",
                    "SERVICE_UNAVAILABLE",
                ],
            },
            "governed_sql": {"type": ["string", "null"], "minLength": 1},
        },
        "required": ["status", "request_id", "reason_code", "governed_sql"],
        "additionalProperties": False,
    },
)

GET_QUERY_STATUS = Tool(
    name=STATUS_TOOL_NAME,
    description=(
        "Check whether an opaque Snowglobe request is pending, complete, or terminal. "
        "Returns no rows, schema, counts, Snowflake identifiers, or database errors."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "request_id": {"type": "string", "pattern": REQUEST_ID_PATTERN},
        },
        "required": ["request_id"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "request_id": {"type": "string", "pattern": REQUEST_ID_PATTERN},
            "status": {
                "type": "string",
                "enum": [status.value for status in QueryLifecycleStatus],
            },
        },
        "required": ["request_id", "status"],
        "additionalProperties": False,
    },
)


async def list_tools(
    _context: ServerRequestContext[Any],
    _params: PaginatedRequestParams | None,
) -> ListToolsResult:
    """Advertise Snowglobe's complete model-facing surface."""

    return ListToolsResult(tools=[SUBMIT_READ_QUERY, GET_QUERY_STATUS])


async def _call_tool(control: ControlPlane, params: CallToolRequestParams) -> CallToolResult:
    """Validate and dispatch a tool call without framework-generated output."""

    try:
        if params.name == SUBMIT_TOOL_NAME:
            arguments = params.arguments
            if arguments is None or not _valid_arguments(arguments):
                return _receipt_result(rejected_receipt(ReasonCode.INVALID_REQUEST))
            receipt = await control.submit(
                sql=arguments["sql"],
                requested_ttl=timedelta(seconds=arguments["requested_ttl"]),
            )
            return _receipt_result(receipt)

        if params.name == STATUS_TOOL_NAME:
            request_id = _valid_status_arguments(params.arguments)
            if request_id is None:
                return _receipt_result(invalid_status_receipt())
            return _receipt_result(control.status(request_id))

        return _receipt_result(rejected_receipt(ReasonCode.INVALID_REQUEST))
    except Exception:
        if params.name == STATUS_TOOL_NAME:
            valid_id = _valid_status_arguments(params.arguments)
            receipt = invalid_status_receipt()
            if valid_id is not None:
                receipt = QueryStatusReceipt(
                    request_id=valid_id,
                    status=QueryLifecycleStatus.SERVICE_UNAVAILABLE,
                )
            return _receipt_result(receipt)
        return _receipt_result(
            rejected_receipt(ReasonCode.SERVICE_UNAVAILABLE),
        )


def create_server(control: ControlPlane) -> Server:
    """Bind the low-level MCP adapter to one process-local control plane."""

    async def call_tool(
        _context: ServerRequestContext[Any],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        return await _call_tool(control, params)

    return Server(
        "Snowglobe",
        version="0.1.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def _valid_arguments(arguments: dict[str, Any] | None) -> bool:
    if arguments is None or set(arguments) != INPUT_FIELDS:
        return False
    if (
        not isinstance(arguments["sql"], str)
        or not arguments["sql"]
        or type(arguments["requested_ttl"]) is not int
        or arguments["requested_ttl"] < 1
    ):
        return False
    try:
        timedelta(seconds=arguments["requested_ttl"])
    except OverflowError:
        return False
    return True


def _valid_status_arguments(arguments: dict[str, Any] | None) -> str | None:
    if arguments is None or set(arguments) != STATUS_INPUT_FIELDS:
        return None
    request_id = arguments["request_id"]
    if not isinstance(request_id, str):
        return None
    try:
        return QueryStatusReceipt(
            request_id=request_id,
            status=QueryLifecycleStatus.NOT_FOUND,
        ).request_id
    except Exception:
        return None


def _receipt_result(receipt: QueryReceipt | QueryStatusReceipt) -> CallToolResult:
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
