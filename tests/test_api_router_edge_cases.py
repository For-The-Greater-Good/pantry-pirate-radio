"""Additional tests for API router edge cases."""

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.exc import OperationalError


class TestRouterEdgeCases:
    """Test edge cases and error paths in router."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request with correlation ID."""
        request = MagicMock(spec=Request)
        request.state.correlation_id = "test-correlation-id"
        return request

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TESTING": "true"}, clear=False)
    async def test_health_check_response(self, mock_request):
        """Test basic health check response."""
        from app.api.v1.router import health_check

        response = await health_check(mock_request)
        assert response["status"] == "healthy"
        assert response["correlation_id"] == "test-correlation-id"
        assert "version" in response

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TESTING": "true"}, clear=False)
    async def test_llm_health_check_unsupported_provider(self, mock_request):
        """Test LLM health check with unsupported provider."""
        with patch("app.api.v1.router.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "unsupported-provider"

            from app.api.v1.router import llm_health_check

            response = await llm_health_check(mock_request)

            assert response["status"] == "unhealthy"
            assert "Unsupported LLM provider" in response["error"]
            assert response["correlation_id"] == "test-correlation-id"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TESTING": "true"}, clear=False)
    async def test_llm_health_check_provider_failure(self, mock_request):
        """Test LLM health check when provider fails."""
        with patch("app.api.v1.router.settings") as mock_settings, patch(
            "app.api.v1.router.OpenAIProvider"
        ) as mock_provider_class:

            mock_settings.LLM_PROVIDER = "openai"
            mock_settings.LLM_MODEL_NAME = "test-model"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1000

            # Mock provider that raises exception on health check
            mock_provider = AsyncMock()
            mock_provider.health_check.side_effect = Exception(
                "Provider connection failed"
            )
            mock_provider_class.return_value = mock_provider

            from app.api.v1.router import llm_health_check

            response = await llm_health_check(mock_request)

            assert response["status"] == "unhealthy"
            assert response["error"] == "Provider connection failed"
            assert response["correlation_id"] == "test-correlation-id"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TESTING": "true"}, clear=False)
    async def test_redis_health_check_connection_failure(self, mock_request):
        """Test Redis health check when connection fails."""
        with patch("app.api.v1.router.Redis") as mock_redis_class:
            # Mock Redis instance that fails to ping
            mock_redis = AsyncMock()
            mock_redis.ping.side_effect = Exception("Redis connection failed")
            mock_redis_class.from_url.return_value = mock_redis

            from app.api.v1.router import redis_health_check

            response = await redis_health_check(mock_request)

            assert response["status"] == "unhealthy"
            assert response["error"] == "Redis connection failed"
            assert response["correlation_id"] == "test-correlation-id"

            # Verify Redis connection was closed
            mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TESTING": "true"}, clear=False)
    async def test_db_health_check_connection_failure(self, mock_request):
        """Test database health check when connection fails."""
        with patch("sqlalchemy.create_engine") as mock_create_engine:
            # Mock engine that fails to connect
            mock_engine = MagicMock()
            mock_engine.connect.side_effect = OperationalError(
                "Connection failed", None, None
            )
            mock_create_engine.return_value = mock_engine

            from app.api.v1.router import db_health_check

            response = await db_health_check(mock_request)

            assert response["status"] == "unhealthy"
            assert "Connection failed" in response["error"]
            assert response["correlation_id"] == "test-correlation-id"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TESTING": "true"}, clear=False)
    async def test_metrics_endpoint(self):
        """Test metrics endpoint returns proper response."""
        with patch("app.api.v1.router.generate_latest") as mock_generate:
            mock_generate.return_value = b'test_metric{label="value"} 1.0\n'

            from app.api.v1.router import metrics

            response = await metrics()

            assert response.status_code == 200
            assert "test_metric" in response.body.decode()
            assert response.media_type == "text/plain; version=0.0.4; charset=utf-8"
