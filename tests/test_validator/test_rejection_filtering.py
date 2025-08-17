"""Tests for data filtering based on confidence thresholds."""

import os
import pytest
from unittest.mock import Mock, patch
from app.validator.scoring import ConfidenceScorer
from app.validator.job_processor import ValidationProcessor
from app.llm.queue.models import JobResult, JobStatus
from app.llm.queue.job import LLMJob
from app.llm.providers.types import LLMResponse


class TestThresholdConfiguration:
    """Test threshold configuration from environment and settings."""

    def test_default_threshold_is_10(self):
        """Test default rejection threshold is 10."""
        scorer = ConfidenceScorer()
        assert scorer.rejection_threshold == 10

    def test_threshold_from_config(self):
        """Test threshold can be set via config."""
        scorer = ConfidenceScorer(config={"rejection_threshold": 15})
        assert scorer.rejection_threshold == 15

    @patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "20"})
    def test_threshold_from_environment_variable(self):
        """Test threshold can be set via environment variable."""
        # Need to reload config to pick up env var
        with patch("app.core.config.settings.VALIDATION_REJECTION_THRESHOLD", 20):
            scorer = ConfidenceScorer()
            assert scorer.rejection_threshold == 20

    def test_get_validation_status_uses_threshold(self):
        """Test get_validation_status uses configured threshold."""
        # Test with default threshold (10)
        scorer = ConfidenceScorer()
        assert scorer.get_validation_status(9) == "rejected"
        assert scorer.get_validation_status(10) == "needs_review"
        assert scorer.get_validation_status(11) == "needs_review"

        # Test with custom threshold (15)
        scorer = ConfidenceScorer(config={"rejection_threshold": 15})
        assert scorer.get_validation_status(14) == "rejected"
        assert scorer.get_validation_status(15) == "needs_review"
        assert scorer.get_validation_status(16) == "needs_review"


