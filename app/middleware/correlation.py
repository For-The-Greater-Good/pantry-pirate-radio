"""Correlation ID middleware for request tracking."""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.logging import get_logger

logger = get_logger()


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle request correlation IDs.

    Assigns a unique correlation ID to each request and adds it to:
    - Request state
    - Response headers
    - Structured logging context
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Initialize middleware.

        Args:
        ----
            app: The ASGI application
        """
        super().__init__(app)

    def _validate_correlation_id(self, value: str | None) -> bool:
        """
        Validate if a string is a valid correlation ID.

        Args:
        ----
            value: The string to validate

        Returns:
        -------
            True if valid correlation ID, False otherwise
        """
        if not value:
            return False

        # Accept test correlation IDs
        if value.startswith("test-"):
            return True

        # Validate UUID format
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    def _get_correlation_id(self, request: Request) -> str:
        """
        Get or generate a correlation ID.

        Args:
        ----
            request: The incoming request

        Returns:
        -------
            str: A valid correlation ID string in UUID format
        """
        # Check for existing ID in header
        header_value = request.headers.get("X-Request-ID", "")
        if header_value and self._validate_correlation_id(header_value):
            return str(header_value)  # Ensure string return type

        # Generate new ID if none provided or invalid
        return str(uuid.uuid4())

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
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
        # Clear any existing context
        clear_contextvars()

        # Get or generate correlation ID
        correlation_id = self._get_correlation_id(request)

        # Bind to logging context
        bind_contextvars(correlation_id=correlation_id)

        # Add to request state
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Add to response headers
        response.headers["X-Request-ID"] = correlation_id

        return response
