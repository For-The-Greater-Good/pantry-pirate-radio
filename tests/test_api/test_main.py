"""Main FastAPI application tests."""

import pytest
from fastapi import status
from httpx import AsyncClient
from prometheus_client import CONTENT_TYPE_LATEST

from app.core.config import Settings

# Mock environment variables for testing
settings = Settings(
    DATABASE_URL="postgresql://test:test@localhost:5432/test",
    REDIS_URL="redis://localhost:6379/0",
    LLM_MODEL_NAME="test-model",
)


@pytest.mark.asyncio
async def test_app_initialization(test_app_async_client: AsyncClient) -> None:
    """Test FastAPI app initialization and configuration."""
    # Test app metadata
    response = await test_app_async_client.get("/openapi.json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["info"]["title"] == settings.app_name
    assert data["info"]["version"] == settings.version

    # Test docs endpoints
    docs_endpoints = ["/docs", "/redoc", "/openapi.json"]
    for endpoint in docs_endpoints:
        response = await test_app_async_client.get(endpoint)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_root_redirect(test_app_async_client: AsyncClient) -> None:
    """Test root endpoint redirects to docs."""
    response = await test_app_async_client.get("/", follow_redirects=False)
    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    assert response.headers["location"] == "/api/docs"


@pytest.mark.asyncio
async def test_metrics_endpoint(test_app_async_client: AsyncClient) -> None:
    """Test metrics endpoint returns Prometheus metrics."""
    response = await test_app_async_client.get("/metrics")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    assert len(response.text) > 0


@pytest.mark.asyncio
async def test_cors_middleware(test_app_async_client: AsyncClient) -> None:
    """Test CORS middleware configuration."""
    headers = {
        "Origin": "http://localhost:8000",
        "Access-Control-Request-Method": "GET",
    }
    response = await test_app_async_client.options("/api/v1/health", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:8000"
    assert "GET" in response.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_security_headers(test_app_async_client: AsyncClient) -> None:
    """Test security headers are present."""
    response = await test_app_async_client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    assert "x-content-type-options" in response.headers
    assert "x-frame-options" in response.headers
    assert "x-xss-protection" in response.headers


@pytest.mark.asyncio
async def test_correlation_middleware(test_app_async_client: AsyncClient) -> None:
    """Test correlation ID middleware."""
    response = await test_app_async_client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_metrics_middleware(test_app_async_client: AsyncClient) -> None:
    """Test metrics middleware updates counters."""
    # Make a request to increment metrics
    await test_app_async_client.get("/api/v1/health")

    # Check metrics have been updated
    response = await test_app_async_client.get("/metrics")
    assert response.status_code == status.HTTP_200_OK
    assert "app_http_requests_total" in response.text
    assert "app_http_responses_total" in response.text


@pytest.mark.asyncio
async def test_error_handling_middleware(test_app_async_client: AsyncClient) -> None:
    """Test error handling middleware formats errors correctly."""
    response = await test_app_async_client.get("/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert "error" in data
    assert "message" in data
    assert "correlation_id" in data
