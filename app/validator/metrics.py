"""Metrics for validator service."""

import logging
from typing import Optional, Dict, Any

try:
    from prometheus_client import Counter, Histogram, Gauge, Info

    # Define metrics
    VALIDATOR_JOBS_TOTAL = Counter(
        "validator_jobs_total",
        "Total number of validation jobs processed",
    )

    VALIDATOR_JOBS_PASSED = Counter(
        "validator_jobs_passed",
        "Number of validation jobs that passed",
    )

    VALIDATOR_JOBS_FAILED = Counter(
        "validator_jobs_failed",
        "Number of validation jobs that failed",
    )

    VALIDATOR_PROCESSING_TIME = Histogram(
        "validator_processing_time_seconds",
        "Time spent processing validation jobs",
        ["job_type"],
        buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    )

    VALIDATOR_QUEUE_SIZE = Gauge(
        "validator_queue_size", "Current size of the validation queue"
    )

    VALIDATOR_ACTIVE_WORKERS = Gauge(
        "validator_active_workers", "Number of active validation workers"
    )

    VALIDATOR_INFO = Info("validator_info", "Validator service information")

    # Rejection metrics
    VALIDATOR_LOCATIONS_REJECTED = Counter(
        "validator_locations_rejected_total",
        "Total number of locations rejected by validator",
    )

    VALIDATOR_REJECTION_RATE = Gauge(
        "validator_rejection_rate",
        "Percentage of locations rejected (0-100)",
    )

    VALIDATOR_LOCATIONS_REJECTED_BY_REASON = Counter(
        "validator_locations_rejected_by_reason_total",
        "Number of locations rejected by reason",
        ["reason"],
    )

    # Set initial info
    VALIDATOR_INFO.info(
        {
            "version": "1.0.0",
            "enabled": "true",
        }
    )

    METRICS_AVAILABLE = True

except ImportError:
    # Create mock metrics for when prometheus_client is not available
    class MockMetric:
        """Mock metric for when prometheus is not available."""

        def __init__(self, name: str):
            self.name = name
            self.logger = logging.getLogger(__name__)

        def inc(self, value: float = 1, **labels: Any) -> None:
            """Increment counter (no-op)."""
            self.logger.debug(f"Mock metric {self.name}.inc({value}, {labels})")

        def dec(self, value: float = 1, **labels: Any) -> None:
            """Decrement gauge (no-op)."""
            self.logger.debug(f"Mock metric {self.name}.dec({value}, {labels})")

        def set(self, value: float, **labels: Any) -> None:
            """Set gauge value (no-op)."""
            self.logger.debug(f"Mock metric {self.name}.set({value}, {labels})")

        def observe(self, value: float, **labels: Any) -> None:
            """Observe histogram value (no-op)."""
            self.logger.debug(f"Mock metric {self.name}.observe({value}, {labels})")

        def info(self, value: Dict[str, str]) -> None:
            """Set info value (no-op)."""
            self.logger.debug(f"Mock metric {self.name}.info({value})")

        def labels(self, **_labelkwargs: Any) -> "MockMetric":
            """Return self for label chaining."""
            return self

    # Create mock metrics
    VALIDATOR_JOBS_TOTAL = MockMetric("validator_jobs_total")  # type: ignore[assignment]
    VALIDATOR_JOBS_PASSED = MockMetric("validator_jobs_passed")  # type: ignore[assignment]
    VALIDATOR_JOBS_FAILED = MockMetric("validator_jobs_failed")  # type: ignore[assignment]
    VALIDATOR_PROCESSING_TIME = MockMetric("validator_processing_time_seconds")  # type: ignore[assignment]
    VALIDATOR_QUEUE_SIZE = MockMetric("validator_queue_size")  # type: ignore[assignment]
    VALIDATOR_ACTIVE_WORKERS = MockMetric("validator_active_workers")  # type: ignore[assignment]
    VALIDATOR_INFO = MockMetric("validator_info")  # type: ignore[assignment]
    VALIDATOR_LOCATIONS_REJECTED = MockMetric("validator_locations_rejected_total")  # type: ignore[assignment]
    VALIDATOR_REJECTION_RATE = MockMetric("validator_rejection_rate")  # type: ignore[assignment]
    VALIDATOR_LOCATIONS_REJECTED_BY_REASON = MockMetric("validator_locations_rejected_by_reason_total")  # type: ignore[assignment]

    METRICS_AVAILABLE = False

    logger = logging.getLogger(__name__)
    logger.debug("Prometheus metrics not available, using mock metrics")


def update_queue_metrics() -> None:
    """Update queue-related metrics."""
    if not METRICS_AVAILABLE:
        return

    try:
        from app.validator.queues import get_validator_queue

        queue = get_validator_queue()
        if queue:
            VALIDATOR_QUEUE_SIZE.set(len(queue))
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update queue metrics: {e}")


def update_worker_metrics(active_workers: int) -> None:
    """Update worker-related metrics.

    Args:
        active_workers: Number of currently active workers
    """
    if not METRICS_AVAILABLE:
        return

    VALIDATOR_ACTIVE_WORKERS.set(active_workers)


def record_job_processing(
    job_type: str,
    source: str,
    success: bool,
    processing_time: float,
    _failure_reason: Optional[str] = None,
) -> None:
    """Record metrics for a processed job.

    Args:
        job_type: Type of job processed
        source: Source of the job
        success: Whether processing was successful
        processing_time: Time taken to process (seconds)
        failure_reason: Reason for failure if not successful
    """
    if not METRICS_AVAILABLE:
        return

    # Increment total counter
    VALIDATOR_JOBS_TOTAL.inc()

    # Increment success/failure counter
    if success:
        VALIDATOR_JOBS_PASSED.inc()
    else:
        VALIDATOR_JOBS_FAILED.inc()

    # Record processing time
    VALIDATOR_PROCESSING_TIME.labels(job_type=job_type).observe(processing_time)


def get_metrics() -> Dict[str, Any]:
    """Get metrics for the validator service.

    Returns:
        Dictionary containing current metrics
    """
    return {
        "jobs_total": 0,  # Would be actual value in production
        "jobs_passed": 0,
        "jobs_failed": 0,
        "processing_time_avg": 0.0,
        "queue_size": 0,
    }


def get_metrics_summary() -> Dict[str, Any]:
    """Get a summary of current metrics.

    Returns:
        Dictionary containing metrics summary
    """
    summary: Dict[str, Any] = {
        "metrics_available": METRICS_AVAILABLE,
    }

    if METRICS_AVAILABLE:
        # In a real implementation, we would query the actual metric values
        # For now, return a placeholder
        summary.update(
            {
                "jobs_total": 0,
                "jobs_passed": 0,
                "jobs_failed": 0,
                "queue_size": 0,
                "active_workers": 0,
                "locations_rejected": 0,
                "rejection_rate": 0.0,
            }
        )

    return summary
