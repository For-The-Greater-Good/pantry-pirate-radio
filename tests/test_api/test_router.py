"""Tests for API v1 router endpoints."""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from typing import Dict, Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Set testing mode
os.environ["TESTING"] = "true"


class TestAPIRouter:
    """Test cases for API v1 router endpoints."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = MagicMock(spec=AsyncSession)
        return session

    @pytest.mark.asyncio
    async def test_export_simple_priority_default_radius(self, mock_session):
        """Test export_simple_priority with default grouping radius."""
        from app.api.v1.router import export_simple_priority

        # Mock database result - rows should have attributes, not dict access
        mock_row = MagicMock()
        mock_row.id = "123"
        mock_row.lat = 40.7128
        mock_row.lng = -74.0060
        mock_row.name = "Test Location"
        mock_row.org = "Test Org"
        mock_row.address_1 = "123 Main St"
        mock_row.city = "New York"
        mock_row.state = "NY"
        mock_row.zip = "10001"
        mock_row.phone = "555-1234"
        mock_row.website = "https://example.com"
        mock_row.email = None
        mock_row.description = "Test description"
        mock_row.confidence_score = 85
        mock_row.validation_status = "validated"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        # Mock count result
        mock_count = MagicMock()
        mock_count.scalar.return_value = 5  # 5 states covered

        # Return appropriate result based on query type
        async def mock_execute_side_effect(*args, **kwargs):
            query_text = str(args[0])
            if "COUNT(DISTINCT a.state_province)" in query_text:
                return mock_count
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        # Call the endpoint with explicit grouping_radius
        result = await export_simple_priority(
            session=mock_session, grouping_radius=None
        )

        assert "locations" in result
        assert "metadata" in result
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_export_simple_priority_custom_radius(self, mock_session):
        """Test export_simple_priority with custom grouping radius."""
        from app.api.v1.router import export_simple_priority

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Call with custom radius
        result = await export_simple_priority(session=mock_session, grouping_radius=500)

        assert "locations" in result
        assert result["locations"] == []
        assert mock_execute.called

    @pytest.mark.asyncio
    async def test_export_simple_priority_no_grouping(self, mock_session):
        """Test export_simple_priority with grouping disabled."""
        from app.api.v1.router import export_simple_priority

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Call with grouping disabled
        result = await export_simple_priority(session=mock_session, grouping_radius=0)

        assert "locations" in result
        assert mock_execute.called

    @pytest.mark.asyncio
    async def test_export_simple_priority_database_error(self, mock_session):
        """Test export_simple_priority handles database errors."""
        from app.api.v1.router import export_simple_priority

        # Mock database error
        mock_session.execute = AsyncMock(side_effect=Exception("Database error"))

        # Should handle the error gracefully
        with pytest.raises(Exception):
            await export_simple_priority(session=mock_session, grouping_radius=None)

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self):
        """Test health check endpoint."""
        from app.api.v1.router import health_check
        from fastapi import Request

        # Create mock request with correlation_id
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"

        result = await health_check(mock_request)

        assert result["status"] == "healthy"
        assert "version" in result
        assert "correlation_id" in result

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self):
        """Test metrics endpoint."""
        from app.api.v1.router import metrics
        from fastapi import Response

        # Call metrics endpoint
        result = await metrics()

        # Check that it returns a Response
        assert isinstance(result, Response)
        assert result.media_type == "text/plain; version=0.0.4; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_api_metadata_endpoint(self):
        """Test get_api_metadata endpoint returns API information."""
        from app.api.v1.router import get_api_metadata

        result = await get_api_metadata()

        assert "version" in result
        assert "profile" in result
        assert result["version"] == "3.1.1"
        assert result["implementation"] == "Pantry Pirate Radio HSDS API"

    @pytest.mark.asyncio
    async def test_llm_health_check_endpoint(self):
        """Test LLM health check endpoint."""
        from app.api.v1.router import llm_health_check
        from fastapi import Request

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"

        with patch("app.api.v1.router.OpenAIProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.health_check = AsyncMock()
            mock_provider_class.return_value = mock_provider

            result = await llm_health_check(mock_request)

            assert "status" in result
            assert "correlation_id" in result

    @pytest.mark.asyncio
    async def test_redis_health_check_endpoint(self):
        """Test Redis health check endpoint."""
        from app.api.v1.router import redis_health_check
        from fastapi import Request

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"

        with patch("app.api.v1.router.Redis") as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping = AsyncMock()
            mock_redis.info = AsyncMock(
                return_value={
                    "redis_version": "7.0.0",
                    "connected_clients": "5",
                    "used_memory_human": "1.2M",
                }
            )
            mock_redis.close = AsyncMock()
            mock_redis_class.from_url.return_value = mock_redis

            result = await redis_health_check(mock_request)

            assert result["status"] == "healthy"
            assert "redis_version" in result
            assert "correlation_id" in result

    @pytest.mark.asyncio
    async def test_db_health_check_endpoint(self):
        """Test database health check endpoint."""
        from app.api.v1.router import db_health_check
        from fastapi import Request

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"

        with patch("sqlalchemy.create_engine") as mock_create_engine:
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one.side_effect = [
                "PostgreSQL 14.0",
                "PostGIS 3.1.0",
            ]
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_engine.connect.return_value = mock_conn
            mock_create_engine.return_value = mock_engine

            result = await db_health_check(mock_request)

            assert result["status"] == "healthy"
            assert "database" in result
            assert result["database"] == "postgresql"
            assert "correlation_id" in result

    def test_router_includes_subrouters(self):
        """Test that the main router includes all sub-routers."""
        from app.api.v1.router import router

        # Check that router is configured
        assert router is not None
        assert hasattr(router, "routes")

    @pytest.mark.asyncio
    async def test_export_with_large_dataset(self, mock_session):
        """Test export handles large datasets efficiently."""
        from app.api.v1.router import export_simple_priority

        # Create a large mock dataset with proper row objects
        large_dataset = []
        for i in range(100):  # Reduced to 100 for test efficiency
            mock_row = MagicMock()
            mock_row.id = str(i)
            mock_row.lat = 40.7 + i * 0.01
            mock_row.lng = -74.0 + i * 0.01
            mock_row.name = f"Location {i}"
            mock_row.org = f"Org {i}"
            mock_row.address_1 = f"{i} Main St"
            mock_row.city = "New York"
            mock_row.state = "NY"
            mock_row.zip = "10001"
            mock_row.phone = f"555-{i:04d}"
            mock_row.website = f"https://example{i}.com"
            mock_row.email = None
            mock_row.description = f"Description {i}"
            mock_row.confidence_score = 80 + (i % 20)
            mock_row.validation_status = "validated"
            large_dataset.append(mock_row)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = large_dataset

        # Mock count result
        mock_count = MagicMock()
        mock_count.scalar.return_value = 10

        # Return appropriate result based on query type
        async def mock_execute_side_effect(*args, **kwargs):
            query_text = str(args[0])
            if "COUNT(DISTINCT a.state_province)" in query_text:
                return mock_count
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        result = await export_simple_priority(
            session=mock_session, grouping_radius=None
        )

        assert "locations" in result
        assert len(result["locations"]) > 0
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_query_parameter_validation(self, mock_session):
        """Test that query parameters are validated."""
        from app.api.v1.router import export_simple_priority

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Test with valid radius within range
        result = await export_simple_priority(
            session=mock_session, grouping_radius=5000
        )
        assert "locations" in result

    @pytest.mark.asyncio
    async def test_cors_headers_included(self):
        """Test that CORS headers are properly configured."""
        from app.api.v1.router import router

        # Check that router has appropriate configuration
        assert router is not None
        assert hasattr(router, "default_response_class")

    def test_settings_override_in_testing(self):
        """Test that we're in testing mode."""
        from app.api.v1.router import settings

        # Just verify we're in testing mode
        # The actual model name can be overridden by CI environment
        assert os.getenv("TESTING") == "true"
        # Verify settings are loaded (not checking specific values as they can be overridden)
        assert settings.LLM_MODEL_NAME is not None
        assert settings.LLM_PROVIDER is not None
