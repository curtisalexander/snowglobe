import asyncio
import json

from mcp import Client

from snowglobe.mcp_gateway import mcp


def test_only_tool_returns_constant_shape_without_input() -> None:
    canary = "RESULT_CANARY_MUST_NOT_ESCAPE"

    async def exercise() -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == ["submit_read_query"]

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
            assert canary not in json.dumps(result.structured_content)
            assert canary not in result.model_dump_json()

    asyncio.run(exercise())
