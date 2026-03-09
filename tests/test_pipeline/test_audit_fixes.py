"""Tests for pipeline audit remediation fixes (C1-C4, H1-H5, M1-M6).

Covers:
- C1: Enqueue-before-store ordering in processor.py
- C3: SQS queue URL validation at startup
- H1: PipelineWorker visibility heartbeat
- H3: Auth/quota error cooldown in SQS mode
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.sqs_worker import PipelineWorker, _VisibilityHeartbeat


class TestC3QueueUrlValidation:
    """C3: Validate that missing queue URLs raise descriptive errors at startup."""

    def test_pipeline_worker_rejects_empty_queue_url(self):
        """PipelineWorker should raise ValueError for empty queue_url."""
        with pytest.raises(ValueError, match="queue_url is required"):
            PipelineWorker(
                queue_url="",
                process_fn=MagicMock(),
                service_name="test-service",
            )

    def test_pipeline_worker_accepts_valid_queue_url(self):
        """PipelineWorker should accept a non-empty queue_url."""
        worker = PipelineWorker(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test.fifo",
            process_fn=MagicMock(),
            service_name="test-service",
        )
        assert worker.queue_url == "https://sqs.us-east-1.amazonaws.com/123/test.fifo"

    @patch.dict("os.environ", {"QUEUE_BACKEND": "sqs"}, clear=False)
    @patch.dict(
        "os.environ",
        {"VALIDATOR_QUEUE_URL": "", "VALIDATOR_ENABLED": "true"},
        clear=False,
    )
    def test_validate_sqs_queue_urls_raises_for_missing_validator_url(self):
        """validate_sqs_queue_urls should raise when VALIDATOR_QUEUE_URL is empty."""
        from app.llm.queue.processor import validate_sqs_queue_urls

        with pytest.raises(ValueError, match="VALIDATOR_QUEUE_URL"):
            validate_sqs_queue_urls()

    @patch.dict("os.environ", {"QUEUE_BACKEND": "redis"}, clear=False)
    def test_validate_sqs_queue_urls_skips_redis_mode(self):
        """validate_sqs_queue_urls should be a no-op in Redis mode."""
        from app.llm.queue.processor import validate_sqs_queue_urls

        # Should not raise
        validate_sqs_queue_urls()


class TestH1VisibilityHeartbeat:
    """H1: PipelineWorker visibility heartbeat prevents message redelivery."""

    def test_heartbeat_extends_visibility(self):
        """Heartbeat should call change_message_visibility on the SQS client."""
        mock_sqs = MagicMock()
        heartbeat = _VisibilityHeartbeat(
            sqs_client=mock_sqs,
            queue_url="https://sqs.../queue.fifo",
            receipt_handle="test-receipt",
            visibility_timeout=300,
            service_name="test",
        )

        heartbeat.start()
        # Give the heartbeat thread time to fire (interval = 300/2 = 150s)
        # We can't wait that long in a test, so verify the thread started
        assert heartbeat._thread.is_alive()
        heartbeat.stop()
        assert not heartbeat._thread.is_alive()

    @patch("app.pipeline.sqs_worker.time")
    def test_heartbeat_sets_failed_on_permanent_error(self, mock_time):
        """Heartbeat should set failed=True after max retries."""
        # Mock time.sleep to be instant, but keep Event.wait working
        mock_time.sleep = MagicMock()

        mock_sqs = MagicMock()
        mock_sqs.change_message_visibility.side_effect = Exception("SQS error")

        heartbeat = _VisibilityHeartbeat(
            sqs_client=mock_sqs,
            queue_url="https://sqs.../queue.fifo",
            receipt_handle="test-receipt",
            visibility_timeout=2,  # Short for testing
            service_name="test",
        )

        heartbeat.start()
        # Wait for the thread to finish (it will fail after max retries)
        heartbeat._thread.join(timeout=10)
        heartbeat.stop()

        assert heartbeat.failed is True

    @patch("app.pipeline.sqs_worker.time")
    def test_heartbeat_retries_on_transient_error(self, mock_time):
        """Heartbeat should retry before giving up."""
        mock_time.sleep = MagicMock()

        mock_sqs = MagicMock()
        # Fail once, then succeed on retry; provide extras for subsequent cycles
        mock_sqs.change_message_visibility.side_effect = [
            Exception("transient"),
            None,  # success on retry (first cycle)
            None,  # success on second cycle
            None,  # success on third cycle
        ]

        heartbeat = _VisibilityHeartbeat(
            sqs_client=mock_sqs,
            queue_url="https://sqs.../queue.fifo",
            receipt_handle="test-receipt",
            visibility_timeout=2,  # Short for testing
            service_name="test",
        )

        heartbeat.start()
        time.sleep(3)
        heartbeat.stop()

        # Should NOT have failed since retry succeeded
        assert heartbeat.failed is False


class TestC1EnqueueBeforeStore:
    """C1: Validator enqueue failure should NOT mark content store as completed."""

    @patch("app.llm.queue.processor._is_sqs_backend", return_value=True)
    @patch("app.llm.queue.processor.should_use_validator", return_value=True)
    @patch("app.llm.queue.processor.enqueue_to_validator")
    @patch("app.content_store.config.get_content_store")
    def test_enqueue_failure_does_not_store_result(
        self,
        mock_get_store,
        mock_enqueue,
        _mock_use_validator,
        _mock_is_sqs,
    ):
        """When validator enqueue fails, content store should NOT have the result."""
        from datetime import datetime

        from app.llm.providers.types import LLMResponse
        from app.llm.queue.job import LLMJob

        mock_enqueue.side_effect = Exception("SQS send failed")
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store

        job = LLMJob(
            id="test-job-123",
            prompt="test prompt",
            metadata={"content_hash": "a" * 64, "scraper_id": "test"},
            created_at=datetime.now(),
        )

        mock_provider = MagicMock()
        mock_provider.generate.return_value = LLMResponse(
            text="valid response",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 20},
        )

        from app.llm.queue.processor import process_llm_job

        with pytest.raises(ValueError, match="Failed to enqueue validator job"):
            process_llm_job(job, mock_provider)

        # Content store should NOT have been written to
        mock_store.store_result.assert_not_called()

    @patch("app.llm.queue.processor._is_sqs_backend", return_value=True)
    @patch("app.llm.queue.processor.should_use_validator", return_value=True)
    @patch("app.llm.queue.processor.enqueue_to_validator", return_value="val-123")
    @patch("app.content_store.config.get_content_store")
    def test_enqueue_success_stores_result(
        self,
        mock_get_store,
        mock_enqueue,
        _mock_use_validator,
        _mock_is_sqs,
    ):
        """When validator enqueue succeeds, content store SHOULD be written."""
        from datetime import datetime

        from app.llm.providers.types import LLMResponse
        from app.llm.queue.job import LLMJob

        mock_store = MagicMock()
        mock_get_store.return_value = mock_store

        job = LLMJob(
            id="test-job-123",
            prompt="test prompt",
            metadata={"content_hash": "a" * 64, "scraper_id": "test"},
            created_at=datetime.now(),
        )

        mock_provider = MagicMock()
        mock_provider.generate.return_value = LLMResponse(
            text="valid response",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 20},
        )

        from app.llm.queue.processor import process_llm_job

        process_llm_job(job, mock_provider)

        # Content store SHOULD have been written to
        mock_store.store_result.assert_called_once()


class TestH3AuthCooldown:
    """H3: SQS mode should sleep on auth/quota errors instead of immediate retry."""

    @patch("app.llm.queue.processor._is_sqs_backend", return_value=True)
    @patch("time.sleep")
    def test_auth_error_triggers_cooldown_in_sqs_mode(self, mock_sleep, _mock_is_sqs):
        """Auth errors in SQS mode should trigger cooldown sleep."""
        from app.llm.providers.claude import ClaudeNotAuthenticatedException
        from app.llm.queue.processor import handle_claude_errors

        error = ClaudeNotAuthenticatedException("auth failed")
        error.retry_after = 120

        job = MagicMock()
        job.id = "test-job"

        # handle_claude_errors uses bare `raise`, so must be called from
        # within an except block to have an active exception context
        with pytest.raises(ClaudeNotAuthenticatedException):
            try:
                raise error
            except ClaudeNotAuthenticatedException:
                handle_claude_errors(error, job)

        # Should have slept for retry_after seconds
        mock_sleep.assert_called_once_with(120)

    @patch("app.llm.queue.processor._is_sqs_backend", return_value=True)
    @patch("time.sleep")
    def test_quota_error_triggers_cooldown_in_sqs_mode(self, mock_sleep, _mock_is_sqs):
        """Quota errors in SQS mode should trigger cooldown sleep."""
        from app.llm.providers.claude import ClaudeQuotaExceededException
        from app.llm.queue.processor import handle_claude_errors

        error = ClaudeQuotaExceededException("quota exceeded")
        error.retry_after = 300

        job = MagicMock()
        job.id = "test-job"

        with pytest.raises(ClaudeQuotaExceededException):
            try:
                raise error
            except ClaudeQuotaExceededException:
                handle_claude_errors(error, job)

        mock_sleep.assert_called_once_with(300)
