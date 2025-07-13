"""Request metrics middleware for Prometheus monitoring."""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.core.events import REQUESTS_TOTAL, RESPONSES_TOTAL
from app.core.logging import get_logger

logger = get_logger()


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect request/response metrics.

    Records:
    - Total requests by method and path
    - Total responses by status code
    - Request duration histogram
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Initialize middleware.

        Args:
        ----
            app: The ASGI application
        """
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Process the request/response cycle and record metrics.

        Args:
        ----
            request: The incoming request
            call_next: The next handler in the middleware chain

        Returns:
        -------
            The response from downstream handlers
        """
        # Record request (ensure consistent path naming)
        path = str(request.url.path).rstrip("/")
        REQUESTS_TOTAL.labels(
            method=request.method,
            path=path,
        ).inc()

        try:
            # Process request and measure duration
            start_time = time.time()
            response = await call_next(request)
            duration = time.time() - start_time

            # Record response
            RESPONSES_TOTAL.labels(status_code=str(response.status_code)).inc()

            # Log request details
            logger.info(
                "request_processed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=duration,
            )

            return response

        except Exception as e:
            # Log error
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
            )
            raise
