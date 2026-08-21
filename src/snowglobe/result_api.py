"""Human-facing result routes for the local viewer."""

import struct
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from snowglobe.arrow_stream import (
    ArrowAdmissionLimits,
    ArrowBatchSource,
    ipc_chunks,
)
from snowglobe.broker import (
    InProcessBroker,
    RequestUnavailable,
    RequestView,
)

STREAM_CONTENT_TYPE = "application/vnd.snowglobe.arrow-stream"
STREAM_MAGIC = b"SNOWGLOBE-ARROW-STREAM\x01"
ARROW_FRAME = 1
COMPLETE_FRAME = 2
FRAME_HEADER = struct.Struct(">BQ")

RESPONSE_HEADERS = {"Cache-Control": "no-store"}


async def health(_request: Request) -> Response:
    return JSONResponse(
        {"status": "ok"},
        headers=RESPONSE_HEADERS,
    )


async def list_requests(request: Request) -> Response:
    try:
        requests = request.app.state.broker.list_requests()
    except Exception:
        return _unavailable()
    return JSONResponse(
        {"requests": [_serialize_view(item) for item in requests]},
        headers=RESPONSE_HEADERS,
    )


async def open_request(request: Request) -> Response:
    try:
        item = request.app.state.broker.get_request(request.path_params["request_id"])
    except RequestUnavailable:
        return _not_found()
    except Exception:
        return _unavailable()
    return JSONResponse(_serialize_view(item), headers=RESPONSE_HEADERS)


async def stream_request(request: Request) -> Response:
    try:
        request_id = request.path_params["request_id"]
        source = request.app.state.broker.open_source(request_id)
        admission_limits = request.app.state.admission_limits
    except RequestUnavailable:
        return _not_found()
    except Exception:
        return _unavailable()

    return StreamingResponse(
        _framed_stream(
            broker=request.app.state.broker,
            request_id=request_id,
            source=source,
            admission_limits=admission_limits,
        ),
        media_type=STREAM_CONTENT_TYPE,
        headers=RESPONSE_HEADERS,
    )


async def _framed_stream(
    *,
    broker: InProcessBroker,
    request_id: str,
    source: ArrowBatchSource,
    admission_limits: ArrowAdmissionLimits,
) -> AsyncIterator[bytes]:
    """Frame Arrow chunks and omit completion unless the local request remains available."""

    yield STREAM_MAGIC
    try:
        async for chunk in ipc_chunks(source, admission_limits.maximum_arrow_bytes):
            if broker.open_source(request_id) is not source:
                return
            yield FRAME_HEADER.pack(ARROW_FRAME, len(chunk)) + chunk
        if broker.open_source(request_id) is not source:
            return
    except Exception:
        return
    yield FRAME_HEADER.pack(COMPLETE_FRAME, 0)


def _serialize_view(item: RequestView) -> dict[str, str]:
    return {
        "request_id": item.request_id,
        "status": item.status.value,
        "expires_at": item.expires_at.isoformat(),
    }


def _not_found() -> JSONResponse:
    return JSONResponse(
        {"error": "not_found"},
        status_code=404,
        headers=RESPONSE_HEADERS,
    )


def _unavailable() -> JSONResponse:
    return JSONResponse(
        {"error": "service_unavailable"},
        status_code=503,
        headers=RESPONSE_HEADERS,
    )


def create_app(
    *,
    broker: InProcessBroker,
    admission_limits: ArrowAdmissionLimits,
) -> Starlette:
    application = Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/v1/requests", list_requests, methods=["GET"]),
            Route("/v1/requests/{request_id}", open_request, methods=["GET"]),
            Route("/v1/requests/{request_id}/stream", stream_request, methods=["GET"]),
        ]
    )
    application.state.broker = broker
    application.state.admission_limits = admission_limits
    return application
