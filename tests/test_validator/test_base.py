"""Tests for ValidationService base class."""

import logging
from unittest.mock import MagicMock, patch, call

import pytest
from sqlalchemy.orm import Session

from app.validator.base import ValidationService


class TestValidationServiceBase:
    """Test the ValidationService base class."""

    def test_validation_service_initialization(self, db_session: Session):
        """Test that ValidationService can be initialized with a database session."""
        service = ValidationService(db=db_session)

        assert service.db == db_session
        assert service.logger is not None
        assert isinstance(service.logger, logging.Logger)
        assert service.logger.name == "app.validator.base.ValidationService"

    def test_validation_service_context_manager(self, db_session: Session):
        """Test that ValidationService works as a context manager."""
        with ValidationService(db=db_session) as service:
            assert service is not None
            assert service.db == db_session

        # Should exit cleanly without errors

    def test_validation_service_inheritance_pattern(self, db_session: Session):
        """Test that ValidationService follows the same pattern as BaseReconciler."""
        from app.reconciler.base import BaseReconciler

        validator = ValidationService(db=db_session)
        reconciler = BaseReconciler(db=db_session)

        # Both should have similar attributes
        assert hasattr(validator, "db")
        assert hasattr(validator, "logger")
        assert hasattr(reconciler, "db")
        assert hasattr(reconciler, "logger")

        # Both should support context manager protocol
        assert hasattr(validator, "__enter__")
        assert hasattr(validator, "__exit__")
        assert hasattr(reconciler, "__enter__")
        assert hasattr(reconciler, "__exit__")

    def test_validation_service_passthrough_method(self, db_session: Session):
        """Test that ValidationService has a passthrough method that returns data unchanged."""
        service = ValidationService(db=db_session)

        test_data = {
            "organization": {
                "name": "Test Organization",
                "description": "Test description",
            },
            "locations": [{"latitude": 40.7128, "longitude": -74.0060}],
        }

        # Call the passthrough method
        result = service.validate(test_data)

        # Data should be returned unchanged
        assert result == test_data
        assert result is test_data  # Should be the same object reference

    def test_validation_service_with_job_result(
        self, db_session: Session, sample_hsds_job
    ):
        """Test that ValidationService can process a JobResult object."""
        service = ValidationService(db=db_session)

        # Process the job result
        result = service.process_job_result(sample_hsds_job)

        # Should return the same job result unchanged
        assert result == sample_hsds_job
        assert result.job_id == sample_hsds_job.job_id
        assert result.result.text == sample_hsds_job.result.text

    def test_validation_service_logging(self, db_session: Session, caplog):
        """Test that ValidationService logs data flow when configured."""
        with caplog.at_level(logging.INFO):
            service = ValidationService(db=db_session, log_data_flow=True)

            test_data = {"test": "data"}
            service.validate(test_data)

            # Should log the data flow
            assert "Validation service received data" in caplog.text
            assert "Validation service passing through data unchanged" in caplog.text

    def test_validation_service_without_logging(self, db_session: Session, caplog):
        """Test that ValidationService doesn't log when logging is disabled."""
        with caplog.at_level(logging.INFO):
            service = ValidationService(db=db_session, log_data_flow=False)

            test_data = {"test": "data"}
            service.validate(test_data)

            # Should not log the data flow
            assert "Validation service received data" not in caplog.text
            assert (
                "Validation service passing through data unchanged" not in caplog.text
            )

    def test_validation_service_configuration(
        self, db_session: Session, validator_config
    ):
        """Test that ValidationService respects configuration settings."""
        service = ValidationService(db=db_session, config=validator_config)

        assert service.enabled == validator_config["enabled"]
        assert service.queue_name == validator_config["queue_name"]
        assert service.redis_ttl == validator_config["redis_ttl"]
        assert service.log_data_flow == validator_config["log_data_flow"]

    def test_validation_service_disabled(
        self, db_session: Session, disabled_validator_config
    ):
        """Test that ValidationService can be disabled via configuration."""
        service = ValidationService(db=db_session, config=disabled_validator_config)

        assert service.enabled is False

        # When disabled, validate should still pass through data
        test_data = {"test": "data"}
        result = service.validate(test_data)
        assert result == test_data

    def test_validation_service_metadata_preservation(self, db_session: Session):
        """Test that ValidationService preserves all metadata from the original job."""
        service = ValidationService(db=db_session)

        # Create a job with metadata
        from app.llm.queue.models import JobResult, JobStatus, LLMJob
        from app.llm.providers.types import LLMResponse
        from datetime import datetime

        job = LLMJob(
            id="test-job",
            prompt="Test prompt",
            format={"type": "hsds"},
            provider_config={"temperature": 0.7},
            metadata={
                "content_hash": "xyz789",
                "source": "test_scraper",
                "scraper_run_id": "run-123",
                "original_url": "https://example.com",
            },
            created_at=datetime.now(),
        )

        response = LLMResponse(
            text='{"test": "data"}',
            model="test-model",
            usage={"total_tokens": 50},
            raw={"response_id": "resp-123"},
        )

        job_result = JobResult(
            job_id=job.id,
            job=job,
            status=JobStatus.COMPLETED,
            result=response,
            error=None,
            completed_at=datetime.now(),
            processing_time=2.0,
        )

        # Process the job result
        result = service.process_job_result(job_result)

        # All metadata should be preserved
        assert result.job.metadata == job.metadata
        assert result.job.metadata["content_hash"] == "xyz789"
        assert result.job.metadata["source"] == "test_scraper"
        assert result.job.metadata["scraper_run_id"] == "run-123"
        assert result.job.metadata["original_url"] == "https://example.com"
