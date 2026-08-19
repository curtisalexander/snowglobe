"""Model-facing Snowglobe MCP control plane."""

import json
import secrets
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

from snowglobe.broker import RequestUnavailable
from snowglobe.contracts import (
    QueryLifecycleStatus,
    QueryReceipt,
    QueryStatusReceipt,
    ReasonCode,
    ReceiptStatus,
)
from snowglobe.executor import BackgroundQueryExecutor, QueryPolicyRejected
from snowglobe.runtime import broker

SUBMIT_TOOL_NAME = "submit_read_query"
STATUS_TOOL_NAME = "get_query_status"
INPUT_FIELDS = frozenset({"sql", "purpose", "requested_ttl"})
STATUS_INPUT_FIELDS = frozenset({"request_id"})
REQUEST_ID_PATTERN = "^[A-Za-z0-9_-]{20,32}$"

# The deployable scaffold remains fail-closed. Tests may inject a synthetic admitted
# executor; real configuration must wait for SQL policy and execution limits.
submission_executor: BackgroundQueryExecutor | None = None

SUBMIT_READ_QUERY = Tool(
    name=SUBMIT_TOOL_NAME,
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
        },
        "required": ["status", "request_id", "reason_code"],
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


async def call_tool(
    _context: ServerRequestContext[Any],
    params: CallToolRequestParams,
) -> CallToolResult:
    """Validate and dispatch a tool call without framework-generated output."""

    try:
        if params.name == SUBMIT_TOOL_NAME:
            arguments = params.arguments
            if arguments is None or not _valid_arguments(arguments):
                return _receipt(ReasonCode.INVALID_REQUEST)

            if submission_executor is None:
                return _receipt(ReasonCode.SERVICE_UNAVAILABLE)
            try:
                request = submission_executor.submit(
                    sql=arguments["sql"],
                    purpose=arguments["purpose"],
                    requested_ttl=timedelta(seconds=arguments["requested_ttl"]),
                )
            except QueryPolicyRejected:
                return _receipt(ReasonCode.POLICY_REJECTED)
            return _accepted_receipt(request.request_id)

        if params.name == STATUS_TOOL_NAME:
            request_id = _valid_status_arguments(params.arguments)
            if request_id is None:
                return _status_receipt(secrets.token_urlsafe(18), QueryLifecycleStatus.NOT_FOUND)
            try:
                item = broker.get_request(request_id)
            except RequestUnavailable:
                return _status_receipt(request_id, QueryLifecycleStatus.NOT_FOUND)
            return _status_receipt(request_id, QueryLifecycleStatus(item.status.value))

        else:
            return CallToolResult(
                content=[TextContent(type="text", text="Tool unavailable.")],
                is_error=True,
            )
    except Exception:
        if params.name == STATUS_TOOL_NAME:
            request_id = _valid_status_arguments(params.arguments)
            return _status_receipt(
                request_id or secrets.token_urlsafe(18),
                QueryLifecycleStatus.SERVICE_UNAVAILABLE,
            )
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


def _accepted_receipt(request_id: str) -> CallToolResult:
    receipt = QueryReceipt(
        status=ReceiptStatus.ACCEPTED,
        request_id=request_id,
        reason_code=ReasonCode.NONE,
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


def _status_receipt(
    request_id: str,
    status: QueryLifecycleStatus,
) -> CallToolResult:
    receipt = QueryStatusReceipt(request_id=request_id, status=status)
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

# This app is useful for transport tests; the supported local launcher composes its
# routes with the viewer backend so both paths share one process-local broker.
app = server.streamable_http_app(stateless_http=True, json_response=True, debug=False)
