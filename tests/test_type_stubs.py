"""Tests to verify type stub functionality."""

from typing import Any, Mapping, MutableMapping

import prometheus_client as prom
import structlog


def test_prometheus_counter() -> None:
    """Test prometheus Counter type hints."""
    counter = prom.Counter("test_counter", "Test counter help", labelnames=["label"])
    labeled_counter = counter.labels(label="value")
    labeled_counter.inc(1.0)
    labeled_counter.inc(amount=2.0)

    # Test with exemplar
    labeled_counter.inc(1.0, {"trace_id": "abc123"})


def test_prometheus_gauge() -> None:
    """Test prometheus Gauge type hints."""
    gauge = prom.Gauge("test_gauge", "Test gauge help", labelnames=["label"])
    labeled_gauge = gauge.labels(label="value")
    labeled_gauge.inc(1.0)
    labeled_gauge.dec(1.0)
    labeled_gauge.set(5.0)


def test_prometheus_histogram() -> None:
    """Test prometheus Histogram type hints."""
    histogram = prom.Histogram(
        "test_histogram",
        "Test histogram help",
        labelnames=["label"],
        buckets=[0.1, 1.0, 10.0],
    )
    labeled_histogram = histogram.labels(label="value")
    labeled_histogram.observe(1.5)
    labeled_histogram.observe(2.5)


def test_structlog_basic() -> None:
    """Test basic structlog functionality type hints."""
    logger = structlog.get_logger()
    logger = logger.bind(key="value")
    logger.info("test message")
    logger.error("error message", error="details")


def test_structlog_processors() -> None:
    """Test structlog processor type hints."""

    def custom_processor(
        logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> Mapping[str, Any]:
        event_dict["extra"] = "value"
        return event_dict

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            custom_processor,
            structlog.processors.JSONRenderer(),
        ]
    )


def test_structlog_stdlib() -> None:
    """Test structlog stdlib integration type hints."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level_number,
            structlog.stdlib.render_to_log_kwargs,
        ]
    )
