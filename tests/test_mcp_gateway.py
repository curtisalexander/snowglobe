import asyncio
import json
from collections.abc import AsyncIterator
from datetime import timedelta

import httpx2
import pyarrow as pa
from mcp import Client, ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from pytest import CaptureFixture, MonkeyPatch

from snowglobe.broker import InProcessBroker
from snowglobe.control import ControlPlane
from snowglobe.executor import BackgroundQueryExecutor
from snowglobe.mcp_gateway import app, create_server, server
from snowglobe.sql_policy import QueryPolicyRejected


class Source:
    schema = pa.schema([("RESULT_COLUMN_CANARY", pa.string())])

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        if False:
            yield pa.record_batch([], schema=self.schema)


def test_advertises_only_the_two_exact_tool_contracts() -> None:
    async def exercise() -> None:
        async with Client(server) as client:
            capabilities = client.server_capabilities.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            assert capabilities == {"tools": {"listChanged": False}}

            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == [
                "submit_read_query",
                "get_query_status",
            ]
            submit, status = tools.tools
            for tool in tools.tools:
                assert tool.input_schema["additionalProperties"] is False
                assert tool.output_schema is not None
                assert tool.output_schema["additionalProperties"] is False
            assert submit.output_schema is not None
            assert status.output_schema is not None
            assert set(submit.output_schema["properties"]) == {
                "status",
                "request_id",
                "reason_code",
            }
            assert set(status.output_schema["properties"]) == {"request_id", "status"}
            assert status.output_schema["properties"]["status"]["enum"] == [
                "pending",
                "complete",
                "failed",
                "cancelled",
                "expired",
                "not_found",
                "service_unavailable",
            ]

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


def test_unrepresentable_ttl_is_an_invalid_request() -> None:
    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "submit_read_query",
                {
                    "sql": "select 1",
                    "purpose": "test",
                    "requested_ttl": 10**100,
                },
            )

            assert result.structured_content is not None
            assert result.structured_content["reason_code"] == "INVALID_REQUEST"

    asyncio.run(exercise())


def test_synthetic_submission_returns_accepted_only_after_pending_startup() -> None:
    request_broker = InProcessBroker()
    started = asyncio.Event()
    release = asyncio.Event()
    source = Source()
    canary = "SUBMISSION_VALUE_CANARY"

    def admit(sql: str, purpose: str):
        assert canary in sql
        assert purpose == canary

        async def work(request_id: str, mark_started) -> Source:
            assert request_broker.get_request(request_id).status.value == "pending"
            mark_started(None)
            started.set()
            await release.wait()
            return source

        return work

    synthetic_server = create_server(
        ControlPlane(
            broker=request_broker,
            executor=BackgroundQueryExecutor(broker=request_broker, admit=admit),
        )
    )

    async def exercise() -> None:
        async with Client(synthetic_server) as client:
            accepted = await client.call_tool(
                "submit_read_query",
                {
                    "sql": f"select '{canary}'",
                    "purpose": canary,
                    "requested_ttl": 60,
                },
            )
            assert accepted.structured_content is not None
            request_id = accepted.structured_content["request_id"]
            assert accepted.structured_content == {
                "status": "accepted",
                "request_id": request_id,
                "reason_code": "NONE",
            }
            assert isinstance(accepted.content[0], TextContent)
            assert json.loads(accepted.content[0].text) == accepted.structured_content
            assert canary not in accepted.model_dump_json()

            await started.wait()
            pending = await client.call_tool("get_query_status", {"request_id": request_id})
            assert pending.structured_content == {
                "request_id": request_id,
                "status": "pending",
            }

            release.set()
            while request_broker.get_request(request_id).status.value == "pending":
                await asyncio.sleep(0)
            complete = await client.call_tool("get_query_status", {"request_id": request_id})
            assert complete.structured_content == {
                "request_id": request_id,
                "status": "complete",
            }
            assert canary not in complete.model_dump_json()

    asyncio.run(exercise())


