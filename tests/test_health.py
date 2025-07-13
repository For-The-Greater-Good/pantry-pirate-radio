"""Tests for health check endpoint."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.core.config import Settings

settings = Settings()


def test_health_check(test_app_client: TestClient) -> None:
    """Test synchronous health check endpoint."""
    response = test_app_client.get(f"{settings.api_prefix}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == settings.version
    assert "correlation_id" in data


@pytest.mark.asyncio
async def test_health_check_async(test_app_async_client: AsyncClient) -> None:
    """Test asynchronous health check endpoint."""
    response = await test_app_async_client.get(f"{settings.api_prefix}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == settings.version
    assert "correlation_id" in data
