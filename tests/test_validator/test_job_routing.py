"""Tests for job routing through the validator service."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse


class TestValidatorJobRouting:
    """Test job routing from LLM to validator to reconciler."""

    def test_llm_routes_to_validator_when_enabled(self, sample_hsds_job, mock_validator_queue):
        """Test that LLM worker routes jobs to validator queue when enabled."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", True):
            with patch("app.llm.queue.processor.validator_queue", mock_validator_queue):
                from app.llm.queue.processor import process_llm_job
                
                # Mock LLM provider
                mock_provider = MagicMock()
                mock_provider.generate.return_value = sample_hsds_job.result
                
                # Process job
                with patch("app.llm.queue.processor.enqueue_to_validator") as mock_enqueue:
                    mock_enqueue.return_value = "validator-job-123"
                    
                    result = process_llm_job(sample_hsds_job.job, mock_provider)
                    
                    # Should enqueue to validator
                    mock_enqueue.assert_called_once()
                    call_args = mock_enqueue.call_args[0]
                    assert isinstance(call_args[0], JobResult)

    def test_llm_routes_directly_to_reconciler_when_disabled(
        self, sample_hsds_job, mock_reconciler_queue
    ):
        """Test that LLM worker bypasses validator when disabled."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            with patch("app.llm.queue.processor.reconciler_queue", mock_reconciler_queue):
                from app.llm.queue.processor import process_llm_job
                
                # Mock LLM provider
                mock_provider = MagicMock()
                mock_provider.generate.return_value = sample_hsds_job.result
                
                # Process job
                with patch("app.llm.queue.processor.should_use_validator", return_value=False):
                    result = process_llm_job(sample_hsds_job.job, mock_provider)
                    
                    # Should enqueue directly to reconciler
                    mock_reconciler_queue.enqueue_call.assert_called_once()
                    call_args = mock_reconciler_queue.enqueue_call.call_args
                    assert "app.reconciler.job_processor.process_job_result" in str(call_args)

    def test_validator_forwards_to_reconciler(
        self, sample_hsds_job, mock_reconciler_queue
    ):
        """Test that validator forwards jobs to reconciler after processing."""
        from app.validator.job_processor import process_validation_job
        
        with patch("app.validator.job_processor.reconciler_queue", mock_reconciler_queue):
            # Process validation job
            result = process_validation_job(sample_hsds_job)
            
            # Should forward to reconciler
            mock_reconciler_queue.enqueue_call.assert_called_once()
            call_args = mock_reconciler_queue.enqueue_call.call_args
            assert call_args[1]["func"] == "app.reconciler.job_processor.process_job_result"
            assert call_args[1]["args"][0] == sample_hsds_job

    def test_job_data_preserved_through_validator(self, sample_hsds_job):
        """Test that job data is preserved unchanged through validator."""
        from app.validator.job_processor import process_validation_job
        
        original_data = sample_hsds_job.result.text
        original_metadata = sample_hsds_job.job.metadata.copy()
        
        # Process through validator
        result = process_validation_job(sample_hsds_job)
        
        # Data should be unchanged
        assert result.result.text == original_data
        assert result.job.metadata == original_metadata
        assert result.job_id == sample_hsds_job.job_id
        assert result.status == sample_hsds_job.status

    def test_validator_queue_error_handling(self, sample_hsds_job):
        """Test error handling when validator queue fails."""
        from app.validator.job_processor import process_validation_job
        
        with patch("app.validator.job_processor.reconciler_queue") as mock_queue:
            mock_queue.enqueue_call.side_effect = Exception("Queue error")
            
            with pytest.raises(Exception) as exc_info:
                process_validation_job(sample_hsds_job)
            
            assert "Queue error" in str(exc_info.value)

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
        assert result.status == JobStatus.FAILED
        assert result.error == "LLM processing failed"

    @patch("app.validator.job_processor.logger")
    def test_validator_logging_data_flow(self, mock_logger, sample_hsds_job):
        """Test that validator logs data flow when configured."""
        from app.validator.job_processor import process_validation_job
        
        with patch("app.core.config.settings.VALIDATOR_LOG_DATA_FLOW", True):
            process_validation_job(sample_hsds_job)
            
            # Should log data flow
            mock_logger.info.assert_called()
            log_messages = [str(call) for call in mock_logger.info.call_args_list]
            assert any("validator received job" in msg.lower() for msg in log_messages)
            assert any("forwarding to reconciler" in msg.lower() for msg in log_messages)

    def test_validator_preserves_job_timing(self, sample_hsds_job):
        """Test that validator preserves job timing information."""
        from app.validator.job_processor import process_validation_job
        
        original_created = sample_hsds_job.job.created_at
        original_completed = sample_hsds_job.completed_at
        original_processing_time = sample_hsds_job.processing_time
        
        result = process_validation_job(sample_hsds_job)
        
        assert result.job.created_at == original_created
        assert result.completed_at == original_completed
        assert result.processing_time == original_processing_time

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
                usage={},
                raw={},
            ),
            error=None,
            completed_at=datetime.now(),
            processing_time=0.5,
        )
        
        # Non-HSDS jobs might bypass validator (configurable)
        with patch("app.core.config.settings.VALIDATOR_ONLY_HSDS", True):
            assert should_validate_job(non_hsds_job) is False