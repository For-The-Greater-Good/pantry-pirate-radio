"""Type stubs for pytest."""

from collections.abc import Callable, Iterator
from typing import Any, Literal, TypeVar, overload

_T = TypeVar("_T")

class Config:
    def addinivalue_line(self, name: str, line: str) -> None: ...
    option: Any
    pluginmanager: Any

class FixtureRequest:
    param: Any
    node: Any
    scope: str
    fixturename: str
    def getfixturevalue(self, name: str) -> Any: ...

class Item:
    name: str
    module: Any
    def add_marker(self, marker: MarkDecorator) -> None: ...
    def iter_markers(self) -> Iterator[Mark]: ...

class Module:
    __name__: str

class Mark:
    @property
    def name(self) -> str: ...
    @property
    def args(self) -> tuple[Any, ...]: ...
    @property
    def kwargs(self) -> dict[str, Any]: ...

class MarkDecorator:
    name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...

class MarkGenerator:
    serial: MarkDecorator
    concurrent: MarkDecorator
    asyncio: MarkDecorator
    parametrize: MarkDecorator
    def __getattr__(self, name: str) -> MarkDecorator: ...

mark: MarkGenerator

@overload
def fixture(
    callable: Callable[..., _T],
    *,
    scope: Literal["session", "module", "class", "function"] | None = None,
    params: Any | None = None,
    autouse: bool = False,
    ids: list[str] | Callable[[Any], str | None] | None = None,
    name: str | None = None,
) -> Callable[..., _T]: ...
@overload
def fixture(
    *,
    scope: Literal["session", "module", "class", "function"] | None = None,
    params: Any | None = None,
    autouse: bool = False,
    ids: list[str] | Callable[[Any], str | None] | None = None,
    name: str | None = None,
) -> Callable[[Callable[..., _T]], Callable[..., _T]]: ...
