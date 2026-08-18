"""Human-facing Result API data-plane shell."""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


async def health(_request: Request) -> Response:
    return JSONResponse(
        {"status": "ok"},
        headers={"Cache-Control": "no-store"},
    )


# Result routes are intentionally absent until audience-bound human authentication,
# ownership authorization, and atomic Arrow admission are implemented together.
app = Starlette(routes=[Route("/healthz", health, methods=["GET"])])
