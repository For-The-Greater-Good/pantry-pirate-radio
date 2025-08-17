"""Integration tests for data rejection pipeline."""

import os
import pytest
from unittest.mock import Mock, patch
from app.validator.job_processor import ValidationProcessor
from app.reconciler.job_processor import JobProcessor
from app.llm.queue.models import JobResult, JobStatus
from app.llm.queue.job import LLMJob
from app.llm.providers.types import LLMResponse


class TestRejectionPipelineIntegration:
    """Test end-to-end rejection pipeline from validator to reconciler."""

    @pytest.fixture
    def mock_validator_db(self):
        """Create mock database for validator."""
        db = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db

    @pytest.fixture
    def mock_reconciler_db(self):
        """Create mock database for reconciler."""
        db = Mock()
        db.execute = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        db.scalar = Mock()
        return db

    @pytest.fixture
    def job_with_mixed_quality_data(self):
        """Create job with mix of good and bad locations."""
        job = Mock(spec=LLMJob)
        job.id = "test-pipeline"
        job.type = "scraper"
        job.data = {}

        result = Mock(spec=LLMResponse)
        result.text = """{
            "organization": {
                "name": "Test Food Bank"
            },
            "locations": [
                {
                    "name": "Good Location",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "address": [{"street": "123 Broadway", "city": "New York", "state": "NY", "postal_code": "10001"}]
                },
                {
                    "name": "Zero Coordinates",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "address": [{"street": "Test St", "city": "Test City", "state": "XX"}]
                },
                {
                    "name": "Missing Coordinates",
                    "address": [{"street": "Unknown St", "city": "Nowhere"}]
                },
                {
                    "name": "Outside US",
                    "latitude": 51.5074,
                    "longitude": -0.1278,
                    "address": [{"street": "10 Downing St", "city": "London", "country": "UK"}]
                },
                {
                    "name": "Test Data Pattern",
                    "latitude": 40.0,
                    "longitude": -75.0,
                    "address": [{"street": "123 Main St", "city": "Anytown", "state": "PA", "postal_code": "00000"}]
                }
            ],
            "services": []
        }"""

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-pipeline"
        job_result.job = job
        job_result.result = result
        job_result.status = JobStatus.COMPLETED

        return job_result

    def test_validator_marks_bad_locations_as_rejected(
        self, mock_validator_db, job_with_mixed_quality_data
    ):
        """Test validator correctly marks low-quality locations as rejected."""
        processor = ValidationProcessor(db=mock_validator_db)

        # Skip enrichment for test
        with patch.object(processor, "_enrich_data", side_effect=lambda jr, data: data):
            result = processor.process_job_result(job_with_mixed_quality_data)

        locations = result["data"]["locations"]

        # Check each location's validation status
        good_loc = next(l for l in locations if l["name"] == "Good Location")
        assert good_loc["validation_status"] != "rejected"
        assert good_loc["confidence_score"] > 10

        zero_loc = next(l for l in locations if l["name"] == "Zero Coordinates")
        assert zero_loc["validation_status"] == "rejected"
        assert zero_loc["confidence_score"] == 0
        assert (
            zero_loc["validation_notes"]["rejection_reason"]
            == "Invalid 0,0 coordinates"
        )

        missing_loc = next(l for l in locations if l["name"] == "Missing Coordinates")
        assert missing_loc["validation_status"] == "rejected"
        assert missing_loc["confidence_score"] == 0
        assert (
            missing_loc["validation_notes"]["rejection_reason"]
            == "Missing coordinates after enrichment"
        )

        outside_us = next(l for l in locations if l["name"] == "Outside US")
        assert outside_us["validation_status"] == "rejected"
        assert outside_us["confidence_score"] < 10
        assert outside_us["validation_notes"]["rejection_reason"] == "Outside US bounds"

        test_data = next(l for l in locations if l["name"] == "Test Data Pattern")
        assert test_data["validation_status"] == "rejected"
        assert test_data["confidence_score"] < 10
        assert test_data["validation_notes"]["rejection_reason"] == "Test data detected"

    def test_reconciler_skips_rejected_locations(
        self, mock_reconciler_db, mock_validator_db, job_with_mixed_quality_data
    ):
        """Test reconciler skips locations marked as rejected by validator."""
        # First run through validator
        validator = ValidationProcessor(db=mock_validator_db)
        with patch.object(validator, "_enrich_data", side_effect=lambda jr, data: data):
            validated_result = validator.process_job_result(job_with_mixed_quality_data)

        # Update job with validated data
        job_with_mixed_quality_data.job.data = validated_result["data"]

        # Now run through reconciler
        reconciler = JobProcessor(db=mock_reconciler_db)

        created_locations = []

        def mock_create_location(**kwargs):
            created_locations.append(kwargs)
            return f"loc-{len(created_locations)}"

        with patch("app.reconciler.job_processor.OrganizationCreator"), patch(
            "app.reconciler.job_processor.LocationCreator"
        ) as MockLocCreator, patch(
            "app.reconciler.job_processor.ServiceCreator"
        ), patch(
            "app.reconciler.job_processor.VersionTracker"
        ):

            mock_loc_creator = Mock()
            MockLocCreator.return_value = mock_loc_creator
            mock_loc_creator.create_location.side_effect = mock_create_location

            reconciler.process_job_result(job_with_mixed_quality_data)

        # Only the good location should be created
        assert len(created_locations) == 1
        assert created_locations[0]["name"] == "Good Location"

        # Rejected locations should not be created
        created_names = [loc["name"] for loc in created_locations]
        assert "Zero Coordinates" not in created_names
        assert "Missing Coordinates" not in created_names
        assert "Outside US" not in created_names
        assert "Test Data Pattern" not in created_names

    def test_metrics_tracked_through_pipeline(
        self, mock_validator_db, job_with_mixed_quality_data
    ):
        """Test rejection metrics are properly tracked."""
        from app.validator.metrics import (
            VALIDATOR_LOCATIONS_REJECTED,
            VALIDATOR_REJECTION_RATE,
            VALIDATOR_LOCATIONS_REJECTED_BY_REASON,
        )

        # Mock the metrics
        with patch.object(
            VALIDATOR_LOCATIONS_REJECTED, "inc"
        ) as mock_rejected_inc, patch.object(
            VALIDATOR_REJECTION_RATE, "set"
        ) as mock_rate_set, patch.object(
            VALIDATOR_LOCATIONS_REJECTED_BY_REASON, "labels"
        ) as mock_reason_labels:

            mock_reason_counter = Mock()
            mock_reason_labels.return_value = mock_reason_counter

            processor = ValidationProcessor(db=mock_validator_db)
            with patch.object(
                processor, "_enrich_data", side_effect=lambda jr, data: data
            ):
                processor.process_job_result(job_with_mixed_quality_data)

            # Should track 4 rejections (all except Good Location)
            assert mock_rejected_inc.call_count == 4

            # Should set rejection rate (4/5 = 80%)
            mock_rate_set.assert_called_once()
            rate = mock_rate_set.call_args[0][0]
            assert rate == 80.0

            # Should track rejection reasons
            assert mock_reason_labels.call_count >= 4
            reason_calls = [
                call.kwargs["reason"]
                for call in mock_reason_labels.call_args_list
                if "reason" in call.kwargs
            ]

            # Check for various rejection reasons
            assert any("zero" in r or "invalid_0,0" in r for r in reason_calls)
            assert any("missing" in r for r in reason_calls)
            assert any("outside" in r or "bounds" in r for r in reason_calls)
            assert any("test" in r for r in reason_calls)

    @patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "20"})
    def test_custom_threshold_affects_pipeline(
        self, mock_validator_db, mock_reconciler_db
    ):
        """Test custom rejection threshold affects entire pipeline."""
        # Mock settings to use higher threshold
        with patch("app.core.config.settings.VALIDATION_REJECTION_THRESHOLD", 20):
            # Create job with borderline location (score 15)
            job = Mock(spec=LLMJob)
            job.data = {
                "locations": [
                    {
                        "name": "Borderline Location",
                        "latitude": 40.0,
                        "longitude": -75.0,
                        "address": [
                            {"street": "456 Oak St", "city": "Somewhere", "state": "PA"}
                        ],
                    }
                ]
            }

            job_result = Mock(spec=JobResult)
            job_result.job_id = "test-threshold"
            job_result.job = job
            job_result.result = Mock(text="")
            job_result.status = JobStatus.COMPLETED

            # Run through validator with custom threshold
            validator = ValidationProcessor(
                db=mock_validator_db, config={"rejection_threshold": 20}
            )

            # Mock scorer to return confidence of 15
            with patch("app.validator.job_processor.ConfidenceScorer") as MockScorer:
                mock_scorer = Mock()
                MockScorer.return_value = mock_scorer
                mock_scorer.calculate_score.return_value = 15
                mock_scorer.get_validation_status.side_effect = lambda s: (
                    "rejected" if s < 20 else "needs_review"
                )
                mock_scorer.score_organization.return_value = 15
                mock_scorer.score_service.return_value = 15
                mock_scorer.rejection_threshold = 20

                with patch.object(
                    validator, "_enrich_data", side_effect=lambda jr, data: data
                ):
                    result = validator.process_job_result(job_result)

            # With threshold of 20, score of 15 should be rejected
            location = result["data"]["locations"][0]
            assert location["confidence_score"] == 15
            assert location["validation_status"] == "rejected"

            # Update job with validated data
            job_result.job.data = result["data"]

            # Run through reconciler
            reconciler = JobProcessor(db=mock_reconciler_db)

            created_locations = []

            with patch("app.reconciler.job_processor.OrganizationCreator"), patch(
                "app.reconciler.job_processor.LocationCreator"
            ) as MockLocCreator, patch(
                "app.reconciler.job_processor.ServiceCreator"
            ), patch(
                "app.reconciler.job_processor.VersionTracker"
            ), patch(
                "app.reconciler.job_processor.settings.VALIDATION_REJECTION_THRESHOLD",
                20,
            ):

                mock_loc_creator = Mock()
                MockLocCreator.return_value = mock_loc_creator
                mock_loc_creator.create_location.side_effect = (
                    lambda **k: created_locations.append(k)
                )

                reconciler.process_job_result(job_result)

            # Location with score 15 should be rejected with threshold 20
            assert len(created_locations) == 0

    def test_rejection_logging_through_pipeline(
        self, mock_validator_db, mock_reconciler_db, job_with_mixed_quality_data, caplog
    ):
        """Test rejection reasons are properly logged throughout pipeline."""
        import logging

        # Run through validator
        validator = ValidationProcessor(db=mock_validator_db)
        with patch.object(validator, "_enrich_data", side_effect=lambda jr, data: data):
            with caplog.at_level(logging.INFO):
                validated_result = validator.process_job_result(
                    job_with_mixed_quality_data
                )

        # Check validator logs
        validator_logs = " ".join([r.message for r in caplog.records])
        assert "rejected" in validator_logs.lower()
        assert "Zero Coordinates" in validator_logs or "confidence=0" in validator_logs

        # Update job with validated data
        job_with_mixed_quality_data.job.data = validated_result["data"]

        # Run through reconciler
        reconciler = JobProcessor(db=mock_reconciler_db)

        with patch("app.reconciler.job_processor.OrganizationCreator"), patch(
            "app.reconciler.job_processor.LocationCreator"
        ), patch("app.reconciler.job_processor.ServiceCreator"), patch(
            "app.reconciler.job_processor.VersionTracker"
        ):

            with caplog.at_level(logging.WARNING):
                reconciler.process_job_result(job_with_mixed_quality_data)

        # Check reconciler logs
        reconciler_logs = " ".join(
            [r.message for r in caplog.records if r.levelname == "WARNING"]
        )
        assert "rejected" in reconciler_logs.lower()
        assert any(
            name in reconciler_logs
            for name in [
                "Zero Coordinates",
                "Missing Coordinates",
                "Outside US",
                "Test Data Pattern",
            ]
        )
