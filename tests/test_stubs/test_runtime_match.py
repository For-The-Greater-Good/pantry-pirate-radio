"""Tests to verify type stubs match runtime behavior."""

import inspect
from typing import Iterable

import prometheus_client
import structlog
from prometheus_client import Counter, Gauge
from structlog.stdlib import BoundLogger


def test_prometheus_counter_signature() -> None:
    """Test Counter class signature matches stub."""
    runtime_params = inspect.signature(Counter.__init__).parameters
    assert "name" in runtime_params
    assert "documentation" in runtime_params
    assert "labelnames" in runtime_params
    assert runtime_params["labelnames"].annotation == Iterable[str]
    assert "namespace" in runtime_params
    assert runtime_params["namespace"].annotation == str
    assert runtime_params["namespace"].default == ""


def test_prometheus_gauge_signature() -> None:
    """Test Gauge class signature matches stub."""
    runtime_params = inspect.signature(Gauge.__init__).parameters
    assert "name" in runtime_params
    assert "documentation" in runtime_params
    assert "labelnames" in runtime_params
    assert runtime_params["labelnames"].annotation == Iterable[str]
    assert "namespace" in runtime_params
    assert runtime_params["namespace"].annotation == str
    assert runtime_params["namespace"].default == ""


def test_prometheus_gauge_methods() -> None:
    """Test Gauge methods match stub."""
    gauge = Gauge("test_gauge_methods", "Test gauge")
    assert hasattr(gauge, "inc")
    assert hasattr(gauge, "dec")
    assert hasattr(gauge, "set")
    assert hasattr(gauge, "set_to_current_time")

    # Test method signatures
    assert inspect.signature(gauge.inc).parameters["amount"].annotation == float
    assert inspect.signature(gauge.dec).parameters["amount"].annotation == float
    assert inspect.signature(gauge.set).parameters["value"].annotation == float


def test_structlog_boundlogger_signature() -> None:
    """Test BoundLogger class signature matches stub."""
    runtime_params = inspect.signature(BoundLogger.__init__).parameters
    assert "logger" in runtime_params
    assert "processors" in runtime_params
    assert "context" in runtime_params
    assert runtime_params["context"].annotation == "Context"


def test_structlog_boundlogger_methods() -> None:
    """Test BoundLogger methods match stub."""
    logger = structlog.get_logger()
    assert hasattr(logger, "debug")
    assert hasattr(logger, "info")
    assert hasattr(logger, "warning")
    assert hasattr(logger, "error")
    assert hasattr(logger, "critical")
    assert hasattr(logger, "bind")

    # Test method signatures
    assert "event" in inspect.signature(logger.info).parameters
    assert "event" in inspect.signature(logger.error).parameters
    assert inspect.signature(logger.bind).return_annotation == "BindableLogger"


def test_prometheus_registry() -> None:
    """Test REGISTRY attribute exists and has expected methods."""
    assert hasattr(prometheus_client, "REGISTRY")
    registry = prometheus_client.REGISTRY
    assert hasattr(registry, "get_sample_value")
