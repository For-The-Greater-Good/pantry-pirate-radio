"""Tests for Fargate worker module."""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobStatus


@pytest.fixture
def sample_llm_job() -> LLMJob:
    """Create a sample LLM job for testing."""
    return LLMJob(
        id=str(uuid4()),
        prompt="Test prompt for Fargate worker testing",
        format={"type": "object", "properties": {"text": {"type": "string"}}},
        provider_config={"temperature": 0.7},
        metadata={"scraper_id": "test_scraper"},
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_sqs_backend():
    """Create a mock SQS backend."""
    from app.llm.queue.backend_sqs import SQSQueueBackend

    backend = MagicMock(spec=SQSQueueBackend)
    backend.queue_name = "test-queue"
    return backend


PROVIDER_ENV = {
    "LLM_PROVIDER": "openai",
    "LLM_MODEL_NAME": "gpt-4",
    "LLM_TEMPERATURE": "0.7",
}


class TestFargateWorkerInit:
    """Tests for FargateWorker initialization."""

    @patch("app.llm.queue.fargate_worker.create_provider")
    def test_init_creates_provider(self, mock_create_provider, mock_sqs_backend):
        """FargateWorker should create LLM provider from settings."""
        from app.llm.queue.fargate_worker import FargateWorker

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "bedrock",
                "LLM_MODEL_NAME": "anthropic.claude-sonnet-4-x",
                "LLM_TEMPERATURE": "0.7",
                "AWS_DEFAULT_REGION": "us-east-1",
            },
        ):
            worker = FargateWorker(mock_sqs_backend)

        mock_create_provider.assert_called_once()
        assert worker.backend == mock_sqs_backend

    @patch("app.llm.queue.fargate_worker.create_provider")
    def test_init_accepts_custom_settings(self, mock_create_provider, mock_sqs_backend):
        """FargateWorker should accept custom polling settings."""
        from app.llm.queue.fargate_worker import FargateWorker

        with patch.dict(os.environ, PROVIDER_ENV):
            worker = FargateWorker(
                mock_sqs_backend,
                max_messages=5,
                wait_time_seconds=10,
                visibility_extension_interval=60,
            )

        assert worker.max_messages == 5
        assert worker.wait_time_seconds == 10
        assert worker.visibility_extension_interval == 60


class TestFargateWorkerProcessing:
    """Tests for FargateWorker job processing."""

    @patch("app.llm.queue.fargate_worker.process_llm_job")
    @patch("app.llm.queue.fargate_worker.create_provider")
    def test_process_single_job_success(
        self,
        mock_create_provider,
        mock_process_job,
        mock_sqs_backend,
        sample_llm_job,
    ):
        """Should process job and update status on success."""
        from app.llm.queue.fargate_worker import FargateWorker

        # Mock successful processing
        mock_result = LLMResponse(
            text="Test response",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        mock_process_job.return_value = mock_result

        with patch.dict(os.environ, PROVIDER_ENV):
            worker = FargateWorker(mock_sqs_backend)

        message = {
            "job_id": sample_llm_job.id,
            "receipt_handle": "receipt-123",
            "job": sample_llm_job,
        }

        result = worker._process_single_job(message)

        assert result is True
        mock_sqs_backend.update_status.assert_any_call(
            sample_llm_job.id, JobStatus.PROCESSING
        )
        mock_sqs_backend.delete_message.assert_called_once_with("receipt-123")

    @patch("app.llm.queue.fargate_worker.process_llm_job")
    @patch("app.llm.queue.fargate_worker.create_provider")
    def test_process_single_job_failure(
        self,
        mock_create_provider,
        mock_process_job,
        mock_sqs_backend,
        sample_llm_job,
    ):
        """Should update status to failed and not delete message on failure."""
        from app.llm.queue.fargate_worker import FargateWorker

        # Mock processing failure
        mock_process_job.side_effect = ValueError("LLM processing failed")

        with patch.dict(os.environ, PROVIDER_ENV):
            worker = FargateWorker(mock_sqs_backend)

        message = {
            "job_id": sample_llm_job.id,
            "receipt_handle": "receipt-123",
            "job": sample_llm_job,
        }

        result = worker._process_single_job(message)

        assert result is False
        mock_sqs_backend.update_status.assert_any_call(
            sample_llm_job.id, JobStatus.FAILED, error="LLM processing failed"
        )
        # Message should NOT be deleted on failure (allow retry)
        mock_sqs_backend.delete_message.assert_not_called()


class TestFargateWorkerMainLoop:
    """Tests for FargateWorker main loop."""

    @patch("app.llm.queue.fargate_worker.create_provider")
    def test_run_polls_for_messages(self, mock_create_provider, mock_sqs_backend):
        """Worker run() should poll SQS for messages."""
        from app.llm.queue.fargate_worker import FargateWorker

        # Return empty messages then stop
        mock_sqs_backend.receive_messages.return_value = []

        with patch.dict(os.environ, PROVIDER_ENV):
            worker = FargateWorker(mock_sqs_backend, wait_time_seconds=1)

        # Stop after first poll
        def stop_on_call(*args, **kwargs):
            worker.stop()
            return []

        mock_sqs_backend.receive_messages.side_effect = stop_on_call

        worker.run()

        mock_sqs_backend.receive_messages.assert_called()

    @patch("app.llm.queue.fargate_worker.create_provider")
    def test_stop_graceful_shutdown(self, mock_create_provider, mock_sqs_backend):
        """Worker stop() should request graceful shutdown."""
        from app.llm.queue.fargate_worker import FargateWorker

        with patch.dict(os.environ, PROVIDER_ENV):
            worker = FargateWorker(mock_sqs_backend)

        worker.stop()

        assert worker._shutdown_requested is True
        assert worker._running is False


class TestFargateWorkerMain:
    """Tests for main() entry point."""

    @patch("app.llm.queue.fargate_worker.get_queue_backend")
    def test_main_requires_sqs_backend(self, mock_get_backend):
        """main() should fail if backend is not SQS."""
        from app.llm.queue.backend import RedisQueueBackend
        from app.llm.queue.fargate_worker import main

        # Return Redis backend instead of SQS
        mock_redis_backend = MagicMock(spec=RedisQueueBackend)
        mock_get_backend.return_value = mock_redis_backend

        result = main()

        assert result == 1  # Error exit code

    @patch("app.llm.queue.fargate_worker.FargateWorker")
    @patch("app.llm.queue.fargate_worker.get_queue_backend")
    def test_main_creates_and_runs_worker(self, mock_get_backend, mock_worker_class):
        """main() should create and run FargateWorker."""
        from app.llm.queue.backend_sqs import SQSQueueBackend
        from app.llm.queue.fargate_worker import main

        # Return SQS backend
        mock_sqs_backend = MagicMock(spec=SQSQueueBackend)
        mock_get_backend.return_value = mock_sqs_backend

        # Mock worker
        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker

        result = main()

        mock_worker_class.assert_called_once_with(mock_sqs_backend)
        mock_worker.run.assert_called_once()
        assert result == 0
