"""Result-free shell adapter for agents without native MCP support."""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import timedelta
from typing import Any, Never

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from snowglobe.contracts import (
    QueryLifecycleStatus,
    QueryReceipt,
    QueryStatusReceipt,
    ReasonCode,
)
from snowglobe.control import invalid_status_receipt, rejected_receipt
from snowglobe.mcp_gateway import STATUS_TOOL_NAME, SUBMIT_TOOL_NAME

MCP_URL = "http://127.0.0.1:8000/mcp"


class _InvalidCommand(Exception):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise _InvalidCommand


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="Call the local Snowglobe control plane.")
    commands = parser.add_subparsers(dest="command", required=True)

    submit = commands.add_parser("submit", help="submit SQL read from standard input")
    submit.add_argument("--purpose", required=True)
    submit.add_argument("--ttl", required=True, type=int)

    status = commands.add_parser("status", help="poll one opaque request ID")
    status.add_argument("request_id")
    return parser


async def _invoke(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    async with (
        streamable_http_client(MCP_URL, terminate_on_close=False) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        result = await session.call_tool(name, arguments)
        return result.structured_content


async def _run(arguments: argparse.Namespace, sql: str) -> QueryReceipt | QueryStatusReceipt:
    if arguments.command == "submit":
        try:
            requested_ttl = timedelta(seconds=arguments.ttl)
        except OverflowError:
            requested_ttl = timedelta(0)
        if not sql or not arguments.purpose or requested_ttl <= timedelta(0):
            return rejected_receipt(ReasonCode.INVALID_REQUEST)
        try:
            content = await _invoke(
                SUBMIT_TOOL_NAME,
                {
                    "sql": sql,
                    "purpose": arguments.purpose,
                    "requested_ttl": arguments.ttl,
                },
            )
            return QueryReceipt.model_validate(content)
        except Exception:
            return rejected_receipt(ReasonCode.SERVICE_UNAVAILABLE)

    try:
        valid_request_id = QueryStatusReceipt(
            request_id=arguments.request_id,
            status=QueryLifecycleStatus.NOT_FOUND,
        ).request_id
    except Exception:
        return invalid_status_receipt()

    try:
        content = await _invoke(STATUS_TOOL_NAME, {"request_id": arguments.request_id})
        receipt = QueryStatusReceipt.model_validate(content)
        if receipt.request_id != valid_request_id:
            raise ValueError
        return receipt
    except Exception:
        return QueryStatusReceipt(
            request_id=valid_request_id,
            status=QueryLifecycleStatus.SERVICE_UNAVAILABLE,
        )


def main(argv: Sequence[str] | None = None) -> int:
    raw_arguments = list(argv) if argv is not None else sys.argv[1:]
    try:
        arguments = _parser().parse_args(raw_arguments)
    except _InvalidCommand:
        receipt = (
            invalid_status_receipt()
            if raw_arguments[:1] == ["status"]
            else rejected_receipt(ReasonCode.INVALID_REQUEST)
        )
        print(json.dumps(receipt.model_dump(mode="json"), separators=(",", ":")))
        return 0

    sql = sys.stdin.read() if arguments.command == "submit" else ""
    receipt = asyncio.run(_run(arguments, sql))
    print(json.dumps(receipt.model_dump(mode="json"), separators=(",", ":")))
    return 0
