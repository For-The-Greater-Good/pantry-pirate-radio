"""API documentation endpoint tests."""

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_openapi_json(test_app_async_client: AsyncClient) -> None:
    """Test OpenAPI JSON schema endpoint."""
    response = await test_app_async_client.get("/openapi.json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data["openapi"].startswith("3.")  # OpenAPI version 3.x
    assert data["info"]["title"] == settings.app_name
    assert data["info"]["version"] == settings.version

    # Check core endpoints are documented
    paths = data["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/metrics" in paths


@pytest.mark.asyncio
async def test_docs_endpoint(test_app_async_client: AsyncClient) -> None:
    """Test Swagger UI docs endpoint."""
    response = await test_app_async_client.get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"

    content = response.text.lower()
    assert "swagger" in content
    assert "openapi" in content


@pytest.mark.asyncio
async def test_redoc_endpoint(test_app_async_client: AsyncClient) -> None:
    """Test ReDoc docs endpoint."""
    response = await test_app_async_client.get("/redoc")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"

    content = response.text.lower()
    assert "redoc" in content
    assert "openapi" in content


@pytest.mark.asyncio
async def test_docs_no_trailing_slash(test_app_async_client: AsyncClient) -> None:
    """Test docs endpoints work without trailing slash."""
    paths = ["/docs", "/redoc", "/openapi.json"]
    for path in paths:
        response = await test_app_async_client.get(path)
        assert response.status_code == 200

        # Test with trailing slash
        response = await test_app_async_client.get(f"{path}/")
        assert response.status_code in (200, 307)  # 307 is redirect


@pytest.mark.asyncio
async def test_docs_security(test_app_async_client: AsyncClient) -> None:
    """Test docs endpoints have proper security headers."""
    paths = ["/docs", "/redoc", "/openapi.json"]
    security_headers = ["x-content-type-options", "x-frame-options", "x-xss-protection"]

    for path in paths:
        response = await test_app_async_client.get(path)
        assert response.status_code == 200
        for header in security_headers:
            assert header in [h.lower() for h in response.headers]
