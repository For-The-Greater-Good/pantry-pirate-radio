"""Tests for error handling middleware."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from httpx import AsyncClient
from starlette.datastructures import URL
from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from starlette.types import Message, Receive, Scope, Send

from app.middleware.errors import ErrorHandlingMiddleware


@pytest.fixture(autouse=True)
def setup_test_routes(test_app: FastAPI) -> None:
    """Setup test routes for error handling tests.

    Args:
        test_app: FastAPI application for testing
    """

    @test_app.get("/api/test-error")
    async def _error_endpoint() -> None:
        raise HTTPException(status_code=400, detail="Test error")

    @test_app.get("/api/test-value-error")
    async def _value_error_endpoint() -> None:
        raise ValueError("Invalid value")

    @test_app.get("/api/test-key-error")
    async def _key_error_endpoint() -> None:
        raise KeyError("Missing key")

    @test_app.get("/api/test-custom-error")
    async def _custom_error_endpoint() -> None:
        # This will result in a 500 since it's an unknown exception
        raise RuntimeError("Custom error")

    @test_app.get("/api/test-401")
    async def _test_401() -> Response:
        # Return a response with status code > 400
        return Response(status_code=401)


@pytest.mark.asyncio
async def test_http_exception_handling(test_app_async_client: AsyncClient) -> None:
    """Test handling of HTTPException."""
    response = await test_app_async_client.get("/api/test-error")
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "HTTPException"
    assert data["message"] == "Test error"
    assert data["status_code"] == 400


@pytest.mark.asyncio
async def test_value_error_handling(test_app_async_client: AsyncClient) -> None:
    """Test handling of ValueError."""
    response = await test_app_async_client.get("/api/test-value-error")
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "ValueError"
    assert data["message"] == "Invalid value"
    assert data["status_code"] == 422


@pytest.mark.asyncio
async def test_key_error_handling(test_app_async_client: AsyncClient) -> None:
    """Test handling of KeyError."""
    response = await test_app_async_client.get("/api/test-key-error")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "KeyError"
    assert data["message"] == "'Missing key'"
    assert data["status_code"] == 404


@pytest.mark.asyncio
async def test_unknown_exception_handling(test_app_async_client: AsyncClient) -> None:
    """Test handling of unknown exceptions."""
    response = await test_app_async_client.get("/api/test-custom-error")
    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "RuntimeError"
    assert data["message"] == "Custom error"
    assert data["status_code"] == 500


@pytest.mark.asyncio
async def test_exception_with_empty_args(test_app: FastAPI) -> None:
    """Test handling of exception with empty args."""
    middleware = ErrorHandlingMiddleware(test_app)
    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"
    mock_request.state.correlation_id = None

    class EmptyArgsError(Exception):
        args = ()

    exc = EmptyArgsError()
    response = await middleware.handle_exception(mock_request, exc)
    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    data = response.body.decode()
    assert str(exc) in data


@pytest.mark.asyncio
async def test_exception_with_none_args(test_app: FastAPI) -> None:
    """Test handling of exception with None args."""
    middleware = ErrorHandlingMiddleware(test_app)
    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"
    mock_request.state.correlation_id = None

    class NoneArgsError(Exception):
        def __init__(self) -> None:
            super().__init__()
            self.args = ()

    exc = NoneArgsError()
    response = await middleware.handle_exception(mock_request, exc)
    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    data = response.body.decode()
    assert str(exc) in data


@pytest.mark.asyncio
async def test_request_validation_error_handling(test_app: FastAPI) -> None:
    """Test handling of RequestValidationError."""
    middleware = ErrorHandlingMiddleware(test_app)
    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"
    mock_request.state.correlation_id = None

    exc = RequestValidationError(errors=[{"loc": ["body"], "msg": "Invalid value"}])
    response = await middleware.handle_exception(mock_request, exc)
    assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY
    data = response.body.decode()
    assert "RequestValidationError" in data


@pytest.mark.asyncio
async def test_exception_with_status_code(test_app: FastAPI) -> None:
    """Test handling of exception with status_code attribute."""
    middleware = ErrorHandlingMiddleware(test_app)
    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"
    mock_request.state.correlation_id = None

    class CustomError(Exception):
        status_code = 418

    exc = CustomError("I'm a teapot")
    response = await middleware.handle_exception(mock_request, exc)
    assert response.status_code == 418
    data = response.body.decode()
    assert "I'm a teapot" in data


@pytest.mark.asyncio
async def test_exception_without_args(test_app: FastAPI) -> None:
    """Test handling of exception without args."""
    middleware = ErrorHandlingMiddleware(test_app)
    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"
    mock_request.state.correlation_id = None

    exc = ValueError()
    response = await middleware.handle_exception(mock_request, exc)
    assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY
    data = response.body.decode()
    assert str(exc) in data


@pytest.mark.asyncio
async def test_key_error_without_args(test_app: FastAPI) -> None:
    """Test handling of KeyError without args."""
    middleware = ErrorHandlingMiddleware(test_app)
    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"
    mock_request.state.correlation_id = None

    exc = KeyError()
    response = await middleware.handle_exception(mock_request, exc)
    assert response.status_code == HTTP_404_NOT_FOUND
    data = response.body.decode()
    assert str(exc) in data


@pytest.mark.asyncio
async def test_correlation_id_in_error(test_app_async_client: AsyncClient) -> None:
    """Test correlation ID is included in error responses."""
    test_id = "test-correlation-id"
    response = await test_app_async_client.get(
        "/api/test-error",
        headers={"X-Request-ID": test_id},
    )
    assert response.status_code == 400
    assert response.headers["X-Request-ID"] == test_id


@pytest.mark.asyncio
async def test_handle_404(test_app_async_client: AsyncClient) -> None:
    """Test handling of 404 Not Found errors."""
    # Test nonexistent endpoint
    response = await test_app_async_client.get("/api/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "HTTPException"
    assert data["message"] == "Not Found"
    assert data["status_code"] == 404

    # Test handle_404 method directly
    middleware = ErrorHandlingMiddleware(FastAPI())
    mock_request = MagicMock(spec=Request)
    mock_exc = HTTPException(status_code=404)
    response = await middleware.handle_404(mock_request, mock_exc)
    assert response.status_code == 404
    data = response.body.decode()
    assert "Not Found" in data


@pytest.mark.asyncio
async def test_handle_405(test_app_async_client: AsyncClient) -> None:
    """Test handling of 405 Method Not Allowed errors."""
    # Test wrong method on endpoint
    response = await test_app_async_client.post("/api/test-error")
    assert response.status_code == 405
    data = response.json()
    assert data["error"] == "HTTPException"
    assert data["message"] == "Method Not Allowed"
    assert data["status_code"] == 405

    # Test handle_405 method directly
    middleware = ErrorHandlingMiddleware(FastAPI())
    mock_request = MagicMock(spec=Request)
    mock_exc = HTTPException(status_code=405)
    response = await middleware.handle_405(mock_request, mock_exc)
    assert response.status_code == 405
    data = response.body.decode()
    assert "Method Not Allowed" in data


@pytest.mark.asyncio
async def test_error_response_status(test_app_async_client: AsyncClient) -> None:
    """Test response handling when status code > 400."""
    response = await test_app_async_client.get("/api/test-401")
    assert response.status_code == 401
    data = response.json()
    # Default message for unknown status codes
    assert data["message"] == "Error"


def test_get_error_message() -> None:
    """Test _get_error_message method with different status codes."""
    middleware = ErrorHandlingMiddleware(FastAPI())

    assert middleware._get_error_message(400) == "Test error"
    assert middleware._get_error_message(404) == "Not Found"
    assert middleware._get_error_message(405) == "Method Not Allowed"
    assert middleware._get_error_message(500) == "Error"  # Default message
    assert middleware._get_error_message(418) == "Error"  # Unknown status code


def test_get_error_detail() -> None:
    """Test _get_error_detail method with different exceptions."""
    middleware = ErrorHandlingMiddleware(FastAPI())

    # Test HTTPException
    exc = HTTPException(status_code=400, detail="Test error")
    detail, status_code = middleware._get_error_detail(exc)
    assert detail == "Test error"
    assert status_code == 400

    # Test KeyError
    exc = KeyError("test_key")
    detail, status_code = middleware._get_error_detail(exc)
    assert detail == "'test_key'"
    assert status_code == 404

    # Test ValueError
    exc = ValueError("Invalid value")
    detail, status_code = middleware._get_error_detail(exc)
    assert detail == "Invalid value"
    assert status_code == 422

    # Test exception without args
    exc = ValueError()
    detail, status_code = middleware._get_error_detail(exc)
    assert detail == str(exc)
    assert status_code == 422

    # Test unknown exception
    exc = Exception("Unknown error")
    detail, status_code = middleware._get_error_detail(exc)
    assert detail == "Unknown error"
    assert status_code == 500


def test_create_error_response() -> None:
    """Test _create_error_response method."""
    middleware = ErrorHandlingMiddleware(FastAPI())

    # Test without correlation ID
    response = middleware._create_error_response(
        error_type="TestError",
        detail="Test message",
        status_code=400,
        correlation_id=None,
    )
    assert response.status_code == 400
    assert "X-Request-ID" not in response.headers
    data = response.body.decode()
    assert "TestError" in data
    assert "Test message" in data

    # Test with correlation ID
    response = middleware._create_error_response(
        error_type="TestError",
        detail="Test message",
        status_code=400,
        correlation_id="test-id",
    )
    assert response.status_code == 400
    assert response.headers["X-Request-ID"] == "test-id"


@patch("app.middleware.errors.logger")
def test_log_error(mock_logger: MagicMock) -> None:
    """Test _log_error method."""
    middleware = ErrorHandlingMiddleware(FastAPI())

    # Create mock request
    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"

    # Test logging with correlation ID
    middleware._log_error(
        request=mock_request,
        error_type="TestError",
        detail="Test message",
        status_code=400,
        correlation_id="test-id",
    )

    mock_logger.error.assert_called_once_with(
        "request_error",
        error_type="TestError",
        error_message="Test message",
        status_code=400,
        path="/api/test",
        method="GET",
        correlation_id="test-id",
    )


class MockApp:
    """Mock application for testing dispatch."""

    def __init__(self, status_code: int = 401) -> None:
        """Initialize mock app."""
        self.status_code = status_code

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Simulate ASGI application."""
        await send(
            {"type": "http.response.start", "status": self.status_code, "headers": []}
        )
        await send(
            {"type": "http.response.body", "body": b"Test response", "more_body": False}
        )


@pytest.mark.asyncio
async def test_dispatch() -> None:
    """Test dispatch method."""
    # Test response with status code > 400
    mock_app = MockApp(status_code=401)
    middleware = ErrorHandlingMiddleware(mock_app)

    mock_request = MagicMock(spec=Request)
    mock_request.url = URL("http://test.com/api/test")
    mock_request.method = "GET"
    mock_request.state.correlation_id = "test-id"
    mock_request.scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [],
    }

    messages = []

    async def mock_receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def mock_send(message: Message) -> None:
        messages.append(message)

    await middleware(mock_request.scope, mock_receive, mock_send)
    assert len(messages) == 2
    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 401
    assert messages[1]["type"] == "http.response.body"
    assert not messages[1].get("more_body", False)

    # Test successful response
    messages.clear()
    mock_app = MockApp(status_code=200)
    middleware = ErrorHandlingMiddleware(mock_app)
    await middleware(mock_request.scope, mock_receive, mock_send)
    assert len(messages) == 3
    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 200
    assert messages[1]["type"] == "http.response.body"
    assert messages[1]["more_body"] is True
    assert messages[2]["type"] == "http.response.body"
    assert not messages[2].get("more_body", False)
