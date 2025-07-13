"""API health check endpoint tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from redis.exceptions import RedisError

from app.core.config import Settings

# Mock environment variables for testing
settings = Settings(
    DATABASE_URL="postgresql://test:test@localhost:5432/test",
    REDIS_URL="redis://localhost:6379/0",
    LLM_MODEL_NAME="test-model",
    LLM_PROVIDER="openai",
)


@pytest.mark.asyncio
async def test_health_check(test_app_async_client: AsyncClient) -> None:
    """Test basic health check endpoint."""
    response = await test_app_async_client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == settings.version
    assert "correlation_id" in data


@pytest.mark.asyncio
@patch("app.llm.providers.openai.OpenAIProvider.health_check")
async def test_llm_health_check_success(
    mock_health_check: AsyncMock, test_app_async_client: AsyncClient
) -> None:
    """Test LLM health check when provider is healthy."""
    mock_health_check.return_value = True

    response = await test_app_async_client.get("/api/v1/health/llm")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["provider"] == "openai"
    assert data["model"] == "test-model"
    assert "correlation_id" in data


@pytest.mark.asyncio
@patch("app.llm.providers.openai.OpenAIProvider.health_check")
async def test_llm_health_check_failure(
    mock_health_check: AsyncMock, test_app_async_client: AsyncClient
) -> None:
    """Test LLM health check when provider is unhealthy."""
    mock_health_check.side_effect = Exception("Connection failed")

    response = await test_app_async_client.get("/api/v1/health/llm")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "error" in data
    assert "Connection failed" in data["error"]
    assert "correlation_id" in data


@pytest.mark.asyncio
@patch("redis.asyncio.Redis.close")
@patch("redis.asyncio.Redis.ping")
@patch("redis.asyncio.Redis.info")
async def test_redis_health_check_success(
    mock_info: AsyncMock,
    mock_ping: AsyncMock,
    mock_close: AsyncMock,
    test_app_async_client: AsyncClient,
) -> None:
    """Test Redis health check when connection is successful."""
    mock_ping.return_value = AsyncMock(return_value=True)()
    mock_info.return_value = AsyncMock(
        return_value={
            "redis_version": "7.0.0",
            "connected_clients": "1",
            "used_memory_human": "1.00M",
        }
    )()
    mock_close.return_value = AsyncMock(return_value=True)()

    response = await test_app_async_client.get("/api/v1/health/redis")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["redis_version"] == "7.0.0"
    assert data["connected_clients"] == "1"
    assert data["used_memory_human"] == "1.00M"
    assert "correlation_id" in data


@pytest.mark.asyncio
@patch("redis.asyncio.Redis.close")
@patch("redis.asyncio.Redis.ping")
async def test_redis_health_check_failure(
    mock_ping: AsyncMock,
    mock_close: AsyncMock,
    test_app_async_client: AsyncClient,
) -> None:
    """Test Redis health check when connection fails."""
    mock_ping.side_effect = RedisError("Connection refused")
    mock_close.return_value = AsyncMock(return_value=True)()

    response = await test_app_async_client.get("/api/v1/health/redis")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "error" in data
    assert "Connection refused" in data["error"]
    assert "correlation_id" in data


@pytest.mark.asyncio
async def test_db_health_check_success(test_app_async_client: AsyncClient) -> None:
    """Test database health check when connection is successful."""
    with patch("sqlalchemy.create_engine") as mock_create_engine:
        # Create mock connection
        mock_conn = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.scalar_one = MagicMock(return_value="PostgreSQL 14.5")
        mock_result2 = MagicMock()
        mock_result2.scalar_one = MagicMock(return_value="POSTGIS 3.2.1")
        mock_conn.execute = MagicMock(side_effect=[mock_result1, mock_result2])

        # Create mock engine with context manager
        mock_engine = MagicMock()

        # Create context manager for connect
        from contextlib import contextmanager

        @contextmanager
        def mock_connect():
            yield mock_conn

        mock_engine.connect = mock_connect
        mock_create_engine.return_value = mock_engine

        response = await test_app_async_client.get("/api/v1/health/db")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "postgresql"
        assert "version" in data
        assert "postgis_version" in data
        assert "correlation_id" in data
