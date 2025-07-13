"""pytest type stubs package."""

import sys
import types
from typing import Any, cast

from .stubs import (
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

# Create module instance
_module = cast(Any, types.ModuleType("pytest"))
_module.__dict__.update(
    {
        "Config": Config,
        "FixtureRequest": FixtureRequest,
        "Item": Item,
        "Module": Module,
        "Mark": Mark,
        "MarkDecorator": MarkDecorator,
        "MarkGenerator": MarkGenerator,
        "fixture": fixture,
        "mark": mark,
    }
)

sys.modules[__name__] = _module
sys.modules["pytest"] = _module

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

# Make exports available in this module
globals().update(_module.__dict__)
