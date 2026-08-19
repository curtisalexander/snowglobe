import asyncio
import json

import httpx2
from mcp import Client, ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from pytest import CaptureFixture, MonkeyPatch

from snowglobe import mcp_gateway
from snowglobe.mcp_gateway import app, server


def test_advertises_only_one_exact_tool_contract() -> None:
    async def exercise() -> None:
        async with Client(server) as client:
            capabilities = client.server_capabilities.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            assert capabilities == {"tools": {"listChanged": False}}

            tools = await client.list_tools()
            assert len(tools.tools) == 1
            tool = tools.tools[0]
            assert tool.name == "submit_read_query"
            assert tool.input_schema["additionalProperties"] is False
            assert tool.output_schema is not None
            assert tool.output_schema["additionalProperties"] is False
            assert set(tool.output_schema["properties"]) == {
                "status",
                "request_id",
                "reason_code",
            }

    asyncio.run(exercise())


def test_receipt_has_constant_shape_without_input_data() -> None:
    canary = "RESULT_CANARY_MUST_NOT_ESCAPE"

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "submit_read_query",
                {
                    "sql": f"select '{canary}'",
                    "purpose": canary,
                    "requested_ttl": 900,
                },
            )

            assert result.structured_content is not None
            assert set(result.structured_content) == {"status", "request_id", "reason_code"}
            assert result.structured_content["status"] == "rejected"
            assert result.structured_content["reason_code"] == "SERVICE_UNAVAILABLE"
            assert len(result.content) == 1
            assert isinstance(result.content[0], TextContent)
            assert json.loads(result.content[0].text) == result.structured_content
            assert canary not in json.dumps(result.structured_content)
            assert canary not in result.model_dump_json()

    asyncio.run(exercise())


def test_unknown_tool_name_is_not_reflected() -> None:
    canary = "UNKNOWN_TOOL_CANARY"

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(canary, {})

            assert result.is_error is True
            assert result.structured_content is None
            assert canary not in result.model_dump_json()

    asyncio.run(exercise())


def test_invalid_arguments_return_only_fixed_reason() -> None:
    canary = "INVALID_ARGUMENT_CANARY"

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "submit_read_query",
                {
                    "sql": canary,
                    "purpose": canary,
                    "requested_ttl": True,
                },
            )

            assert result.structured_content is not None
            assert result.structured_content["reason_code"] == "INVALID_REQUEST"
            assert canary not in result.model_dump_json()

    asyncio.run(exercise())


def test_unexpected_exception_is_sanitized(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    canary = "INTERNAL_EXCEPTION_CANARY"

    def fail_validation(_arguments: object) -> bool:
        raise RuntimeError(canary)

    monkeypatch.setattr(mcp_gateway, "_valid_arguments", fail_validation)

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "submit_read_query",
                {"sql": "select 1", "purpose": "test", "requested_ttl": 60},
            )

            assert result.structured_content is not None
            assert result.structured_content["reason_code"] == "SERVICE_UNAVAILABLE"
            assert canary not in result.model_dump_json()

    asyncio.run(exercise())
    captured = capsys.readouterr()
    assert canary not in captured.out
    assert canary not in captured.err


def test_streamable_http_round_trip_preserves_the_contract() -> None:
    async def exercise() -> None:
        async with app.router.lifespan_context(app):
            transport = httpx2.ASGITransport(app=app)
            async with (
                httpx2.AsyncClient(
                    transport=transport,
                    base_url="http://localhost:8000",
                ) as http_client,
                streamable_http_client(
                    "http://localhost:8000/mcp",
                    http_client=http_client,
                    terminate_on_close=False,
                ) as streams,
                ClientSession(*streams) as session,
            ):
                initialized = await session.initialize()
                capabilities = initialized.capabilities.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_defaults=True,
                    exclude_none=True,
                )
                assert capabilities == {
                    "experimental": {},
                    "tools": {"listChanged": False},
                }

                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == ["submit_read_query"]

                result = await session.call_tool(
                    "submit_read_query",
                    {"sql": "select 1", "purpose": "test", "requested_ttl": 60},
                )
                assert result.structured_content is not None
                assert result.structured_content["reason_code"] == "SERVICE_UNAVAILABLE"

    asyncio.run(exercise())
