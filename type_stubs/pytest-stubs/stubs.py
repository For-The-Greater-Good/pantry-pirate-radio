"""Runtime implementation of pytest stubs."""

import sys
from typing import Any, cast

from . import (
    Config,
    FixtureRequest,
    Item,
    Mark,
    MarkDecorator,
    MarkGenerator,
    Module,
    fixture,
    mark,
)

# Export all types
__all__ = [
    "Config",
    "FixtureRequest",
    "Item",
    "Module",
    "Mark",
    "MarkDecorator",
    "MarkGenerator",
    "fixture",
    "mark",
]

# Make pytest importable
_module = sys.modules[__name__]
_package = cast(str, __package__)  # We know __package__ is a string here
for name in __all__:
    value: Any = getattr(sys.modules[_package], name)
    setattr(_module, name, value)
sys.modules["pytest"] = _module