class TestValidatorRejectionLogic:
    """Test validator marks locations as rejected based on threshold."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db

    @pytest.fixture
    def sample_job_result(self):
        """Create a sample job result with location data."""
        job = Mock(spec=LLMJob)
        job.id = "test-job-123"
        job.type = "scraper"
        job.data = {}

        result = Mock(spec=LLMResponse)
        result.text = """{
            "organization": {
                "name": "Test Org"
            },
            "locations": [
                {
                    "name": "Good Location",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "address": [{"street": "123 Real St", "city": "New York", "state": "NY", "postal_code": "10001"}]
                },
                {
                    "name": "Test Location",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "address": [{"street": "123 Test St", "city": "Anytown", "state": "XX", "postal_code": "00000"}]
                },
                {
                    "name": "Missing Coords",
                    "address": [{"street": "456 Unknown St", "city": "Nowhere", "state": "XX"}]
                }
            ],
            "services": []
        }"""

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-job-123"
        job_result.job = job
        job_result.result = result
        job_result.status = JobStatus.COMPLETED

        return job_result

    def test_validator_marks_low_confidence_as_rejected(
        self, mock_db, sample_job_result
    ):
        """Test validator marks locations with low confidence as rejected."""
        processor = ValidationProcessor(db=mock_db)

        # Mock enrichment to skip it
        with patch.object(processor, "_enrich_data", side_effect=lambda jr, data: data):
            result = processor.process_job_result(sample_job_result)

        # Check that low confidence locations are marked as rejected
        locations = result["data"]["locations"]

        # Good location should not be rejected
        good_loc = next(l for l in locations if l["name"] == "Good Location")
        assert good_loc["confidence_score"] > 10
        assert good_loc["validation_status"] != "rejected"

        # Test location (0,0 coords) should be rejected
        test_loc = next(l for l in locations if l["name"] == "Test Location")
        assert test_loc["confidence_score"] < 10
        assert test_loc["validation_status"] == "rejected"

        # Missing coords location should be rejected
        missing_loc = next(l for l in locations if l["name"] == "Missing Coords")
        assert missing_loc["confidence_score"] == 0
        assert missing_loc["validation_status"] == "rejected"

    def test_rejection_reasons_in_validation_notes(self, mock_db, sample_job_result):
        """Test rejection reasons are included in validation_notes."""
        processor = ValidationProcessor(db=mock_db)

        with patch.object(processor, "_enrich_data", side_effect=lambda jr, data: data):
            result = processor.process_job_result(sample_job_result)

        locations = result["data"]["locations"]

        # Test location should have rejection reason
        test_loc = next(l for l in locations if l["name"] == "Test Location")
        assert "validation_notes" in test_loc
        assert "rejection_reason" in test_loc["validation_notes"]
        assert test_loc["validation_notes"]["rejection_reason"] is not None

        # Missing coords should have specific rejection reason
        missing_loc = next(l for l in locations if l["name"] == "Missing Coords")
        assert (
            missing_loc["validation_notes"]["rejection_reason"]
            == "Missing coordinates after enrichment"
        )

    def test_custom_threshold_changes_rejection(self, mock_db, sample_job_result):
        """Test custom threshold changes what gets rejected."""
        # Create processor with higher threshold (50)
        processor = ValidationProcessor(db=mock_db, config={"rejection_threshold": 50})

        # Mock the scorer to use the custom threshold
        with patch("app.validator.job_processor.ConfidenceScorer") as MockScorer:
            mock_scorer = Mock()
            MockScorer.return_value = mock_scorer

            # Setup mock scorer to use threshold of 50
            mock_scorer.calculate_score.return_value = 45  # Below threshold
            mock_scorer.get_validation_status = lambda score: (
                "rejected" if score < 50 else "needs_review"
            )
            mock_scorer.score_organization.return_value = 45
            mock_scorer.score_service.return_value = 45

            with patch.object(
                processor, "_enrich_data", side_effect=lambda jr, data: data
            ):
                result = processor.process_job_result(sample_job_result)

            # With threshold of 50, even good locations might be rejected
            locations = result["data"]["locations"]
            for loc in locations:
                if loc["confidence_score"] < 50:
                    assert loc["validation_status"] == "rejected"


class TestRejectionTracking:
    """Test tracking of rejected locations."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db

    def test_validator_tracks_rejection_count(self, mock_db):
        """Test validator tracks count of rejected locations."""
        processor = ValidationProcessor(db=mock_db)

        # Create test data with multiple locations
        test_data = {
            "locations": [
                {
                    "name": "Rejected 1",
                    "confidence_score": 5,
                    "validation_status": "rejected",
                },
                {
                    "name": "Good 1",
                    "confidence_score": 80,
                    "validation_status": "verified",
                },
                {
                    "name": "Rejected 2",
                    "confidence_score": 3,
                    "validation_status": "rejected",
                },
                {
                    "name": "Review 1",
                    "confidence_score": 30,
                    "validation_status": "needs_review",
                },
                {
                    "name": "Rejected 3",
                    "confidence_score": 0,
                    "validation_status": "rejected",
                },
            ]
        }

        # Process the data
        validated_data = processor.validate_data(test_data)

        # Check validation errors includes rejections
        assert len(processor._validation_errors) == 3  # 3 rejected locations

        # Check each rejection is tracked
        rejection_errors = [e for e in processor._validation_errors if "rejected" in e]
        assert len(rejection_errors) == 3

    def test_rejection_summary_in_result(self, mock_db):
        """Test rejection summary is included in result."""
        processor = ValidationProcessor(db=mock_db)

        job = Mock(spec=LLMJob)
        job.id = "test-job"
        job.type = "scraper"

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-job"
        job_result.job = job
        job_result.data = {
            "locations": [
                {"name": "Rejected 1", "latitude": 0, "longitude": 0},
                {"name": "Good 1", "latitude": 40.7128, "longitude": -74.0060},
                {"name": "Rejected 2"},  # Missing coords
            ]
        }

        with patch.object(processor, "_enrich_data", side_effect=lambda jr, data: data):
            result = processor.process_job_result(job_result)

        # Check validation notes includes rejection summary
        assert "validation_notes" in result

        # Check for rejection information
        locations = result["data"]["locations"]
        rejected_count = sum(
            1 for l in locations if l.get("validation_status") == "rejected"
        )
        assert rejected_count >= 2  # At least 2 should be rejected


class TestEnvironmentVariableIntegration:
    """Test environment variable configuration works end-to-end."""

    @patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "25"}, clear=False)
    def test_env_var_affects_validation(self):
        """Test environment variable changes validation behavior."""
        # This test verifies the env var would be used if properly loaded
        # In practice, the settings module needs to be reloaded to pick up env changes

        # Mock the settings to simulate env var being loaded
        with patch("app.core.config.settings.VALIDATION_REJECTION_THRESHOLD", 25):
            scorer = ConfidenceScorer()

            # Score of 20 should be rejected with threshold of 25
            assert scorer.get_validation_status(20) == "rejected"
            assert scorer.get_validation_status(25) == "needs_review"
            assert scorer.get_validation_status(30) == "needs_review"
