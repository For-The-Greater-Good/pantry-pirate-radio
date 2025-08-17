"""Metrics collection for validator service."""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Detect if we're in testing mode
TESTING = os.environ.get("TESTING", "false").lower() == "true"


# Define a test/dummy metric class that doesn't use Prometheus
class TestMetric:
    """Test metric that doesn't register with Prometheus."""

    def __init__(self, name=None, description=None, labels=None):
        self._name = name
        self._value = 0
        self._labels = labels or []

    def inc(self, amount=1):
        """Increment counter."""
        self._value += amount

    def dec(self, amount=1):
        """Decrement counter."""
        self._value -= amount

    def set(self, value):
        """Set gauge value."""
        self._value = value

    def observe(self, value):
        """Observe histogram value."""
        pass

    def info(self, value):
        """Set info value."""
        pass

    def labels(self, **kwargs):
        """Return self for chaining."""
        return self


# Initialize metric variables with proper types
VALIDATOR_JOBS_TOTAL: Any
VALIDATOR_JOBS_PASSED: Any
VALIDATOR_JOBS_FAILED: Any
VALIDATOR_PROCESSING_TIME: Any
VALIDATOR_QUEUE_SIZE: Any
VALIDATOR_ACTIVE_WORKERS: Any
VALIDATOR_INFO: Any
VALIDATOR_LOCATIONS_REJECTED: Any
VALIDATOR_REJECTION_RATE: Any
VALIDATOR_LOCATIONS_REJECTED_BY_REASON: Any
METRICS_AVAILABLE: bool

