"""Tests for simplified LLM job processor."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.llm.queue.models import LLMJob
from app.llm.queue.processor import process_llm_job
from app.llm.providers.claude import (
    ClaudeNotAuthenticatedException,
    ClaudeQuotaExceededException,
)


@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
    return LLMJob(
        id="test-job-123",
        prompt="Test prompt",
        format={"type": "object", "properties": {"answer": {"type": "string"}}},
        provider_config={},
        metadata={},
        created_at=datetime.now(),
    )


def test_process_llm_job_claude_auth_error_updates_state_and_raises(
    sample_job: LLMJob,
) -> None:
    """Test that auth errors update state and re-raise."""
    mock_provider = MagicMock()
    auth_error = ClaudeNotAuthenticatedException("Auth failed", retry_after=300)
    mock_provider.generate.side_effect = auth_error

    with patch("app.llm.queue.processor.llm_queue") as mock_queue:
        with patch("app.llm.queue.auth_state.AuthStateManager") as mock_auth_manager:
            mock_auth_instance = MagicMock()
            mock_auth_manager.return_value = mock_auth_instance

            # Should raise the auth exception
            with pytest.raises(ClaudeNotAuthenticatedException):
                process_llm_job(sample_job, mock_provider)

            # Verify auth state was updated
            mock_auth_manager.assert_called_once_with(mock_queue.connection)
            mock_auth_instance.set_auth_failed.assert_called_once_with(
                "Auth failed", retry_after=300
            )


def test_process_llm_job_claude_quota_error_updates_state_and_raises(
    sample_job: LLMJob,
) -> None:
    """Test that quota errors update state and re-raise."""
    mock_provider = MagicMock()
    quota_error = ClaudeQuotaExceededException("Quota exceeded", retry_after=3600)
    mock_provider.generate.side_effect = quota_error

    with patch("app.llm.queue.processor.llm_queue") as mock_queue:
        with patch("app.llm.queue.auth_state.AuthStateManager") as mock_auth_manager:
            mock_auth_instance = MagicMock()
            mock_auth_manager.return_value = mock_auth_instance

            # Should raise the quota exception
            with pytest.raises(ClaudeQuotaExceededException):
                process_llm_job(sample_job, mock_provider)

            # Verify quota state was updated
            mock_auth_manager.assert_called_once_with(mock_queue.connection)
            mock_auth_instance.set_quota_exceeded.assert_called_once_with(
                "Quota exceeded", retry_after=3600
            )


def test_process_llm_job_other_errors_reraise_without_state_update(
    sample_job: LLMJob,
) -> None:
    """Test that other errors are re-raised without updating auth state."""
    mock_provider = MagicMock()
    generic_error = ValueError("Something went wrong")
    mock_provider.generate.side_effect = generic_error

    with patch("app.llm.queue.auth_state.AuthStateManager") as mock_auth_manager:
        # Should raise the generic exception
        with pytest.raises(ValueError, match="Something went wrong"):
            process_llm_job(sample_job, mock_provider)

        # Auth manager should not be instantiated for generic errors
        mock_auth_manager.assert_not_called()


def test_process_llm_job_success_enqueues_follow_up_jobs(sample_job: LLMJob) -> None:
    """Test successful job processing enqueues reconciler and recorder jobs."""
    from app.llm.providers.types import LLMResponse

    mock_provider = MagicMock()
    mock_response = LLMResponse(
        text="Test response",
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        raw={},
    )

    # Mock coroutine for async generate
    async def mock_generate(*args, **kwargs):
        return mock_response

    mock_provider.generate.return_value = mock_generate()

    with patch("app.llm.queue.processor.should_use_validator", return_value=False):
        with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler:
            with patch("app.llm.queue.processor.recorder_queue") as mock_recorder:
                mock_reconciler_job = MagicMock()
                mock_reconciler_job.id = "reconciler-123"
                mock_reconciler.enqueue_call.return_value = mock_reconciler_job

                mock_recorder_job = MagicMock()
                mock_recorder_job.id = "recorder-123"
                mock_recorder.enqueue_call.return_value = mock_recorder_job

                result = process_llm_job(sample_job, mock_provider)

            # Verify result
            assert result == mock_response

            # Verify reconciler job was enqueued
            mock_reconciler.enqueue_call.assert_called_once()
            assert (
                mock_reconciler.enqueue_call.call_args[1]["func"]
                == "app.reconciler.job_processor.process_job_result"
            )

            # Verify recorder job was enqueued
            mock_recorder.enqueue_call.assert_called_once()
            assert (
                mock_recorder.enqueue_call.call_args[1]["func"]
                == "app.recorder.utils.record_result"
            )
