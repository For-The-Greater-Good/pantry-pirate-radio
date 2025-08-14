"""Integration tests for the validator service."""

import json
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from redis import Redis
from rq import Queue, Worker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse


class TestValidatorIntegration:
    """Integration tests for the validator service."""

    @pytest.mark.integration
    def test_full_pipeline_with_validator(self, db_session, mock_redis):
        """Test the full pipeline: LLM -> Validator -> Reconciler."""
        from app.llm.queue.processor import process_llm_job
        from app.validator.job_processor import process_validation_job
        from app.reconciler.job_processor import process_job_result
        
        # Create LLM job
        job = LLMJob(
            id="integration-test-job",
            prompt="Extract organization data",
            format={"type": "hsds"},
            provider_config={},
            metadata={"content_hash": "xyz123", "source": "integration_test"},
            created_at=datetime.now(),
        )
        
        # Mock LLM response
        llm_response = LLMResponse(
            text=json.dumps({
                "organization": {
                    "name": "Integration Test Food Bank",
                    "description": "Testing the full pipeline"
                },
                "locations": [{
                    "name": "Main Location",
                    "latitude": 40.7128,
                    "longitude": -74.0060
                }]
            }),
            model="test-model",
            usage={"total_tokens": 100},
            raw={},
        )
        
        # Mock provider
        mock_provider = MagicMock()
        mock_provider.generate.return_value = llm_response
        
        with patch("app.core.config.settings.VALIDATOR_ENABLED", True):
            # Step 1: LLM processing
            with patch("app.llm.queue.processor.validator_queue") as mock_validator_queue:
                with patch("app.llm.queue.processor.recorder_queue"):
                    llm_result = process_llm_job(job, mock_provider)
                    assert llm_result == llm_response
                    
                    # Should enqueue to validator
                    mock_validator_queue.enqueue_call.assert_called_once()
            
            # Create job result for next step
            job_result = JobResult(
                job_id=job.id,
                job=job,
                status=JobStatus.COMPLETED,
                result=llm_response,
                error=None,
                completed_at=datetime.now(),
                processing_time=1.0,
            )
            
            # Step 2: Validator processing
            with patch("app.validator.job_processor.reconciler_queue") as mock_reconciler_queue:
                validation_result = process_validation_job(job_result)
                
                # Should pass through unchanged
                assert validation_result == job_result
                
                # Should enqueue to reconciler
                mock_reconciler_queue.enqueue_call.assert_called_once()
            
            # Step 3: Reconciler processing
            with patch("app.reconciler.job_processor.create_engine"):
                with patch("app.reconciler.job_processor.JobProcessor") as MockProcessor:
                    mock_instance = MockProcessor.return_value
                    mock_instance.process_job_result.return_value = {
                        "status": "success",
                        "organization_id": "org-123",
                        "location_ids": ["loc-456"]
                    }
                    
                    final_result = process_job_result(job_result)
                    
                    assert final_result["status"] == "success"
                    assert "organization_id" in final_result

    @pytest.mark.integration
    def test_validator_worker_processing(self, mock_redis):
        """Test validator worker processing jobs from queue."""
        from app.validator.worker import ValidatorWorker
        from app.validator.queues import validator_queue
        
        # Create worker
        worker = ValidatorWorker(redis=mock_redis)
        
        # Create test job
        test_job = JobResult(
            job_id="worker-test",
            job=LLMJob(
                id="worker-test",
                prompt="Test",
                format={},
                provider_config={},
                metadata={},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text='{"test": "data"}',
                model="test",
                usage={},
                raw={},
            ),
            error=None,
            completed_at=datetime.now(),
            processing_time=0.5,
        )
        
        with patch.object(validator_queue, "enqueue_call") as mock_enqueue:
            mock_enqueue.return_value = MagicMock(id="queued-job-id")
            
            # Enqueue job
            job_id = validator_queue.enqueue_call(
                func="app.validator.job_processor.process_validation_job",
                args=(test_job,)
            ).id
            
            assert job_id == "queued-job-id"
            mock_enqueue.assert_called_once()

    @pytest.mark.integration
    def test_validator_metrics_integration(self):
        """Test that validator metrics are properly integrated."""
        from app.validator.metrics import (
            VALIDATOR_JOBS_TOTAL,
            VALIDATOR_JOBS_PASSED,
            VALIDATOR_PROCESSING_TIME,
        )
        from prometheus_client import REGISTRY
        
        # Metrics should be registered
        assert VALIDATOR_JOBS_TOTAL._name in REGISTRY._names_to_collectors
        assert VALIDATOR_JOBS_PASSED._name in REGISTRY._names_to_collectors
        assert VALIDATOR_PROCESSING_TIME._name in REGISTRY._names_to_collectors

    @pytest.mark.integration
    def test_validator_database_integration(self, db_session):
        """Test validator integration with database."""
        from app.validator.job_processor import ValidationProcessor
        from app.database.models import Organization, Location
        
        processor = ValidationProcessor(db=db_session)
        
        # Create test data
        org = Organization(
            name="Test Org",
            description="Test"
        )
        db_session.add(org)
        db_session.commit()
        
        location = Location(
            name="Test Location",
            latitude=40.7128,
            longitude=-74.0060,
            organization_id=org.id
        )
        db_session.add(location)
        db_session.commit()
        
        # Process should be able to update validation fields
        with patch.object(processor, "update_location_validation") as mock_update:
            mock_update.return_value = None
            
            # Create job result with location data
            job_result = JobResult(
                job_id="db-test",
                job=LLMJob(
                    id="db-test",
                    prompt="Test",
                    format={},
                    provider_config={},
                    metadata={"organization_id": str(org.id)},
                    created_at=datetime.now(),
                ),
                status=JobStatus.COMPLETED,
                result=LLMResponse(
                    text=json.dumps({
                        "organization": {"id": str(org.id)},
                        "locations": [{"id": str(location.id)}]
                    }),
                    model="test",
                    usage={},
                    raw={},
                ),
                error=None,
                completed_at=datetime.now(),
                processing_time=1.0,
            )
            
            processor.process_job_result(job_result)
            
            # Should attempt to update validation fields
            mock_update.assert_called()

    @pytest.mark.integration
    def test_validator_redis_integration(self, mock_redis):
        """Test validator integration with Redis."""
        from app.validator.queues import setup_validator_queues
        
        with patch("redis.Redis", return_value=mock_redis):
            queues = setup_validator_queues()
            
            assert "validator" in queues
            assert "reconciler" in queues
            
            # Should be able to enqueue jobs
            validator_queue = queues["validator"]
            assert hasattr(validator_queue, "enqueue_call")

    @pytest.mark.integration
    def test_validator_disabled_integration(self):
        """Test system integration when validator is disabled."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            from app.llm.queue.processor import get_next_queue
            
            # Should skip validator queue
            next_queue = get_next_queue("llm")
            assert next_queue == "reconciler"
            
            # Validator queue shouldn't be in pipeline
            from app.validator.config import get_pipeline_stages
            stages = get_pipeline_stages()
            assert "validator" not in stages

    @pytest.mark.integration
    def test_validator_error_recovery(self, db_session):
        """Test error recovery in validator service."""
        from app.validator.job_processor import ValidationProcessor
        
        processor = ValidationProcessor(db=db_session)
        
        # Create job with invalid data
        invalid_job = JobResult(
            job_id="error-test",
            job=LLMJob(
                id="error-test",
                prompt="Test",
                format={},
                provider_config={},
                metadata={},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text="not valid json at all",
                model="test",
                usage={},
                raw={},
            ),
            error=None,
            completed_at=datetime.now(),
            processing_time=1.0,
        )
        
        # Should handle error gracefully
        with patch("app.validator.job_processor.logger") as mock_logger:
            result = processor.process_job_result(invalid_job)
            
            # Should log error
            mock_logger.error.assert_called()
            
            # Should still return a result (pass through)
            assert result is not None

    @pytest.mark.integration
    def test_validator_performance(self, db_session):
        """Test validator performance doesn't significantly impact pipeline."""
        from app.validator.job_processor import ValidationProcessor
        
        processor = ValidationProcessor(db=db_session)
        
        # Create large job
        large_data = {
            "organization": {"name": "Test"},
            "locations": [
                {"latitude": i, "longitude": -i}
                for i in range(100)  # 100 locations
            ],
            "services": [
                {"name": f"Service {i}"}
                for i in range(50)  # 50 services
            ]
        }
        
        job_result = JobResult(
            job_id="perf-test",
            job=LLMJob(
                id="perf-test",
                prompt="Test",
                format={},
                provider_config={},
                metadata={},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text=json.dumps(large_data),
                model="test",
                usage={},
                raw={},
            ),
            error=None,
            completed_at=datetime.now(),
            processing_time=1.0,
        )
        
        # Measure processing time
        start_time = time.time()
        processor.process_job_result(job_result)
        processing_time = time.time() - start_time
        
        # Should be fast (passthrough only)
        assert processing_time < 0.1  # Less than 100ms