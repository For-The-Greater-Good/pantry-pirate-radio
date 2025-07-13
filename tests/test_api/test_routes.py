"""API routes tests."""

import pytest
from fastapi import status
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_not_found(test_app_async_client: AsyncClient) -> None:
    """Test 404 response for non-existent endpoint."""
    response = await test_app_async_client.get("/api/v1/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error"] == "HTTPException"
    assert "not found" in data["message"].lower()


@pytest.mark.asyncio
async def test_invalid_version(test_app_async_client: AsyncClient) -> None:
    """Test invalid API version."""
    response = await test_app_async_client.get("/api/v2/health")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error"] == "HTTPException"
    assert "not found" in data["message"].lower()


@pytest.mark.asyncio
async def test_method_not_allowed(test_app_async_client: AsyncClient) -> None:
    """Test 405 response for invalid HTTP method."""
    response = await test_app_async_client.post("/api/v1/health")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    data = response.json()
    assert data["error"] == "HTTPException"
    assert "method not allowed" in data["message"].lower()


@pytest.mark.asyncio
async def test_root_redirect(test_app_async_client: AsyncClient) -> None:
    """Test root path redirects to docs."""
    response = await test_app_async_client.get("/", follow_redirects=False)
    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    assert response.headers["location"] == "/api/docs"


@pytest.mark.asyncio
async def test_trailing_slash(test_app_async_client: AsyncClient) -> None:
    """Test endpoints work with and without trailing slash."""
    base_paths = ["/api/v1/health", "/api/v1/metrics"]
    for base in base_paths:
        # Without slash
        response = await test_app_async_client.get(base)
        assert response.status_code == status.HTTP_200_OK

        # With slash
        response = await test_app_async_client.get(f"{base}/")
        assert response.status_code in (
            status.HTTP_200_OK,
            status.HTTP_307_TEMPORARY_REDIRECT,
        )


@pytest.mark.asyncio
async def test_api_version_prefix(test_app_async_client: AsyncClient) -> None:
    """Test API version prefix is required."""
    # Without version
    response = await test_app_async_client.get("/api/health")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # With version
    response = await test_app_async_client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
