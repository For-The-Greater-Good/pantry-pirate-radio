"""WebSocket test fixtures."""

import asyncio
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    MutableMapping,
    Optional,
    Protocol,
    cast,
)

import pytest
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from httpx import AsyncClient, HTTPError
from starlette.types import Scope, Send
from starlette.websockets import WebSocketState

DEFAULT_WS_TIMEOUT = 5.0


class WebSocketInterface(Protocol):
    """Protocol for WebSocket interface."""

    async def send_json(self, data: Dict[str, Any]) -> None:
        """Send JSON data."""
        ...

    async def receive_json(self) -> Dict[str, Any]:
        """Receive JSON data."""
        ...

    async def close(self) -> None:
        """Close the connection."""
        ...

    @property
    def client_state(self) -> WebSocketState:
        """Get client state."""
        ...


@pytest.fixture(name="websocket_url")
def websocket_url_fixture() -> str:
    """Get WebSocket test URL.

    Returns:
        str: Base WebSocket URL for testing
    """
    return "ws://test/api"


async def receive() -> Dict[str, Any]:
    """Dummy receive function for WebSocket connection."""
    return {}


async def send(_message: MutableMapping[str, Any]) -> None:
    """Dummy send function for WebSocket connection."""
    pass


@asynccontextmanager
async def websocket_connect(
    client: AsyncClient,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_WS_TIMEOUT,
) -> AsyncGenerator[WebSocketInterface, None]:
    """Connect to WebSocket endpoint with timeout and error handling.

    Args:
        client: Async client for WebSocket connection
        path: WebSocket endpoint path
        headers: Optional request headers
        timeout: Connection timeout in seconds

    Yields:
        WebSocketInterface: Connected WebSocket client

    Raises:
        HTTPError: If connection fails
        TimeoutError: If connection times out
        WebSocketDisconnect: If connection is closed unexpectedly
    """
    ws: Optional[WebSocket] = None
    try:
        async with asyncio.timeout(timeout):
            # Create WebSocket connection
            scope = {
                "type": "websocket",
                "path": path,
                "headers": [
                    (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
                ],
            }
            ws = WebSocket(
                scope=cast(Scope, scope), receive=receive, send=cast(Send, send)
            )
            await ws.accept()
            yield cast(WebSocketInterface, ws)
    except TimeoutError:
        raise TimeoutError(f"WebSocket connection timed out after {timeout}s")
    except WebSocketDisconnect as e:
        # Re-raise with original code
        raise WebSocketDisconnect(code=e.code)
    except Exception as e:
        raise HTTPError(f"WebSocket connection failed: {str(e)}")
    finally:
        if ws and ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()


@pytest.fixture(name="ws_client")
async def ws_client_fixture(
    test_app: FastAPI,
    websocket_url: str,
) -> AsyncGenerator[AsyncClient, None]:
    """Get WebSocket test client with automatic cleanup.

    Args:
        test_app: FastAPI test application
        websocket_url: Base WebSocket URL

    Yields:
        AsyncClient: Configured WebSocket test client
    """
    async with AsyncClient(
        base_url=websocket_url,
        timeout=DEFAULT_WS_TIMEOUT,
        headers={"Connection": "upgrade", "Upgrade": "websocket"},
    ) as client:
        yield client


@pytest.fixture(name="ws_test_session")
async def ws_test_session_fixture(
    ws_client: AsyncClient,
    websocket_url: str,
) -> AsyncGenerator[WebSocketInterface, None]:
    """Get WebSocket test session with connection management.

    Args:
        ws_client: WebSocket test client
        websocket_url: Base WebSocket URL

    Yields:
        WebSocketInterface: Connected WebSocket session
    """
    async with websocket_connect(
        ws_client,
        f"{websocket_url}/ws/test",
        timeout=DEFAULT_WS_TIMEOUT,
    ) as websocket:
        yield websocket


class WebSocketWithJson:
    """WebSocket class with JSON helper methods."""

    def __init__(self, ws: WebSocketInterface) -> None:
        """Initialize enhanced WebSocket.

        Args:
            ws: Base WebSocket instance
        """
        self._ws = ws

    async def send_json_with_timeout(
        self, data: Dict[str, Any], timeout: float = DEFAULT_WS_TIMEOUT
    ) -> None:
        """Send JSON data with timeout.

        Args:
            data: JSON data to send
            timeout: Send timeout in seconds

        Raises:
            TimeoutError: If send operation times out
        """
        try:
            async with asyncio.timeout(timeout):
                await self._ws.send_json(data)
        except TimeoutError:
            raise TimeoutError(f"WebSocket send timed out after {timeout}s")

    async def receive_json_with_timeout(
        self, timeout: float = DEFAULT_WS_TIMEOUT
    ) -> Dict[str, Any]:
        """Receive JSON data with timeout.

        Args:
            timeout: Receive timeout in seconds

        Returns:
            Dict[str, Any]: Received JSON data

        Raises:
            TimeoutError: If receive operation times out
        """
        try:
            async with asyncio.timeout(timeout):
                json_data = await self._ws.receive_json()
                if not isinstance(json_data, dict):
                    raise TypeError("Expected dict from receive_json")
                return json_data
        except TimeoutError:
            raise TimeoutError(f"WebSocket receive timed out after {timeout}s")


@pytest.fixture(name="json_websocket")
async def json_websocket_fixture(
    ws_test_session: WebSocketInterface,
) -> AsyncGenerator[WebSocketWithJson, None]:
    """Get WebSocket fixture for JSON message testing.

    Args:
        ws_test_session: WebSocket test session

    Yields:
        WebSocketWithJson: Connected WebSocket with JSON helpers
    """
    yield WebSocketWithJson(ws_test_session)
