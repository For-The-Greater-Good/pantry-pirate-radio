"""CORS middleware scoped to Tightbeam write endpoints.

Global CORS allows only GET/HEAD/OPTIONS. This middleware adds
PUT/DELETE/POST handling for the /api/v1/tightbeam prefix so that
write-method CORS is scoped to the authenticated Tightbeam API.
Must be added as the outermost middleware (last ``add_middleware`` call)
so it intercepts preflight requests before the global CORSMiddleware.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_TIGHTBEAM_PREFIX = "/api/v1/tightbeam"
_WRITE_METHODS = "GET, HEAD, OPTIONS, PUT, DELETE, POST"


class TightbeamCORSMiddleware(BaseHTTPMiddleware):
    """Add write-method CORS headers exclusively for Tightbeam endpoints."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith(_TIGHTBEAM_PREFIX):
            return await call_next(request)

        origin = request.headers.get("origin", "")

        # Preflight: return full CORS response for tightbeam write methods
        if request.method == "OPTIONS":
            response = Response(status_code=200)
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = _WRITE_METHODS
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-Request-ID, X-Api-Key"
            )
            response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
            response.headers["Access-Control-Max-Age"] = "600"
            return response

        # Actual request: pass through, add method header to response
        response = await call_next(request)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = _WRITE_METHODS
        return response
