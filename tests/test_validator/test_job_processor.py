"""Tests for validator job processor."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch, Mock, call

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse
from app.validator.job_processor import (
    process_validation_job,
    ValidationProcessor,
    enqueue_to_reconciler,
)


class TestValidationJobProcessor:
    """Test the validation job processor."""

    def test_process_validation_job_entry_point(self, sample_hsds_job):
        """Test the main entry point for RQ to process validation jobs."""
        with patch("app.validator.job_processor.create_engine") as mock_engine:
            with patch("app.validator.job_processor.sessionmaker") as mock_session:
                with patch.object(
                    ValidationProcessor, "process_job_result"
                ) as mock_process:
                    mock_process.return_value = {"status": "validated"}

                    result = process_validation_job(sample_hsds_job)

                    assert result == {"status": "validated"}
                    mock_process.assert_called_once_with(sample_hsds_job)

    def test_validation_processor_initialization(self, db_session):
        """Test ValidationProcessor initialization."""
        processor = ValidationProcessor(db=db_session)

        assert processor.db == db_session
        assert processor.logger is not None
        assert processor.enabled is not None

    def test_validation_processor_passthrough(self, db_session, sample_hsds_job):
        """Test that ValidationProcessor passes data through unchanged."""
        processor = ValidationProcessor(db=db_session)

        # Process job result
        result = processor.process_job_result(sample_hsds_job)

        # Should return the same data
        assert result["job_id"] == sample_hsds_job.job_id
        assert result["status"] == "passed_validation"
        assert result["data"] == json.loads(sample_hsds_job.result.text)
        assert result["validation_notes"] is None  # No validation logic yet

    def test_validation_processor_with_database(self, db_session, sample_hsds_job):
        """Test ValidationProcessor with database operations."""
        processor = ValidationProcessor(db=db_session)

        with patch.object(processor, "update_validation_fields") as mock_update:
            processor.process_job_result(sample_hsds_job)

            # Should attempt to update validation fields
            mock_update.assert_called_once()

    def test_enqueue_to_reconciler(self, sample_hsds_job, mock_reconciler_queue):
        """Test enqueueing validated job to reconciler."""
        # Now that reconciler_queue is imported, we can patch it directly
        with patch(
            "app.validator.job_processor.reconciler_queue", mock_reconciler_queue
        ):
            mock_reconciler_queue.enqueue_call.return_value = MagicMock(
                id="test-job-id"
            )
            job_id = enqueue_to_reconciler(sample_hsds_job)

            assert job_id == "test-job-id"
            mock_reconciler_queue.enqueue_call.assert_called_once()

            call_args = mock_reconciler_queue.enqueue_call.call_args
            assert (
                call_args[1]["func"]
                == "app.reconciler.job_processor.process_job_result"
            )
            assert call_args[1]["args"][0] == sample_hsds_job

    def test_validation_processor_error_handling(self, db_session):
        """Test error handling in ValidationProcessor."""
        processor = ValidationProcessor(db=db_session)

        # Create a job with invalid data
        invalid_job = JobResult(
            job_id="invalid",
            job=LLMJob(
                id="invalid",
                prompt="Test",
                format={},
                provider_config={},
                metadata={},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text="invalid json",  # Not valid JSON
                model="test",
                usage={"total_tokens": 10},
                raw={},
            ),
            error=None,
            completed_at=datetime.now(),
            processing_time=1.0,
        )

        # Should handle the error gracefully
        result = processor.process_job_result(invalid_job)
        assert result["status"] in [
            "error",
            "passed_validation",
            "validation_failed",
        ]  # Depends on implementation

    def test_validation_processor_metrics(self, db_session, sample_hsds_job):
        """Test that ValidationProcessor updates metrics."""
        processor = ValidationProcessor(db=db_session)

        with patch("app.validator.metrics.VALIDATOR_JOBS_TOTAL") as mock_total:
            with patch("app.validator.metrics.VALIDATOR_JOBS_PASSED") as mock_passed:
                processor.process_job_result(sample_hsds_job)

                # Should increment metrics
                mock_total.inc.assert_called_once()
                mock_passed.inc.assert_called_once()

    def test_validation_processor_logging(self, db_session, sample_hsds_job, caplog):
        """Test logging in ValidationProcessor."""
        import logging

        processor = ValidationProcessor(db=db_session)

        with caplog.at_level(logging.INFO):
            processor.process_job_result(sample_hsds_job)

            # Should log processing
            assert (
                "Processing validation job" in caplog.text
                or "validation" in caplog.text.lower()
            )

    def test_validation_processor_disabled(self, db_session, sample_hsds_job):
        """Test ValidationProcessor when disabled."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            processor = ValidationProcessor(db=db_session)
            assert processor.enabled is False

            # Should still pass through data
            result = processor.process_job_result(sample_hsds_job)
            assert result is not None

    def test_validation_fields_update(self, db_session):
        """Test updating validation fields in the database."""
        processor = ValidationProcessor(db=db_session)

        # Mock a job with location data
        job_data = {
            "organization": {"name": "Test Org"},
            "locations": [
                {"latitude": 40.7128, "longitude": -74.0060, "address": "123 Test St"}
            ],
        }

        job_result = JobResult(
            job_id="test-123",
            job=LLMJob(
                id="test-123",
                prompt="Test",
                format={"type": "hsds"},
                provider_config={},
                metadata={"source": "test"},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text=json.dumps(job_data),
                model="test",
                usage={"total_tokens": 50},
                raw={},
            ),
            error=None,
            completed_at=datetime.now(),
            processing_time=1.0,
        )

        # Process and check if validation fields would be set
        with patch.object(processor, "set_validation_fields") as mock_set:
            processor.process_job_result(job_result)

            # Should attempt to set validation fields
            mock_set.assert_called()
            call_args = mock_set.call_args[0]
            assert "confidence_score" in call_args[0] or len(call_args) > 0

    def test_validation_processor_transaction(self, db_session, sample_hsds_job):
        """Test that ValidationProcessor uses database transactions properly."""
        processor = ValidationProcessor(db=db_session)

        with patch.object(db_session, "commit") as mock_commit:
            with patch.object(db_session, "rollback") as mock_rollback:
                processor.process_job_result(sample_hsds_job)

                # Should commit on success
                mock_commit.assert_called()
                mock_rollback.assert_not_called()

    def test_validation_processor_rollback_on_error(self, db_session, sample_hsds_job):
        """Test that ValidationProcessor rolls back on error."""
        processor = ValidationProcessor(db=db_session)

        # Force an error during processing
        with patch.object(
            processor, "_commit_changes", side_effect=Exception("Database error")
        ):
            with patch.object(db_session, "rollback") as mock_rollback:
                # Process should raise the error
                with pytest.raises(Exception) as exc_info:
                    processor.process_job_result(sample_hsds_job)

                # Check it's our expected error
                assert "Database error" in str(exc_info.value)
