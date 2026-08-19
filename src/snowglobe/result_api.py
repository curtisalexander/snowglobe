"""Human-facing Result API for the synthetic boundary proof."""

import struct
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from snowglobe.arrow_stream import (
    ArrowAdmissionLimits,
    ArrowBatchSource,
    admitted_ipc_chunks,
)
from snowglobe.broker import (
    InProcessBroker,
    RequestUnavailable,
    RequestView,
)
from snowglobe.runtime import broker as local_broker

STREAM_CONTENT_TYPE = "application/vnd.snowglobe.arrow-stream"
STREAM_MAGIC = b"SNOWGLOBE-ARROW-STREAM\x01"
ARROW_FRAME = 1
COMPLETE_FRAME = 2
FRAME_HEADER = struct.Struct(">BQ")

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


async def health(_request: Request) -> Response:
    return JSONResponse(
        {"status": "ok"},
        headers=SECURITY_HEADERS,
    )


async def list_requests(request: Request) -> Response:
    try:
        requests = request.app.state.broker.list_requests()
    except Exception:
        return _unavailable()
    return JSONResponse(
        {"requests": [_serialize_view(item) for item in requests]},
        headers=SECURITY_HEADERS,
    )


async def open_request(request: Request) -> Response:
    try:
        item = request.app.state.broker.get_request(request.path_params["request_id"])
    except RequestUnavailable:
        return _not_found()
    except Exception:
        return _unavailable()
    return JSONResponse(_serialize_view(item), headers=SECURITY_HEADERS)


async def cancel_request(request: Request) -> Response:
    try:
        item = request.app.state.broker.cancel(request.path_params["request_id"])
    except RequestUnavailable:
        return _not_found()
    except Exception:
        return _unavailable()
    return JSONResponse(_serialize_view(item), headers=SECURITY_HEADERS)


async def stream_request(request: Request) -> Response:
    try:
        request_id = request.path_params["request_id"]
        source = request.app.state.broker.open_source(request_id)
        admission_limits = request.app.state.admission_limits
        if admission_limits is None:
            return _unavailable()
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
        headers=SECURITY_HEADERS,
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
        async for chunk in admitted_ipc_chunks(source, admission_limits):
            if broker.open_source(request_id) is not source:
                return
            yield FRAME_HEADER.pack(ARROW_FRAME, len(chunk))
            yield chunk
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
        headers=SECURITY_HEADERS,
    )


def _unavailable() -> JSONResponse:
    return JSONResponse(
        {"error": "service_unavailable"},
        status_code=503,
        headers=SECURITY_HEADERS,
    )


def create_app(
    *,
    broker: InProcessBroker | None = None,
    admission_limits: ArrowAdmissionLimits | None = None,
) -> Starlette:
    application = Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/v1/requests", list_requests, methods=["GET"]),
            Route("/v1/requests/{request_id}", open_request, methods=["GET"]),
            Route("/v1/requests/{request_id}/cancel", cancel_request, methods=["POST"]),
            Route("/v1/requests/{request_id}/stream", stream_request, methods=["GET"]),
        ]
    )
    application.state.broker = broker or local_broker
    application.state.admission_limits = admission_limits
    return application


app = create_app()
