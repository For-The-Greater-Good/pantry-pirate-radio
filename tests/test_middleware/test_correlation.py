"""Correlation ID middleware tests."""

from typing import Any, AsyncGenerator, Awaitable, Callable, TypeVar, cast
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pytest import fixture, mark
from pytest_asyncio import fixture as asyncio_fixture

from app.middleware.correlation import CorrelationMiddleware

F = TypeVar("F", bound=Callable[..., Any])


@fixture  # type: ignore[misc]
def correlation_app() -> FastAPI:
    """Get test application with correlation ID middleware.

    Returns:
        FastAPI application for testing
    """
    app = FastAPI()

    @app.get("/test")  # type: ignore[misc]
    async def test_endpoint(request: Request) -> JSONResponse:
        """Test endpoint that returns correlation ID."""
        return JSONResponse({"correlation_id": request.state.correlation_id})

    app.add_middleware(CorrelationMiddleware)
    return app


@asyncio_fixture  # type: ignore[misc]
async def correlation_client(
    correlation_app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    """Get test client for correlation tests.

    Args:
        correlation_app: FastAPI application for testing

    Yields:
        Test client for making requests
    """
    transport = ASGITransport(
        app=cast(
            Callable[
                [
                    dict[str, Any],
                    Callable[[], Awaitable[dict[str, Any]]],
                    Callable[[dict[str, Any]], Awaitable[None]],
                ],
                Awaitable[None],
            ],
            correlation_app,
        )
    )
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client


@mark.asyncio  # type: ignore[misc]
async def test_correlation_id_generation(correlation_client: AsyncClient) -> None:
    """Test correlation ID is generated when not provided."""
    response = await correlation_client.get("/test")
    assert response.status_code == status.HTTP_200_OK
    assert "X-Request-ID" in response.headers

    # Verify UUID format
    correlation_id = response.headers["X-Request-ID"]
    assert UUID(correlation_id)

    # Verify ID in response body matches header
    assert response.json()["correlation_id"] == correlation_id


@mark.asyncio  # type: ignore[misc]
async def test_correlation_id_propagation(correlation_client: AsyncClient) -> None:
    """Test correlation ID is propagated when provided."""
    test_id = str(uuid4())
    response = await correlation_client.get(
        "/test",
        headers={"X-Request-ID": test_id},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["X-Request-ID"] == test_id
    assert response.json()["correlation_id"] == test_id


@mark.asyncio  # type: ignore[misc]
async def test_correlation_id_invalid(correlation_client: AsyncClient) -> None:
    """Test new correlation ID is generated when invalid ID provided."""
    invalid_id = "not-a-uuid"
    response = await correlation_client.get(
        "/test",
        headers={"X-Request-ID": invalid_id},
    )
    assert response.status_code == status.HTTP_200_OK

    # Verify new valid UUID was generated
    correlation_id = response.headers["X-Request-ID"]
    assert correlation_id != invalid_id
    assert UUID(correlation_id)
    assert response.json()["correlation_id"] == correlation_id
