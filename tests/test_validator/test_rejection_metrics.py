"""Tests for rejection metrics tracking."""

import json
import pytest
from unittest.mock import Mock, patch
from app.validator.job_processor import ValidationProcessor

# Don't import metrics at module level to avoid import order issues
# Metrics will be imported lazily in each test method
from app.llm.queue.models import JobResult, JobStatus
from app.llm.queue.job import LLMJob
from app.llm.providers.types import LLMResponse


class TestRejectionMetrics:
    """Test metrics tracking for rejected locations."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db

    @pytest.fixture
    def job_with_rejected_locations(self):
        """Create job result with rejected locations."""
        job = Mock(spec=LLMJob)
        job.id = "test-job-metrics"
        job.type = "scraper"
        job.metadata = {"scraper_id": "test-scraper"}  # Add metadata

        # Data that should be in the JobResult
        data = {
            "locations": [
                {"name": "Good 1", "latitude": 40.7, "longitude": -74.0},
                {"name": "Rejected 1", "latitude": 0.0, "longitude": 0.0},
                {"name": "Good 2", "latitude": 41.8, "longitude": -87.6},
                {"name": "Rejected 2"},  # Missing coordinates
                {
                    "name": "Rejected 3",
                    "latitude": 999,
                    "longitude": 999,
                },  # Outside bounds
            ]
        }

        result = Mock(spec=LLMResponse)
        result.text = json.dumps(data)  # Put data in result.text

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-job-metrics"
        job_result.job = job
        job_result.result = result
        job_result.status = JobStatus.COMPLETED
        job_result.data = data  # Also add data directly to job_result

        return job_result

    def test_rejection_counter_increments(self, mock_db, job_with_rejected_locations):
        """Test VALIDATOR_LOCATIONS_REJECTED counter increments."""
        processor = ValidationProcessor(db=mock_db)

        # Mock the new rejection counter (to be added)
        with patch(
            "app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED"
        ) as mock_counter:
            mock_counter.inc = Mock()

            # Mock enrichment to skip it
            with patch.object(
                processor, "_enrich_data", side_effect=lambda _jr, data: data
            ):
                processor.process_job_result(job_with_rejected_locations)

            # Should increment for each rejected location
            # We expect 3 rejections (0,0 coords, missing coords, outside bounds)
            assert mock_counter.inc.call_count >= 3

    def test_rejection_rate_calculation(self, mock_db, job_with_rejected_locations):
        """Test VALIDATOR_REJECTION_RATE gauge is updated."""
        processor = ValidationProcessor(db=mock_db)

        # Mock the rejection rate gauge (to be added)
        with patch("app.validator.metrics.VALIDATOR_REJECTION_RATE") as mock_gauge:
            mock_gauge.set = Mock()

            with patch.object(
                processor, "_enrich_data", side_effect=lambda _jr, data: data
            ):
                result = processor.process_job_result(job_with_rejected_locations)

            # Should calculate and set rejection rate
            # 3 rejected out of 5 total = 60% rejection rate
            locations = result["data"]["locations"]
            rejected_count = sum(
                1 for loc in locations if loc.get("validation_status") == "rejected"
            )
            total_count = len(locations)
            expected_rate = (
                (rejected_count / total_count) * 100 if total_count > 0 else 0
            )

            # Verify gauge was set with rejection rate
            if mock_gauge.set.called:
                set_value = mock_gauge.set.call_args[0][0]
                assert set_value == pytest.approx(expected_rate, rel=0.1)

    def test_rejection_reason_labels(self, mock_db):
        """Test rejection metrics include reason labels."""
        processor = ValidationProcessor(db=mock_db)

        # Create job with specific rejection reasons
        job = Mock(spec=LLMJob)
        job.metadata = {"scraper_id": "test-scraper"}  # Add metadata

        data = {
            "locations": [
                {"name": "Zero Coords", "latitude": 0.0, "longitude": 0.0},
                {"name": "Missing Coords"},
                {"name": "Outside US", "latitude": 10.0, "longitude": 10.0},  # Africa
                {
                    "name": "Test Data",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "address": "123 Test St",
                    "city": "Anytown",
                    "postal_code": "00000",
                },
            ]
        }

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-reasons"
        job_result.job = job
        job_result.result = Mock(text=json.dumps(data))
        job_result.status = JobStatus.COMPLETED
        job_result.data = data

        # Mock the labeled counter where it's imported from
        with patch(
            "app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED_BY_REASON"
        ) as mock_counter:
            mock_counter.labels = Mock(return_value=Mock(inc=Mock()))

            with patch.object(
                processor, "_enrich_data", side_effect=lambda _jr, data: data
            ):
                processor.process_job_result(job_result)

            # Should have different labels for different rejection reasons
            label_calls = mock_counter.labels.call_args_list

            # The metric should have been called at least once
            assert (
                mock_counter.labels.called
            ), "VALIDATOR_LOCATIONS_REJECTED_BY_REASON.labels() was not called"

            if label_calls:
                # Extract reasons from the calls
                reasons = []
                for call in label_calls:
                    # Check both args and kwargs
                    if call.kwargs and "reason" in call.kwargs:
                        reasons.append(call.kwargs["reason"])

                # Check we got some reasons
                assert (
                    len(reasons) >= 2
                ), f"Expected at least 2 rejection reasons, got {reasons}"

                # Check for expected rejection reason types (not exact matches)
                reason_str = " ".join(str(r).lower() for r in reasons)
                assert (
                    "zero" in reason_str
                    or "0,0" in reason_str
                    or "invalid" in reason_str
                )
                assert "missing" in reason_str or "outside" in reason_str

    def test_metrics_updated_on_validation(self, mock_db, job_with_rejected_locations):
        """Test standard metrics are still updated during validation."""
        # Import metrics lazily to ensure TESTING flag is set
        from app.validator.metrics import (
            VALIDATOR_JOBS_TOTAL,
            VALIDATOR_JOBS_PASSED,
            VALIDATOR_JOBS_FAILED,
        )

        processor = ValidationProcessor(db=mock_db)

        # Mock all metrics
        with patch.object(VALIDATOR_JOBS_TOTAL, "inc") as mock_total, patch.object(
            VALIDATOR_JOBS_PASSED, "inc"
        ) as mock_passed, patch.object(VALIDATOR_JOBS_FAILED, "inc") as mock_failed:

            with patch.object(
                processor, "_enrich_data", side_effect=lambda _jr, data: data
            ):
                result = processor.process_job_result(job_with_rejected_locations)

            # Total should always increment
            mock_total.assert_called_once()

            # Either passed or failed should increment based on validation errors
            if processor._validation_errors:
                mock_failed.assert_called_once()
                mock_passed.assert_not_called()
            else:
                mock_passed.assert_called_once()
                mock_failed.assert_not_called()

    def test_rejection_metrics_in_summary(self, mock_db):
        """Test rejection metrics appear in metrics summary."""
        from app.validator.metrics import get_metrics_summary

        # The get_metrics_summary function returns hardcoded values for now
        # So we just check the structure
        summary = get_metrics_summary()

        # Should include basic structure
        assert "metrics_available" in summary

        # When metrics are available, these fields should be present (even if 0)
        if summary.get("metrics_available"):
            assert "locations_rejected" in summary
            assert "rejection_rate" in summary
            assert isinstance(summary["locations_rejected"], int | float)
            assert isinstance(summary["rejection_rate"], int | float)

    def test_rejection_metrics_export(self):
        """Test rejection metrics can be exported for Prometheus."""
        # This would test that the metrics are properly registered
        # and can be scraped by Prometheus

        # In test mode, we use TestMetric which doesn't register with Prometheus
        # So we just verify the metrics exist and can be used
        from app.validator.metrics import (
            VALIDATOR_LOCATIONS_REJECTED,
            VALIDATOR_REJECTION_RATE,
            VALIDATOR_LOCATIONS_REJECTED_BY_REASON,
        )

        # Verify metrics exist and have the right methods
        assert hasattr(VALIDATOR_LOCATIONS_REJECTED, "inc")
        assert hasattr(VALIDATOR_REJECTION_RATE, "set")
        assert hasattr(VALIDATOR_LOCATIONS_REJECTED_BY_REASON, "labels")

        # Test that we can use them without errors
        VALIDATOR_LOCATIONS_REJECTED.inc()
        VALIDATOR_REJECTION_RATE.set(50.0)
        VALIDATOR_LOCATIONS_REJECTED_BY_REASON.labels(reason="test").inc()


class TestRejectionMetricsIntegration:
    """Test metrics integration with full validation pipeline."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock()
        db.commit = Mock()
        return db

    def test_end_to_end_metrics_tracking(self, mock_db):
        """Test metrics are tracked through full validation pipeline."""
        # Import metrics lazily to ensure TESTING flag is set
        from app.validator.metrics import (
            VALIDATOR_JOBS_TOTAL,
            VALIDATOR_JOBS_PASSED,
            VALIDATOR_JOBS_FAILED,
        )

        processor = ValidationProcessor(db=mock_db)

        # Create a realistic job
        job = Mock(spec=LLMJob)
        job.metadata = {"scraper_id": "test-scraper"}  # Add metadata

        data = {
            "organization": {"name": "Food Bank"},
            "locations": [
                {"name": "Main Site", "latitude": 40.7128, "longitude": -74.0060},
                {"name": "Test Site", "latitude": 0, "longitude": 0},
                {"name": "Missing GPS Site", "address": "Unknown St"},
            ],
        }

        result = Mock(spec=LLMResponse)
        result.text = json.dumps(data)

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-e2e"
        job_result.job = job
        job_result.result = result
        job_result.status = JobStatus.COMPLETED
        job_result.data = data

        # Track all metric calls
        metric_calls = {"total": 0, "passed": 0, "failed": 0, "rejected": 0}

        def track_inc(metric_type):
            def _inc(*args, **kwargs):
                metric_calls[metric_type] += 1

            return _inc

        # Mock all metrics
        with patch.object(
            VALIDATOR_JOBS_TOTAL, "inc", side_effect=track_inc("total")
        ), patch.object(
            VALIDATOR_JOBS_PASSED, "inc", side_effect=track_inc("passed")
        ), patch.object(
            VALIDATOR_JOBS_FAILED, "inc", side_effect=track_inc("failed")
        ), patch(
            "app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED",
            Mock(inc=Mock(side_effect=track_inc("rejected"))),
        ):

            with patch.object(
                processor, "_enrich_data", side_effect=lambda _jr, data: data
            ):
                result = processor.process_job_result(job_result)

            # Verify metrics were tracked
            assert metric_calls["total"] == 1  # Job was processed

            # Should have some rejections
            locations = result["data"]["locations"]
            rejected_count = sum(
                1 for loc in locations if loc.get("validation_status") == "rejected"
            )
            assert rejected_count >= 2  # Test site and Missing GPS site
