"""API metrics endpoint tests."""

import pytest
from httpx import AsyncClient
from prometheus_client.exposition import CONTENT_TYPE_LATEST


@pytest.mark.asyncio
async def test_metrics_content_type(test_app_async_client: AsyncClient) -> None:
    """Test metrics endpoint returns correct content type."""
    response = await test_app_async_client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


@pytest.mark.asyncio
async def test_metrics_format(test_app_async_client: AsyncClient) -> None:
    """Test metrics endpoint returns Prometheus format."""
    response = await test_app_async_client.get("/metrics")
    assert response.status_code == 200
    content = response.text

    # Basic Prometheus format checks
    assert "# HELP" in content  # Contains help text
    assert "# TYPE" in content  # Contains type information
    assert "responses_total" in content  # Contains our custom metric


@pytest.mark.asyncio
async def test_metrics_update(test_app_async_client: AsyncClient) -> None:
    """Test metrics are updated after requests."""
    # Get initial metric value
    response = await test_app_async_client.get("/metrics")
    initial_content = response.text

    # Make some requests to increment metrics
    await test_app_async_client.get("/v1/health")
    await test_app_async_client.get("/v1/health")

    # Get updated metrics
    response = await test_app_async_client.get("/metrics")
    updated_content = response.text

    # Verify metrics were updated
    assert initial_content != updated_content
    assert "responses_total" in updated_content


@pytest.mark.asyncio
async def test_metrics_labels(test_app_async_client: AsyncClient) -> None:
    """Test metrics include correct labels."""
    # Make a request to generate metrics
    await test_app_async_client.get("/v1/health")

    # Get metrics
    response = await test_app_async_client.get("/metrics")
    content = response.text

    # Check for status code label
    assert 'status_code="200"' in content


@pytest.mark.asyncio
async def test_invalid_method(test_app_async_client: AsyncClient) -> None:
    """Test metrics endpoint rejects invalid HTTP methods."""
    response = await test_app_async_client.post("/metrics")
    assert response.status_code == 405  # Method not allowed
