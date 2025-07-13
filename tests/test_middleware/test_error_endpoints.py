"""Test error handling middleware."""

from typing import AsyncGenerator, Dict, cast

import pytest
import pytest_asyncio
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def error_app() -> FastAPI:
    """Create test app with error endpoints."""
    app = FastAPI()

    @app.get("/test")
    async def _test_endpoint() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/test-error")
    async def _error_endpoint() -> None:
        raise Exception("test error")

    @app.get("/test-value-error")
    async def _value_error_endpoint() -> None:
        raise ValueError("Invalid value")

    @app.get("/test-key-error")
    async def _key_error_endpoint() -> None:
        raise KeyError("Missing key")

    # Add middleware for testing
    from app.middleware.errors import ErrorHandlingMiddleware

    app.add_middleware(ErrorHandlingMiddleware)

    return app


@pytest_asyncio.fixture
async def error_client(error_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Get test client for error app."""
    transport = ASGITransport(
        app=error_app, client=cast(tuple[str, int], ("testserver", 80))
    )
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_success_endpoint(error_client: AsyncClient) -> None:
    """Test successful endpoint."""
    response = await error_client.get("/test")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_generic_error_endpoint(error_client: AsyncClient) -> None:
    """Test generic error handling."""
    response = await error_client.get("/test-error")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert data["error"] == "Exception"
    assert data["message"] == "test error"
    assert data["status_code"] == 500


@pytest.mark.asyncio
async def test_value_error_endpoint(error_client: AsyncClient) -> None:
    """Test ValueError handling."""
    response = await error_client.get("/test-value-error")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert data["error"] == "ValueError"
    assert data["message"] == "Invalid value"
    assert data["status_code"] == 422


@pytest.mark.asyncio
async def test_key_error_endpoint(error_client: AsyncClient) -> None:
    """Test KeyError handling."""
    response = await error_client.get("/test-key-error")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error"] == "KeyError"
    assert data["message"].strip("'") == "Missing key"
    assert data["status_code"] == 404
