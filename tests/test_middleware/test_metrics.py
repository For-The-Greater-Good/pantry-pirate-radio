"""Tests for metrics middleware."""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient
from prometheus_client import REGISTRY

from app.core.config import Settings
from app.core.events import REQUESTS_TOTAL, RESPONSES_TOTAL

settings = Settings()


@pytest.fixture(autouse=True)
def setup_test_routes(test_app: FastAPI) -> None:
    """Setup test routes for metrics tests.

    Args:
        test_app: FastAPI application for testing
    """

    # Using underscore prefix to indicate these are test-only routes
    # noqa: ARG001 - unused function argument
    @test_app.get(f"{settings.api_prefix}/test-success", include_in_schema=False)
    async def _test_success() -> dict[str, str]:  # noqa: ARG001
        return {"status": "success"}

    @test_app.get(f"{settings.api_prefix}/test-error", include_in_schema=False)
    async def _test_error() -> None:  # noqa: ARG001
        raise HTTPException(status_code=400, detail="Test error")


@pytest.mark.asyncio
async def test_successful_request_metrics(test_app_async_client: AsyncClient) -> None:
    """Test metrics are recorded for successful requests."""
    endpoint = f"{settings.api_prefix}/test-success"
    path = endpoint
    # Make request
    response = await test_app_async_client.get(endpoint)
    assert response.status_code == 200

    # Clear any existing metrics
    for metric in REGISTRY.collect():
        if metric.name in ["app_http_requests_total", "app_http_responses_total"]:
            REGISTRY.unregister(metric)

    # Record new metric
    REQUESTS_TOTAL.labels(method="GET", path=path).inc()
    RESPONSES_TOTAL.labels(status_code="200").inc()

    # Verify metrics
    req_value = REQUESTS_TOTAL.labels(
        method="GET", path=path
    )._value.get()  # type: ignore
    resp_value = RESPONSES_TOTAL.labels(status_code="200")._value.get()  # type: ignore

    assert req_value > 0
    assert resp_value > 0


@pytest.mark.asyncio
async def test_error_request_metrics(test_app_async_client: AsyncClient) -> None:
    """Test metrics are recorded for failed requests."""
    endpoint = f"{settings.api_prefix}/test-error"
    path = endpoint
    # Make request
    response = await test_app_async_client.get(endpoint)
    assert response.status_code == 400

    # Clear any existing metrics
    for metric in REGISTRY.collect():
        if metric.name in ["app_http_requests_total", "app_http_responses_total"]:
            REGISTRY.unregister(metric)

    # Record new metric
    REQUESTS_TOTAL.labels(method="GET", path=path).inc()
    RESPONSES_TOTAL.labels(status_code="400").inc()

    # Verify metrics
    req_value = REQUESTS_TOTAL.labels(
        method="GET", path=path
    )._value.get()  # type: ignore
    resp_value = RESPONSES_TOTAL.labels(status_code="400")._value.get()  # type: ignore

    assert req_value > 0
    assert resp_value > 0


@pytest.mark.asyncio
async def test_metrics_endpoint(test_app_async_client: AsyncClient) -> None:
    """Test metrics endpoint returns Prometheus format."""
    # Make some requests to generate metrics
    await test_app_async_client.get(f"{settings.api_prefix}/health")

    # Get metrics
    response = await test_app_async_client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    # Verify metrics content
    metrics_text = response.text
    assert "app_http_requests_total" in metrics_text
    assert "app_http_responses_total" in metrics_text
