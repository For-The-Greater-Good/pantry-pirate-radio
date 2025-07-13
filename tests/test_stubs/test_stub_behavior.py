"""Tests to verify type stub behavior and inference."""

from typing import Dict

import pytest
from prometheus_client import Counter, Gauge
from structlog import get_logger
from structlog.types import BindableLogger


def test_counter_label_types() -> None:
    """Test Counter label type inference."""
    counter = Counter(
        name="test_counter_labels",
        documentation="Test counter",
        labelnames=["method", "path"],
    )

    # These should type check correctly
    counter.labels("GET", "/api")
    counter.labels(method="GET", path="/api")

    # These would fail type checking if run with mypy
    with pytest.raises(ValueError):
        counter.labels(123)  # type: ignore
    with pytest.raises(ValueError):
        counter.labels(path=123)  # type: ignore


def test_gauge_value_types() -> None:
    """Test Gauge value type inference."""
    gauge = Gauge(
        name="test_gauge_values",
        documentation="Test gauge",
    )

    # These should type check correctly
    gauge.set(42)
    gauge.set(3.14)
    gauge.inc(1)
    gauge.dec(0.5)

    # These would fail type checking if run with mypy
    with pytest.raises(ValueError):
        gauge.set("invalid")  # type: ignore
    with pytest.raises(TypeError):
        gauge.inc("invalid")  # type: ignore


def test_structlog_logger_binding() -> None:
    """Test structlog logger binding type inference."""
    logger = get_logger()

    # These should type check correctly
    bound_logger = logger.bind(request_id="123")
    assert isinstance(bound_logger, BindableLogger)

    # Test method chaining
    bound_logger.bind(user_id="456").info("test message")

    # Test with various value types
    context: Dict[str, str] = {"key": "value"}
    bound_logger.bind(**context).debug("test")


def test_structlog_logger_methods() -> None:
    """Test structlog logger method type inference."""
    logger = get_logger()

    # These should type check correctly
    logger.info("test message")
    logger.error("error message", error_code=500)
    logger.debug("debug message", data={"key": "value"})

    # Test with various argument types
    logger.info(
        "message",
        str_arg="string",
        int_arg=123,
        float_arg=3.14,
        dict_arg={"key": "value"},
        list_arg=[1, 2, 3],
    )


def test_prometheus_registry_types() -> None:
    """Test prometheus registry type inference."""
    from prometheus_client import REGISTRY

    # Create and test metrics with registry
    gauge = Gauge(
        name="test_gauge_registry_3",
        documentation="Test gauge",
        registry=REGISTRY,
    )
    gauge.set(42)
    assert gauge._value.get() == 42

    counter = Counter(
        name="test_counter_registry_3",
        documentation="Test counter",
        registry=REGISTRY,
    )
    counter.inc()
    assert counter._value.get() == 1
