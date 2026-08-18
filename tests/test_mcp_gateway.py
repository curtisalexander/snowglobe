import asyncio
import json

from mcp import Client
from mcp.types import TextContent

from snowglobe.mcp_gateway import server


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