def test_background_execution_failure_exposes_only_failed_without_process_output(
    capsys: CaptureFixture[str],
) -> None:
    request_broker = InProcessBroker()
    finished = asyncio.Event()
    sql_canary = "EXECUTION_SQL_CANARY"
    purpose_canary = "EXECUTION_PURPOSE_CANARY"
    error_canary = "EXECUTION_ERROR_CANARY"

    def admit(sql: str, purpose: str):
        assert sql_canary in sql
        assert purpose == purpose_canary

        async def work(_request_id: str, mark_started) -> Source:
            mark_started(None)
            finished.set()
            raise RuntimeError(error_canary)

        return work

    synthetic_server = create_server(
        ControlPlane(
            broker=request_broker,
            executor=BackgroundQueryExecutor(broker=request_broker, admit=admit),
        )
    )

    async def exercise() -> None:
        async with Client(synthetic_server) as client:
            accepted = await client.call_tool(
                "submit_read_query",
                {
                    "sql": f"select '{sql_canary}'",
                    "purpose": purpose_canary,
                    "requested_ttl": 60,
                },
            )
            assert accepted.structured_content is not None
            request_id = accepted.structured_content["request_id"]

            await finished.wait()
            while request_broker.get_request(request_id).status.value == "pending":
                await asyncio.sleep(0)
            failed = await client.call_tool("get_query_status", {"request_id": request_id})

            assert failed.structured_content == {
                "request_id": request_id,
                "status": "failed",
            }
            model_visible = accepted.model_dump_json() + failed.model_dump_json()
            for canary in (sql_canary, purpose_canary, error_canary):
                assert canary not in model_visible

    asyncio.run(exercise())
    captured = capsys.readouterr()
    for canary in (sql_canary, purpose_canary, error_canary):
        assert canary not in captured.out
        assert canary not in captured.err


def test_synthetic_policy_rejection_uses_only_fixed_reason() -> None:
    request_broker = InProcessBroker()

    def reject(_sql: str, _purpose: str):
        raise QueryPolicyRejected

    synthetic_server = create_server(
        ControlPlane(
            broker=request_broker,
            executor=BackgroundQueryExecutor(broker=request_broker, admit=reject),
        )
    )

    async def exercise() -> None:
        async with Client(synthetic_server) as client:
            result = await client.call_tool(
                "submit_read_query",
                {"sql": "select 1", "purpose": "test", "requested_ttl": 60},
            )
            assert result.structured_content is not None
            assert result.structured_content["status"] == "rejected"
            assert result.structured_content["reason_code"] == "POLICY_REJECTED"
            assert request_broker.list_requests() == ()

    asyncio.run(exercise())


def test_status_tool_reports_only_lifecycle_state() -> None:
    request_broker = InProcessBroker()
    item = request_broker.submit(requested_ttl=timedelta(minutes=5))
    synthetic_server = create_server(ControlPlane(broker=request_broker, executor=None))

    async def exercise() -> None:
        async with Client(synthetic_server) as client:
            pending = await client.call_tool(
                "get_query_status",
                {"request_id": item.request_id},
            )

            assert pending.structured_content == {
                "request_id": item.request_id,
                "status": "pending",
            }
            assert len(pending.content) == 1
            assert isinstance(pending.content[0], TextContent)
            assert json.loads(pending.content[0].text) == pending.structured_content

            request_broker.fail(item.request_id)
            failed = await client.call_tool(
                "get_query_status",
                {"request_id": item.request_id},
            )
            assert failed.structured_content == {
                "request_id": item.request_id,
                "status": "failed",
            }

    asyncio.run(exercise())


def test_status_tool_does_not_reflect_invalid_ids() -> None:
    canary = "INVALID.STATUS.ID.CANARY"

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool("get_query_status", {"request_id": canary})

            assert result.structured_content is not None
            assert result.structured_content["status"] == "not_found"
            assert canary not in result.model_dump_json()

    asyncio.run(exercise())


def test_unexpected_exception_is_sanitized(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    from snowglobe import mcp_gateway

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
                assert [tool.name for tool in tools.tools] == [
                    "submit_read_query",
                    "get_query_status",
                ]

                result = await session.call_tool(
                    "submit_read_query",
                    {"sql": "select 1", "purpose": "test", "requested_ttl": 60},
                )
                assert result.structured_content is not None
                assert result.structured_content["reason_code"] == "SERVICE_UNAVAILABLE"

                status = await session.call_tool(
                    "get_query_status",
                    {"request_id": result.structured_content["request_id"]},
                )
                assert status.structured_content is not None
                assert status.structured_content["status"] == "not_found"

    asyncio.run(exercise())
