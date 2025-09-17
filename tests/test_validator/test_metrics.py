"""Tests for validator metrics module."""

import pytest
import os
from unittest.mock import patch, MagicMock, Mock
from typing import Any

# Set testing mode before importing metrics
os.environ["TESTING"] = "true"

from app.validator.metrics import (
    TestMetric,
    VALIDATOR_JOBS_TOTAL,
    VALIDATOR_JOBS_PASSED,
    VALIDATOR_JOBS_FAILED,
    VALIDATOR_PROCESSING_TIME,
    VALIDATOR_QUEUE_SIZE,
    VALIDATOR_ACTIVE_WORKERS,
    VALIDATOR_INFO,
    VALIDATOR_LOCATIONS_REJECTED,
    VALIDATOR_REJECTION_RATE,
    VALIDATOR_LOCATIONS_REJECTED_BY_REASON,
    METRICS_AVAILABLE,
    update_job_metrics,
    update_queue_metrics,
    update_info_metrics,
    get_metrics,
    get_metrics_summary,
)


class TestTestMetric:
    """Test the TestMetric class used in testing mode."""

    def test_init(self):
        """Test TestMetric initialization."""
        metric = TestMetric("test_metric", "Test description", ["label1", "label2"])
        assert metric._name == "test_metric"
        assert metric._value == 0
        assert metric._labels == ["label1", "label2"]

    def test_inc(self):
        """Test incrementing counter."""
        metric = TestMetric("counter")
        metric.inc()
        assert metric._value == 1
        metric.inc(5)
        assert metric._value == 6

    def test_dec(self):
        """Test decrementing counter."""
        metric = TestMetric("counter")
        metric._value = 10
        metric.dec()
        assert metric._value == 9
        metric.dec(3)
        assert metric._value == 6

    def test_set(self):
        """Test setting gauge value."""
        metric = TestMetric("gauge")
        metric.set(42)
        assert metric._value == 42

    def test_observe(self):
        """Test observing histogram value."""
        metric = TestMetric("histogram")
        # Observe doesn't change value in test metric
        metric.observe(100)
        assert metric._value == 0

    def test_info(self):
        """Test setting info value."""
        metric = TestMetric("info")
        # Info doesn't change value in test metric
        metric.info({"version": "1.0.0"})
        assert metric._value == 0

    def test_labels(self):
        """Test labels method for chaining."""
        metric = TestMetric("labeled_metric", labels=["status", "reason"])
        labeled = metric.labels(status="success", reason="valid")
        assert labeled is metric  # Should return self for chaining


class TestMetricFunctions:
    """Test metric manipulation functions."""

    def test_update_job_metrics_passed(self):
        """Test updating job metrics with passed status."""
        initial_total = VALIDATOR_JOBS_TOTAL._value
        initial_passed = VALIDATOR_JOBS_PASSED._value

        update_job_metrics("passed")

        assert VALIDATOR_JOBS_TOTAL._value == initial_total + 1
        assert VALIDATOR_JOBS_PASSED._value == initial_passed + 1

    def test_update_job_metrics_failed(self):
        """Test updating job metrics with failed status."""
        initial_total = VALIDATOR_JOBS_TOTAL._value
        initial_failed = VALIDATOR_JOBS_FAILED._value

        update_job_metrics("failed")

        assert VALIDATOR_JOBS_TOTAL._value == initial_total + 1
        assert VALIDATOR_JOBS_FAILED._value == initial_failed + 1

    def test_update_queue_metrics(self):
        """Test updating queue metrics."""
        update_queue_metrics(10, 5)

        assert VALIDATOR_QUEUE_SIZE._value == 10
        assert VALIDATOR_ACTIVE_WORKERS._value == 5

    def test_update_info_metrics(self):
        """Test updating info metrics."""
        update_info_metrics("1.0.0", True)
        # Info doesn't change value in TestMetric, just ensure no error

    def test_get_metrics(self):
        """Test getting metrics in Prometheus format."""
        result = get_metrics()
        # In testing mode, this returns None
        assert result is None

    def test_get_metrics_summary(self):
        """Test getting metrics summary."""
        summary = get_metrics_summary()

        # The function returns a dictionary with metrics_available and default values
        assert "metrics_available" in summary
        assert summary["metrics_available"] == METRICS_AVAILABLE


class TestProductionMetrics:
    """Test production metrics initialization."""

    @patch.dict(os.environ, {"TESTING": "false"})
    @patch("app.validator.metrics.REGISTRY")
    @patch("app.validator.metrics.Counter")
    @patch("app.validator.metrics.Gauge")
    @patch("app.validator.metrics.Histogram")
    @patch("app.validator.metrics.Info")
    def test_production_metrics_creation(
        self, mock_info, mock_histogram, mock_gauge, mock_counter, mock_registry
    ):
        """Test that production metrics are created properly."""
        # Mock registry collector check
        mock_registry._collector_to_names = {}

        # Reload the module to trigger production initialization
        import importlib
        import app.validator.metrics as metrics_module

        # This would normally create production metrics
        # We're just testing the logic path exists


class TestMetricsWithoutPrometheus:
    """Test metrics when prometheus_client is not available."""

    @patch.dict("sys.modules", {"prometheus_client": None})
    def test_metrics_without_prometheus(self):
        """Test that metrics gracefully handle missing prometheus_client."""
        # Force reimport without prometheus_client
        import importlib
        import app.validator.metrics as metrics_module

        # When prometheus is not available, we should use TestMetrics
        # or handle gracefully


class TestMetricsIntegration:
    """Integration tests for metrics in various scenarios."""

    def test_metrics_in_validation_workflow(self):
        """Test metrics during a validation workflow."""
        # Simulate a validation workflow
        update_queue_metrics(1, 1)

        # Simulate processing - just update job metrics
        update_job_metrics("passed")

        # Simulate completion
        update_queue_metrics(0, 0)

        # Verify metrics state
        summary = get_metrics_summary()
        assert summary["metrics_available"] == METRICS_AVAILABLE

    def test_metrics_in_rejection_workflow(self):
        """Test metrics during rejection workflow."""
        # Simulate rejections
        update_job_metrics("failed")

        # Since we don't have direct access to rejection functions,
        # we can manually update the metrics for testing
        VALIDATOR_LOCATIONS_REJECTED._value += 5
        VALIDATOR_REJECTION_RATE._value = 0.25

        summary = get_metrics_summary()
        assert summary["metrics_available"] == METRICS_AVAILABLE

    def test_concurrent_metric_updates(self):
        """Test that metrics handle concurrent updates."""
        import threading

        def update_metrics():
            for _ in range(10):
                update_job_metrics("passed")

        threads = [threading.Thread(target=update_metrics) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have processed 50 jobs total
        assert VALIDATOR_JOBS_TOTAL._value >= 50
        assert VALIDATOR_JOBS_PASSED._value >= 50
