"""Type stubs for FastAPI."""

from collections.abc import Callable
from typing import Any, TypeVar

from starlette.responses import Response

T = TypeVar("T")

class FastAPI:
    """FastAPI application class."""

    def __init__(
        self,
        *,
        debug: bool = False,
        title: str = "",
        description: str = "",
        version: str = "",
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
        openapi_url: str | None = "/openapi.json",
        root_path: str = "",
        root_path_in_servers: bool = True,
        default_response_class: type[Response] = Response,
    ) -> None: ...
    def add_middleware(self, middleware_class: type[Any], **options: Any) -> None: ...
    def add_event_handler(self, event_type: str, func: Callable[..., Any]) -> None: ...
    def include_router(self, router: Any, *, prefix: str = "") -> None: ...

class Request:
    """FastAPI request class."""

    method: str
    url: URL
    state: State

class URL:
    """URL components."""

    path: str

class State:
    """Request state."""

    correlation_id: str
