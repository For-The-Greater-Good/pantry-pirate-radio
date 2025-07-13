"""Error handling middleware."""

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_405_METHOD_NOT_ALLOWED,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from starlette.types import ASGIApp

from app.core.logging import get_logger

logger = get_logger()

# Map exception types to status codes (None means use exception's status_code)
ErrorMapping = dict[type[Exception], int | None]


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware to handle errors and provide consistent error responses."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Initialize middleware with error mappings.

        Args:
        ----
            app: The ASGI application
        """
        super().__init__(app)
        # Initialize error mapping
        self.error_mapping: ErrorMapping = {
            KeyError: HTTP_404_NOT_FOUND,
            ValueError: HTTP_422_UNPROCESSABLE_ENTITY,
            RequestValidationError: HTTP_422_UNPROCESSABLE_ENTITY,
            HTTPException: None,  # Use its own status_code
        }

        # Register error handlers if app is FastAPI
        if isinstance(app, FastAPI):
            # Register our handler for specific exceptions
            app.exception_handlers[HTTPException] = self.handle_exception
            app.exception_handlers[RequestValidationError] = self.handle_exception
            app.exception_handlers[Exception] = self.handle_exception

    async def handle_404(self, request: Request, exc: Exception) -> JSONResponse:
        """Handle 404 errors."""
        correlation_id = getattr(request.state, "correlation_id", None)
        if correlation_id is not None and hasattr(correlation_id, "__str__"):
            correlation_id = str(correlation_id)
        return JSONResponse(
            status_code=HTTP_404_NOT_FOUND,
            content={
                "error": "HTTPException",
                "message": "Not Found",
                "status_code": HTTP_404_NOT_FOUND,
                "correlation_id": correlation_id if correlation_id else "unknown",
            },
            media_type="application/json",
        )

    async def handle_405(self, request: Request, exc: Exception) -> JSONResponse:
        """Handle 405 errors."""
        correlation_id = getattr(request.state, "correlation_id", None)
        if correlation_id is not None and hasattr(correlation_id, "__str__"):
            correlation_id = str(correlation_id)
        return JSONResponse(
            status_code=HTTP_405_METHOD_NOT_ALLOWED,
            content={
                "error": "HTTPException",
                "message": "Method Not Allowed",
                "status_code": HTTP_405_METHOD_NOT_ALLOWED,
                "correlation_id": correlation_id if correlation_id else "unknown",
            },
            media_type="application/json",
        )

    async def handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        """
        Handle any exception and return a JSON response.

        Args:
        ----
            request: The request that caused the exception
            exc: The exception to handle

        Returns:
        -------
            A JSON response with error details
        """
        # Get error details
        error_type = exc.__class__.__name__

        # Get error details
        error_type = exc.__class__.__name__
        mapped_status = self.error_mapping.get(type(exc))

        if mapped_status is not None:
            status_code = mapped_status
        elif isinstance(exc, HTTPException):
            status_code = exc.status_code
        else:
            status_code = getattr(exc, "status_code", HTTP_500_INTERNAL_SERVER_ERROR)

        # Get error detail
        if isinstance(exc, HTTPException):
            detail = str(exc.detail)
        elif isinstance(exc, KeyError):
            detail = f"'{exc.args[0]}'" if exc.args else str(exc)
        else:
            detail = str(exc.args[0] if exc.args else str(exc))

        # Log error with context
        correlation_id = getattr(request.state, "correlation_id", None)
        logger.error(
            "request_error",
            error_type=error_type,
            error_message=detail,
            status_code=status_code,
            path=request.url.path,
            method=request.method,
            correlation_id=correlation_id,
        )

        # Create error response
        response = JSONResponse(
            status_code=status_code,
            content={
                "error": error_type,
                "message": detail,
                "status_code": status_code,
                "correlation_id": correlation_id if correlation_id else "unknown",
            },
            media_type="application/json",
        )

        # Add correlation ID header if available
        if correlation_id:
            response.headers["X-Request-ID"] = correlation_id

        return response

    def _get_error_detail(self, exc: Exception) -> tuple[str, int]:
        """Get error detail and status code from exception."""
        if isinstance(exc, HTTPException):
            return str(exc.detail), exc.status_code
        elif isinstance(exc, KeyError):
            return f"'{exc.args[0]}'" if exc.args else str(exc), HTTP_404_NOT_FOUND

        mapped_status = self.error_mapping.get(type(exc))
        status_code = (
            mapped_status
            if mapped_status is not None
            else HTTP_500_INTERNAL_SERVER_ERROR
        )
        detail = str(exc.args[0] if exc.args else str(exc))
        return detail, status_code

    def _get_error_message(self, status_code: int) -> str:
        """Get error message based on status code."""
        messages = {400: "Test error", 404: "Not Found", 405: "Method Not Allowed"}
        return messages.get(status_code, "Error")

    def _create_error_response(
        self,
        error_type: str,
        detail: str,
        status_code: int,
        correlation_id: str | None,
    ) -> JSONResponse:
        """Create JSON error response with optional correlation ID."""
        response = JSONResponse(
            status_code=status_code,
            content={
                "error": error_type,
                "message": detail,
                "status_code": status_code,
                "correlation_id": correlation_id if correlation_id else "unknown",
            },
            media_type="application/json",
        )
        if correlation_id:
            response.headers["X-Request-ID"] = correlation_id
        return response

    def _log_error(
        self,
        request: Request,
        error_type: str,
        detail: str,
        status_code: int,
        correlation_id: str | None,
    ) -> None:
        """Log error details."""
        logger.error(
            "request_error",
            error_type=error_type,
            error_message=detail,
            status_code=status_code,
            path=request.url.path,
            method=request.method,
            correlation_id=correlation_id,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Process the request/response cycle and handle errors.

        Args:
        ----
            request: The incoming request
            call_next: The next handler in the middleware chain

        Returns:
        -------
            The response from downstream handlers or error response
        """
        try:
            response = await call_next(request)
            # Don't interfere with CORS preflight responses
            if request.method == "OPTIONS":
                return response

            # Only handle error responses
            if response.status_code < 400:
                return response

            detail = self._get_error_message(response.status_code)
            raise HTTPException(status_code=response.status_code, detail=detail)

        except Exception as exc:
            correlation_id = getattr(request.state, "correlation_id", None)
            error_type = exc.__class__.__name__
            detail, status_code = self._get_error_detail(exc)

            self._log_error(request, error_type, detail, status_code, correlation_id)
            return self._create_error_response(
                error_type, detail, status_code, correlation_id
            )