# Try to import and create metrics
try:
    from prometheus_client import (
        REGISTRY,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Info,
    )

    # Create dummy metrics for testing to avoid registration issues
    if TESTING:
        # Use test metrics when testing
        VALIDATOR_JOBS_TOTAL = TestMetric("validator_jobs_total")
        VALIDATOR_JOBS_PASSED = TestMetric("validator_jobs_passed")
        VALIDATOR_JOBS_FAILED = TestMetric("validator_jobs_failed")
        VALIDATOR_PROCESSING_TIME = TestMetric("validator_processing_seconds")
        VALIDATOR_QUEUE_SIZE = TestMetric("validator_queue_size")
        VALIDATOR_ACTIVE_WORKERS = TestMetric("validator_active_workers")
        VALIDATOR_INFO = TestMetric("validator_info")
        VALIDATOR_LOCATIONS_REJECTED = TestMetric("validator_locations_rejected_total")
        VALIDATOR_REJECTION_RATE = TestMetric("validator_rejection_rate")
        VALIDATOR_LOCATIONS_REJECTED_BY_REASON = TestMetric(
            "validator_locations_rejected_by_reason_total", labels=["reason"]
        )

    else:
        # Production mode - create real metrics
        # Function to safely get or create a metric
        def get_or_create_counter(name: str, description: str, labels=None):
            """Get existing counter from registry or create new one."""
            # Check if metric already exists
            for collector in list(REGISTRY._collector_to_names.keys()):
                if hasattr(collector, "_name") and collector._name == name:
                    return collector
            # Create new metric
            if labels:
                return Counter(name, description, labels)
            return Counter(name, description)

        def get_or_create_gauge(name: str, description: str):
            """Get existing gauge from registry or create new one."""
            # Check if metric already exists
            for collector in list(REGISTRY._collector_to_names.keys()):
                if hasattr(collector, "_name") and collector._name == name:
                    return collector
            # Create new metric
            return Gauge(name, description)

        def get_or_create_histogram(name: str, description: str, buckets=None):
            """Get existing histogram from registry or create new one."""
            # Check if metric already exists
            for collector in list(REGISTRY._collector_to_names.keys()):
                if hasattr(collector, "_name") and collector._name == name:
                    return collector
            # Create new metric
            if buckets:
                return Histogram(name, description, buckets=buckets)
            return Histogram(name, description)

        def get_or_create_info(name: str, description: str):
            """Get existing info from registry or create new one."""
            # Check if metric already exists
            for collector in list(REGISTRY._collector_to_names.keys()):
                if hasattr(collector, "_name") and collector._name == name:
                    return collector
            # Create new metric
            return Info(name, description)

        # Create all metrics using the safe functions
        VALIDATOR_JOBS_TOTAL = get_or_create_counter(
            "validator_jobs_total",
            "Total number of validation jobs processed",
        )

        VALIDATOR_JOBS_PASSED = get_or_create_counter(
            "validator_jobs_passed",
            "Number of validation jobs that passed",
        )

        VALIDATOR_JOBS_FAILED = get_or_create_counter(
            "validator_jobs_failed",
            "Number of validation jobs that failed",
        )

        VALIDATOR_PROCESSING_TIME = get_or_create_histogram(
            "validator_processing_seconds",
            "Time spent processing validation jobs",
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        VALIDATOR_QUEUE_SIZE = get_or_create_gauge(
            "validator_queue_size",
            "Number of jobs waiting in validation queue",
        )

        VALIDATOR_ACTIVE_WORKERS = get_or_create_gauge(
            "validator_active_workers",
            "Number of active validation workers",
        )

        VALIDATOR_INFO = get_or_create_info(
            "validator_info",
            "Validator service information",
        )

        # Rejection metrics
        VALIDATOR_LOCATIONS_REJECTED = get_or_create_counter(
            "validator_locations_rejected_total",
            "Total number of locations rejected by validator",
        )

        VALIDATOR_REJECTION_RATE = get_or_create_gauge(
            "validator_rejection_rate",
            "Percentage of locations rejected (0-100)",
        )

        VALIDATOR_LOCATIONS_REJECTED_BY_REASON = get_or_create_counter(
            "validator_locations_rejected_by_reason_total",
            "Number of locations rejected by reason",
            ["reason"],
        )

    METRICS_AVAILABLE = True

except ImportError:
    # Prometheus client not installed
    logger.warning("Prometheus client not installed, metrics disabled")
    METRICS_AVAILABLE = False

    # Use test metrics when prometheus_client is not available
    VALIDATOR_JOBS_TOTAL = TestMetric("validator_jobs_total")
    VALIDATOR_JOBS_PASSED = TestMetric("validator_jobs_passed")
    VALIDATOR_JOBS_FAILED = TestMetric("validator_jobs_failed")
    VALIDATOR_PROCESSING_TIME = TestMetric("validator_processing_seconds")
    VALIDATOR_QUEUE_SIZE = TestMetric("validator_queue_size")
    VALIDATOR_ACTIVE_WORKERS = TestMetric("validator_active_workers")
    VALIDATOR_INFO = TestMetric("validator_info")
    VALIDATOR_LOCATIONS_REJECTED = TestMetric("validator_locations_rejected_total")
    VALIDATOR_REJECTION_RATE = TestMetric("validator_rejection_rate")
    VALIDATOR_LOCATIONS_REJECTED_BY_REASON = TestMetric(
        "validator_locations_rejected_by_reason_total", labels=["reason"]
    )


def update_job_metrics(status: str) -> None:
    """Update job metrics based on validation status.

    Args:
        status: Job status (passed/failed)
    """
    if not METRICS_AVAILABLE:
        return

    VALIDATOR_JOBS_TOTAL.inc()
    if status == "passed":
        VALIDATOR_JOBS_PASSED.inc()
    else:
        VALIDATOR_JOBS_FAILED.inc()


def update_queue_metrics(queue_size: int, active_workers: int) -> None:
    """Update queue metrics.

    Args:
        queue_size: Current queue size
        active_workers: Number of active workers
    """
    if not METRICS_AVAILABLE:
        return

    VALIDATOR_QUEUE_SIZE.set(queue_size)
    VALIDATOR_ACTIVE_WORKERS.set(active_workers)


def update_info_metrics(version: str, enabled: bool) -> None:
    """Update service info metrics.

    Args:
        version: Service version
        enabled: Whether validation is enabled
    """
    if not METRICS_AVAILABLE:
        return

    VALIDATOR_INFO.info({"version": version, "enabled": str(enabled)})


def get_metrics() -> Optional[bytes]:
    """Get current metrics in Prometheus format.

    Returns:
        Metrics data or None if not available
    """
    if not METRICS_AVAILABLE or TESTING:
        return None

    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return generate_latest(REGISTRY)


def get_metrics_summary() -> Dict[str, Any]:
    """Get a summary of current metrics.

    Returns:
        Dictionary with metric summaries
    """
    if not METRICS_AVAILABLE:
        return {"metrics_available": False}

    # This would need actual metric collection logic
    # For now, return a placeholder
    return {
        "metrics_available": True,
        "jobs_total": 0,
        "jobs_passed": 0,
        "jobs_failed": 0,
        "queue_size": 0,
        "active_workers": 0,
        "locations_rejected": 0,
        "rejection_rate": 0.0,
    }
