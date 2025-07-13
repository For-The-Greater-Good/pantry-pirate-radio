"""Security headers middleware."""

from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Initialize middleware.

        Args:
        ----
            app: The ASGI application
        """
        super().__init__(app)
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000",
        }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Process the request/response cycle.

        Args:
        ----
            request: The incoming request
            call_next: The next handler in the middleware chain

        Returns:
        -------
            The response from downstream handlers
        """
        response = await call_next(request)

        # Add security headers
        for header_name, header_value in self.security_headers.items():
            response.headers[header_name] = header_value

        return response
