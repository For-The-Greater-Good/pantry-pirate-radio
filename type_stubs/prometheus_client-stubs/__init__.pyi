"""Type stubs for prometheus_client."""

from typing import Any

class Counter:
    """A counter metric."""

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
        namespace: str = "",
        subsystem: str = "",
        unit: str = "",
        registry: Any | None = None,
    ) -> None: ...
    def inc(self, amount: int | float = 1) -> None: ...
    def labels(self, *labelvalues: str, **labelkwargs: str) -> Counter: ...
