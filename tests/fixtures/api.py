"""API test fixtures."""

from types import TracebackType
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Generator,
    Optional,
    Type,
    cast,
)

import pytest
import pytest_asyncio
from fastapi import FastAPI, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from httpx import ASGITransport, AsyncClient, Timeout
from starlette import status
from starlette.testclient import TestClient
from starlette.types import ASGIApp
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.middleware.correlation import CorrelationMiddleware
from app.middleware.errors import ErrorHandlingMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.middleware.security import SecurityHeadersMiddleware

# Default timeout configuration
DEFAULT_TIMEOUT: Timeout = Timeout(
    timeout=5.0,  # Default total timeout
    connect=2.0,  # Connection timeout
    read=5.0,  # Read timeout
    write=5.0,  # Write timeout
    pool=2.0,  # Pool timeout
)


@pytest.fixture(scope="function")
def test_app() -> FastAPI:
    """Get FastAPI test application.

    Returns:
        FastAPI application for testing
    """
    # Create a test app without startup handlers for basic endpoint tests
    test_app = FastAPI(
        title="Pantry Pirate Radio",
        description="Food security data aggregation system using HSDS",
        version="0.1.0",
        redirect_slashes=True,  # Enable automatic trailing slash redirection
    )

    # Add middleware in same order as main app
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
        allow_credentials=False,
    )
    test_app.add_middleware(SecurityHeadersMiddleware)
    test_app.add_middleware(CorrelationMiddleware)
    test_app.add_middleware(MetricsMiddleware)
    test_app.add_middleware(ErrorHandlingMiddleware)

    # Add metrics endpoint
    @test_app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Expose Prometheus metrics."""
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Add root redirect
    @test_app.get("/", include_in_schema=False)
    async def root_redirect() -> RedirectResponse:
        """Redirect root path to docs."""
        return RedirectResponse(
            url="/api/docs", status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    # Include v1 router with prefix
    # Temporarily unset TESTING environment variable to load API routes
    import os

    testing_env = os.environ.get("TESTING")
    if testing_env:
        del os.environ["TESTING"]

    from app.api.v1.router import router as v1_router
    from app.core.config import settings

    # Force import the individual routers for integration testing
    from app.api.v1.organizations import router as organizations_router
    from app.api.v1.locations import router as locations_router
    from app.api.v1.services import router as services_router
    from app.api.v1.service_at_location import router as service_at_location_router

    # Include individual routers directly
    test_app.include_router(organizations_router, prefix=settings.api_prefix)
    test_app.include_router(locations_router, prefix=settings.api_prefix)
    test_app.include_router(services_router, prefix=settings.api_prefix)
    test_app.include_router(service_at_location_router, prefix=settings.api_prefix)

    # Also include the main router for health checks
    test_app.include_router(v1_router, prefix=settings.api_prefix)

    # Restore TESTING environment variable
    if testing_env:
        os.environ["TESTING"] = testing_env
    return test_app


@pytest.fixture(scope="function")
def test_app_client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """Get FastAPI test client.

    Args:
        test_app: FastAPI application for testing

    Yields:
        Test client for making synchronous requests
    """
    with TestClient(test_app, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def test_app_async_client(
    test_app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    """Get FastAPI async test client.

    Args:
        test_app: FastAPI application for testing

    Yields:
        Test client for making asynchronous requests
    """
    transport = ASGITransport(app=cast(ASGIApp, test_app))
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
        timeout=DEFAULT_TIMEOUT,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def websocket_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Get FastAPI WebSocket test client.

    Args:
        test_app: FastAPI application for testing

    Yields:
        Test client configured for WebSocket testing
    """
    transport = ASGITransport(app=cast(ASGIApp, test_app))
    async with AsyncClient(
        transport=transport,
        base_url="ws://test",
        timeout=DEFAULT_TIMEOUT,
        headers={"Connection": "upgrade", "Upgrade": "websocket"},
    ) as client:
        yield client


class WebSocketTestSession:
    """WebSocket test session helper.

    Provides utilities for testing WebSocket connections with timeouts
    and connection management.
    """

    def __init__(self, websocket: WebSocket, timeout: float = 5.0) -> None:
        self.websocket = websocket
        self.timeout = timeout

    async def __aenter__(self) -> "WebSocketTestSession":
        await self.websocket.accept()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],  # noqa: vulture
        exc_val: Optional[BaseException],  # noqa: vulture
        exc_tb: Optional[TracebackType],  # noqa: vulture
    ) -> None:
        if self.websocket.client_state != WebSocketState.DISCONNECTED:
            await self.websocket.close()

    async def send_json(self, data: Dict[str, Any]) -> None:
        """Send JSON data with timeout.

        Args:
            data: JSON-serializable dictionary to send

        Raises:
            TimeoutError: If send operation times out
        """
        try:
            await self.websocket.send_json(data)
        except WebSocketDisconnect:
            raise TimeoutError("WebSocket send timeout")

    async def receive_json(self) -> Dict[str, Any]:
        """Receive JSON data with timeout.

        Returns:
            Received JSON data as dictionary

        Raises:
            TimeoutError: If receive operation times out
            TypeError: If received data is not a dictionary
        """
        try:
            json_data = await self.websocket.receive_json()
            if not isinstance(json_data, dict):
                raise TypeError("Expected dict from receive_json")
            return json_data
        except WebSocketDisconnect:
            raise TimeoutError("WebSocket receive timeout")
