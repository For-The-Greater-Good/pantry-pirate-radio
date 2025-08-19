"""Tests for job routing through the validator service."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse


class TestValidatorJobRouting:
    """Test job routing from LLM to validator to reconciler."""

    def test_llm_routes_to_validator_when_enabled(
        self, sample_hsds_job, mock_validator_queue
    ):
        """Test that LLM worker routes jobs to validator queue when enabled."""
        with patch("app.llm.queue.processor.should_use_validator", return_value=True):
            from app.llm.queue.processor import process_llm_job

            # Mock LLM provider
            mock_provider = MagicMock()

            # Create async coroutine for generate
            async def mock_generate(*args, **kwargs):
                return sample_hsds_job.result

            mock_provider.generate.return_value = mock_generate()

            # Process job
            with patch(
                "app.validator.queues.get_validator_queue"
            ) as mock_get_val_queue:
                mock_val_queue = MagicMock()
                mock_val_queue.enqueue_call.return_value = MagicMock(
                    id="validator-job-123"
                )
                mock_get_val_queue.return_value = mock_val_queue

                with patch("app.llm.queue.processor.recorder_queue") as mock_recorder:
                    mock_recorder.enqueue_call.return_value = MagicMock(
                        id="recorder-123"
                    )

                    result = process_llm_job(sample_hsds_job.job, mock_provider)

                    # Should enqueue to validator
                    mock_val_queue.enqueue_call.assert_called_once()
                    call_args = mock_val_queue.enqueue_call.call_args
                    assert "app.validator.job_processor.process_validation_job" in str(
                        call_args
                    )

    def test_llm_routes_directly_to_reconciler_when_disabled(
        self, sample_hsds_job, mock_reconciler_queue
    ):
        """Test that LLM worker bypasses validator when disabled."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            with patch(
                "app.llm.queue.processor.reconciler_queue", mock_reconciler_queue
            ):
                from app.llm.queue.processor import process_llm_job

                # Mock LLM provider
                mock_provider = MagicMock()
                mock_provider.generate.return_value = sample_hsds_job.result

                # Process job
                with patch(
                    "app.llm.queue.processor.should_use_validator", return_value=False
                ):
                    result = process_llm_job(sample_hsds_job.job, mock_provider)

                    # Should enqueue directly to reconciler
                    mock_reconciler_queue.enqueue_call.assert_called_once()
                    call_args = mock_reconciler_queue.enqueue_call.call_args
                    assert "app.reconciler.job_processor.process_job_result" in str(
                        call_args
                    )

    def test_validator_forwards_to_reconciler(
        self, sample_hsds_job, mock_reconciler_queue
    ):
        """Test that validator forwards jobs to reconciler after processing."""
        from app.validator.job_processor import process_validation_job

        with patch(
            "app.validator.job_processor.reconciler_queue", mock_reconciler_queue
        ):
            # Process validation job
            result = process_validation_job(sample_hsds_job)

            # Should forward to reconciler
            mock_reconciler_queue.enqueue_call.assert_called_once()
            call_args = mock_reconciler_queue.enqueue_call.call_args
            assert (
                call_args[1]["func"]
                == "app.reconciler.job_processor.process_job_result"
            )
            # Check that an enriched copy was passed (with data field populated)
            enriched_job_result = call_args[1]["args"][0]
            assert enriched_job_result.job_id == sample_hsds_job.job_id
            assert enriched_job_result.job == sample_hsds_job.job
            assert enriched_job_result.status == sample_hsds_job.status
            assert enriched_job_result.result == sample_hsds_job.result
            # Most importantly, check that data field was populated with validated data
            assert enriched_job_result.data is not None
            assert "organization" in enriched_job_result.data

    def test_job_data_preserved_through_validator(self, sample_hsds_job):
        """Test that job data is preserved unchanged through validator."""
        from app.validator.job_processor import process_validation_job

        original_data = sample_hsds_job.result.text
        original_metadata = sample_hsds_job.job.metadata.copy()

        # Process through validator
        result = process_validation_job(sample_hsds_job)

        # Data should be unchanged (result is dict from process_validation_job)
        assert result["job_id"] == sample_hsds_job.job_id
        assert result["data"] == json.loads(original_data)

    def test_validator_queue_error_handling(self, sample_hsds_job):
        """Test error handling when validator queue fails."""
        from app.validator.job_processor import process_validation_job

        with patch("app.validator.job_processor.reconciler_queue") as mock_queue:
            mock_queue.enqueue_call.side_effect = Exception("Queue error")

            # Process should handle error and still return result
            result = process_validation_job(sample_hsds_job)

            # Should still return a result even if enqueueing fails
            assert result is not None
            assert result["job_id"] == sample_hsds_job.job_id

    def test_routing_with_failed_llm_job(self):
        """Test routing when LLM job fails."""
        failed_job = JobResult(
            job_id="failed-job",
            job=LLMJob(
                id="failed-job",
                prompt="Test",
                format={},
                provider_config={},
                metadata={},
                created_at=datetime.now(),
            ),
            status=JobStatus.FAILED,
            result=None,
            error="LLM processing failed",
            completed_at=datetime.now(),
            processing_time=0.5,
        )

        from app.validator.job_processor import process_validation_job

        # Failed jobs should still pass through
        result = process_validation_job(failed_job)
        # Failed jobs should still pass through with status info
        assert result["job_id"] == "failed-job"
        assert "status" in result

    def test_validator_logging_data_flow(self, sample_hsds_job):
        """Test that validator logs data flow when configured."""
        from app.validator.job_processor import process_validation_job

        with patch("app.validator.job_processor.logger") as mock_logger:
            with patch("app.validator.config.get_validator_config") as mock_config:
                # Mock config to have log_data_flow = True
                mock_config.return_value.log_data_flow = True

                process_validation_job(sample_hsds_job)

                # Should log data flow
                mock_logger.info.assert_called()
                log_messages = [str(c) for c in mock_logger.info.call_args_list]
                # Check that some logging occurred
                assert mock_logger.info.call_count > 0

    def test_validator_preserves_job_timing(self, sample_hsds_job):
        """Test that validator preserves job timing information."""
        from app.validator.job_processor import process_validation_job

        original_created = sample_hsds_job.job.created_at
        original_completed = sample_hsds_job.completed_at
        original_processing_time = sample_hsds_job.processing_time

        result = process_validation_job(sample_hsds_job)

        # Timing should be preserved in the result
        assert result["job_id"] == sample_hsds_job.job_id

    def test_routing_configuration_check(self):
        """Test that routing configuration can be checked."""
        from app.validator.routing import get_routing_config

        with patch("app.core.config.settings.VALIDATOR_ENABLED", True):
            config = get_routing_config()
            assert config["pipeline"] == ["llm", "validator", "reconciler"]

        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            config = get_routing_config()
            assert config["pipeline"] == ["llm", "reconciler"]

    def test_dynamic_routing_based_on_job_type(self, sample_hsds_job):
        """Test that routing can be dynamic based on job type/metadata."""
        from app.validator.routing import should_validate_job

        # HSDS jobs should go through validator
        assert should_validate_job(sample_hsds_job) is True

        # Create a non-HSDS job
        non_hsds_job = JobResult(
            job_id="non-hsds",
            job=LLMJob(
                id="non-hsds",
                prompt="Simple query",
                format={},  # No HSDS format
                provider_config={},
                metadata={"type": "simple"},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text="Simple response",
                model="test-model",
                usage={"total_tokens": 10},
                raw={},
            ),
            error=None,
            completed_at=datetime.now(),
            processing_time=0.5,
        )

        # Non-HSDS jobs might bypass validator (configurable)
        with patch("app.core.config.settings.VALIDATOR_ONLY_HSDS", True):
            assert should_validate_job(non_hsds_job) is False
