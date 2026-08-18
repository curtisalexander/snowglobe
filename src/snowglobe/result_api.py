"""Human-facing Result API for the synthetic boundary proof."""

import struct
from collections.abc import AsyncIterator
from typing import Protocol

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
    RequestAccessDenied,
    RequestView,
    ViewerClaims,
)

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


class ViewerAuthenticator(Protocol):
    """Adapter boundary that returns only independently verified viewer claims."""

    async def authenticate(self, request: Request) -> ViewerClaims: ...


class DenyAllViewerAuthenticator:
    """Fail-closed default until a deployment selects a human identity provider."""

    async def authenticate(self, request: Request) -> ViewerClaims:
        del request
        raise RequestAccessDenied


async def health(_request: Request) -> Response:
    return JSONResponse(
        {"status": "ok"},
        headers=SECURITY_HEADERS,
    )


async def list_requests(request: Request) -> Response:
    try:
        claims = await _claims(request)
        requests = request.app.state.broker.list_requests(claims)
    except RequestAccessDenied:
        return _access_denied()
    except Exception:
        return _unavailable()
    return JSONResponse(
        {"requests": [_serialize_view(item) for item in requests]},
        headers=SECURITY_HEADERS,
    )


async def open_request(request: Request) -> Response:
    try:
        claims = await _claims(request)
        item = request.app.state.broker.get_request(claims, request.path_params["request_id"])
    except RequestAccessDenied:
        return _access_denied()
    except Exception:
        return _unavailable()
    return JSONResponse(_serialize_view(item), headers=SECURITY_HEADERS)


async def cancel_request(request: Request) -> Response:
    try:
        claims = await _claims(request)
        item = request.app.state.broker.cancel(claims, request.path_params["request_id"])
    except RequestAccessDenied:
        return _access_denied()
    except Exception:
        return _unavailable()
    return JSONResponse(_serialize_view(item), headers=SECURITY_HEADERS)


async def stream_request(request: Request) -> Response:
    try:
        claims = await _claims(request)
        request_id = request.path_params["request_id"]
        source = request.app.state.broker.open_source(claims, request_id)
        admission_limits = request.app.state.admission_limits
        if admission_limits is None:
            return _unavailable()
    except RequestAccessDenied:
        return _access_denied()
    except Exception:
        return _unavailable()

    return StreamingResponse(
        _framed_stream(
            broker=request.app.state.broker,
            claims=claims,
            request_id=request_id,
            source=source,
            admission_limits=admission_limits,
        ),
        media_type=STREAM_CONTENT_TYPE,
        headers=SECURITY_HEADERS,
    )


async def _claims(request: Request) -> ViewerClaims:
    return await request.app.state.authenticator.authenticate(request)


async def _framed_stream(
    *,
    broker: InProcessBroker,
    claims: ViewerClaims,
    request_id: str,
    source: ArrowBatchSource,
    admission_limits: ArrowAdmissionLimits,
) -> AsyncIterator[bytes]:
    """Frame Arrow chunks and omit completion unless the entire stream remains authorized."""

    yield STREAM_MAGIC
    try:
        async for chunk in admitted_ipc_chunks(source, admission_limits):
            if broker.open_source(claims, request_id) is not source:
                return
            yield FRAME_HEADER.pack(ARROW_FRAME, len(chunk))
            yield chunk
        if broker.open_source(claims, request_id) is not source:
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


def _access_denied() -> JSONResponse:
    return JSONResponse(
        {"error": "access_denied"},
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
    authenticator: ViewerAuthenticator | None = None,
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
    application.state.broker = broker or InProcessBroker()
    application.state.authenticator = authenticator or DenyAllViewerAuthenticator()
    application.state.admission_limits = admission_limits
    return application


app = create_app()
