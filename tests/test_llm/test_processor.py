"""Tests for LLM job processor."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_mock import MockerFixture

from app.llm.providers.types import LLMResponse
from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.queue.processor import process_llm_job


@pytest.fixture
def mock_provider(mocker: MockerFixture) -> MagicMock:
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.model_name = "test-model"
    return provider


@pytest.fixture
def sample_job() -> LLMJob:
    """Create a sample LLM job."""
    return LLMJob(
        id="test-job-123",
        prompt="Test prompt",
        format={"type": "object", "properties": {"answer": {"type": "string"}}},
        created_at=datetime.now(),
    )


@pytest.fixture
def sample_llm_response() -> LLMResponse:
    """Create a sample LLM response."""
    return LLMResponse(
        text="Test response",
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        raw={"test": "data"},
    )


def test_process_llm_job_coroutine_success(
    sample_job: LLMJob, mock_provider: MagicMock, sample_llm_response: LLMResponse
) -> None:
    """Test successful processing of LLM job with coroutine result."""

    # Mock provider.generate to return a coroutine
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response

    mock_provider.generate.return_value = mock_generate()

    # Mock the queue operations
    with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler_queue:
        with patch("app.llm.queue.processor.recorder_queue") as mock_recorder_queue:
            result = process_llm_job(sample_job, mock_provider)

    # Verify result
    assert result == sample_llm_response

    # Verify provider was called correctly
    mock_provider.generate.assert_called_once_with(
        prompt=sample_job.prompt, format=sample_job.format, config=None
    )

    # Verify follow-up jobs were enqueued
    mock_reconciler_queue.enqueue_call.assert_called_once()
    mock_recorder_queue.enqueue_call.assert_called_once()

    # Check reconciler queue call
    reconciler_call = mock_reconciler_queue.enqueue_call.call_args
    assert (
        reconciler_call[1]["func"] == "app.reconciler.job_processor.process_job_result"
    )
    assert len(reconciler_call[1]["args"]) == 1
    job_result = reconciler_call[1]["args"][0]
    assert isinstance(job_result, JobResult)
    assert job_result.job_id == sample_job.id
    assert job_result.status == JobStatus.COMPLETED
    assert job_result.result == sample_llm_response

    # Check recorder queue call
    recorder_call = mock_recorder_queue.enqueue_call.call_args
    assert recorder_call[1]["func"] == "app.recorder.utils.record_result"


def test_process_llm_job_async_generator_success(
    sample_job: LLMJob, mock_provider: MagicMock, sample_llm_response: LLMResponse
) -> None:
    """Test successful processing of LLM job with async generator result."""

    # Mock provider.generate to return an async generator
    async def mock_generate(
        *args: Any, **kwargs: Any
    ) -> AsyncGenerator[LLMResponse, None]:
        yield sample_llm_response

    mock_provider.generate.return_value = mock_generate()

    # Mock the queue operations
    with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler_queue:
        with patch("app.llm.queue.processor.recorder_queue") as mock_recorder_queue:
            result = process_llm_job(sample_job, mock_provider)

    # Verify result
    assert result == sample_llm_response

    # Verify follow-up jobs were enqueued
    mock_reconciler_queue.enqueue_call.assert_called_once()
    mock_recorder_queue.enqueue_call.assert_called_once()


def test_process_llm_job_claude_not_authenticated_first_retry(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of Claude authentication error with retry."""
    from app.llm.providers.claude import ClaudeNotAuthenticatedException

    # Mock provider to raise authentication error
    mock_provider.generate.side_effect = ClaudeNotAuthenticatedException(
        "Authentication required"
    )

    # Mock current job context
    mock_job = MagicMock()
    mock_job.meta = {}
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with patch("app.llm.queue.queues.llm_queue") as mock_llm_queue:
            mock_retry_job = MagicMock()
            mock_retry_job.id = "retry-job-123"
            mock_llm_queue.enqueue_in.return_value = mock_retry_job

            result = process_llm_job(sample_job, mock_provider)

    # Verify retry was scheduled
    assert isinstance(result, LLMResponse)
    assert "Authentication required" in result.text
    assert result.raw["auth_retry_scheduled"] is True
    assert result.raw["retry_delay"] == 300  # 5 minutes

    # Verify job metadata was updated
    assert mock_job.meta["auth_retry_count"] == 1
    mock_job.save_meta.assert_called_once()

    # Verify retry job was enqueued
    mock_llm_queue.enqueue_in.assert_called_once()
    call_args = mock_llm_queue.enqueue_in.call_args
    assert call_args[0][0] == timedelta(seconds=300)
    assert "auth_retry" in call_args[1]["job_id"]


def test_process_llm_job_claude_not_authenticated_max_retries(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of Claude authentication error after max retries."""
    from app.llm.providers.claude import ClaudeNotAuthenticatedException

    # Mock provider to raise authentication error
    auth_error = ClaudeNotAuthenticatedException("Authentication required")
    mock_provider.generate.side_effect = auth_error

    # Mock current job context with max retries reached
    mock_job = MagicMock()
    mock_job.meta = MagicMock()
    mock_job.meta.auth_retry_count = 12  # Max retries
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with pytest.raises(ClaudeNotAuthenticatedException):
            process_llm_job(sample_job, mock_provider)


def test_process_llm_job_claude_not_authenticated_no_job_context(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of Claude authentication error without job context."""
    from app.llm.providers.claude import ClaudeNotAuthenticatedException

    # Mock provider to raise authentication error
    auth_error = ClaudeNotAuthenticatedException("Authentication required")
    mock_provider.generate.side_effect = auth_error

    # Mock no current job context
    with patch("app.llm.queue.processor.get_current_job", return_value=None):
        with pytest.raises(ClaudeNotAuthenticatedException):
            process_llm_job(sample_job, mock_provider)


def test_process_llm_job_claude_quota_exceeded_first_retry(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of Claude quota exceeded error with retry."""
    from app.llm.providers.claude import ClaudeQuotaExceededException

    # Mock provider to raise quota exceeded error
    mock_provider.generate.side_effect = ClaudeQuotaExceededException("Quota exceeded")

    # Mock current job context
    mock_job = MagicMock()
    mock_job.meta = {}
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.CLAUDE_QUOTA_RETRY_DELAY = 3600
    mock_settings.CLAUDE_QUOTA_MAX_DELAY = 14400
    mock_settings.CLAUDE_QUOTA_BACKOFF_MULTIPLIER = 1.5

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with patch("app.core.config.settings", mock_settings):
            with patch("app.llm.queue.queues.llm_queue") as mock_llm_queue:
                mock_retry_job = MagicMock()
                mock_retry_job.id = "retry-job-123"
                mock_llm_queue.enqueue_in.return_value = mock_retry_job

                result = process_llm_job(sample_job, mock_provider)

    # Verify retry was scheduled
    assert isinstance(result, LLMResponse)
    assert "Quota exceeded" in result.text
    assert result.raw["retry_scheduled"] is True
    assert result.raw["retry_delay"] == 3600  # Base delay

    # Verify job metadata was updated
    assert mock_job.meta["quota_retry_count"] == 1
    mock_job.save_meta.assert_called_once()

    # Verify retry job was enqueued
    mock_llm_queue.enqueue_in.assert_called_once()


def test_process_llm_job_claude_quota_exceeded_exponential_backoff(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test exponential backoff for quota exceeded retries."""
    from app.llm.providers.claude import ClaudeQuotaExceededException

    # Mock provider to raise quota exceeded error
    mock_provider.generate.side_effect = ClaudeQuotaExceededException("Quota exceeded")

    # Mock current job context with existing retry count
    mock_job = MagicMock()
    mock_job.meta = MagicMock()
    mock_job.meta.quota_retry_count = 2  # Third retry
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.CLAUDE_QUOTA_RETRY_DELAY = 3600  # 1 hour
    mock_settings.CLAUDE_QUOTA_MAX_DELAY = 14400  # 4 hours
    mock_settings.CLAUDE_QUOTA_BACKOFF_MULTIPLIER = 1.5

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with patch("app.core.config.settings", mock_settings):
            with patch("app.llm.queue.queues.llm_queue") as mock_llm_queue:
                mock_retry_job = MagicMock()
                mock_retry_job.id = "retry-job-123"
                mock_llm_queue.enqueue_in.return_value = mock_retry_job

                result = process_llm_job(sample_job, mock_provider)

    # Calculate expected delay: 3600 * (1.5^2) = 8100
    expected_delay = 8100
    assert result.raw["retry_delay"] == expected_delay

    # Verify retry job was enqueued with correct delay
    call_args = mock_llm_queue.enqueue_in.call_args
    assert call_args[0][0] == timedelta(seconds=expected_delay)


def test_process_llm_job_claude_quota_exceeded_max_delay(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test that exponential backoff respects max delay."""
    from app.llm.providers.claude import ClaudeQuotaExceededException

    # Mock provider to raise quota exceeded error
    mock_provider.generate.side_effect = ClaudeQuotaExceededException("Quota exceeded")

    # Mock current job context with high retry count
    mock_job = MagicMock()
    mock_job.meta = MagicMock()
    mock_job.meta.quota_retry_count = 10  # High retry count
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.CLAUDE_QUOTA_RETRY_DELAY = 3600  # 1 hour
    mock_settings.CLAUDE_QUOTA_MAX_DELAY = 14400  # 4 hours max
    mock_settings.CLAUDE_QUOTA_BACKOFF_MULTIPLIER = 1.5

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with patch("app.core.config.settings", mock_settings):
            with patch("app.llm.queue.queues.llm_queue") as mock_llm_queue:
                mock_retry_job = MagicMock()
                mock_retry_job.id = "retry-job-123"
                mock_llm_queue.enqueue_in.return_value = mock_retry_job

                result = process_llm_job(sample_job, mock_provider)

    # Should be capped at max delay
    assert result.raw["retry_delay"] == 14400


def test_process_llm_job_claude_quota_exceeded_no_job_context(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of Claude quota exceeded error without job context."""
    from app.llm.providers.claude import ClaudeQuotaExceededException

    # Mock provider to raise quota exceeded error
    quota_error = ClaudeQuotaExceededException("Quota exceeded")
    mock_provider.generate.side_effect = quota_error

    # Mock no current job context
    with patch("app.llm.queue.processor.get_current_job", return_value=None):
        with pytest.raises(ClaudeQuotaExceededException):
            process_llm_job(sample_job, mock_provider)


def test_process_llm_job_generic_exception(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of generic exceptions."""
    # Mock provider to raise generic error
    generic_error = ValueError("Generic error")
    mock_provider.generate.side_effect = generic_error

    with pytest.raises(ValueError, match="Generic error"):
        process_llm_job(sample_job, mock_provider)


def test_process_llm_job_settings_fallback(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test fallback behavior when settings attributes are missing."""
    from app.llm.providers.claude import ClaudeQuotaExceededException

    # Mock provider to raise quota exceeded error
    mock_provider.generate.side_effect = ClaudeQuotaExceededException("Quota exceeded")

    # Mock current job context
    mock_job = MagicMock()
    mock_job.meta = {}
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    # Mock settings to use default values when attributes are missing
    mock_settings = MagicMock()
    # Remove the Claude-specific attributes to trigger getattr defaults
    del mock_settings.CLAUDE_QUOTA_RETRY_DELAY
    del mock_settings.CLAUDE_QUOTA_MAX_DELAY
    del mock_settings.CLAUDE_QUOTA_BACKOFF_MULTIPLIER

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with patch("app.core.config.settings", mock_settings):
            with patch("app.llm.queue.queues.llm_queue") as mock_llm_queue:
                mock_retry_job = MagicMock()
                mock_retry_job.id = "retry-job-123"
                mock_llm_queue.enqueue_in.return_value = mock_retry_job

                result = process_llm_job(sample_job, mock_provider)

    # Should use default values (3600 is the default for CLAUDE_QUOTA_RETRY_DELAY)
    assert result.raw["retry_delay"] == 3600  # Default base delay


def test_process_llm_job_event_loop_cleanup(
    sample_job: LLMJob, mock_provider: MagicMock, sample_llm_response: LLMResponse
) -> None:
    """Test that event loop is properly cleaned up."""

    # Mock provider.generate to return a coroutine
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response

    mock_provider.generate.return_value = mock_generate()

    # Mock the loop operations
    mock_loop = MagicMock()
    mock_loop.run_until_complete.return_value = sample_llm_response

    with patch("asyncio.new_event_loop", return_value=mock_loop):
        with patch("asyncio.set_event_loop"):
            with patch("app.llm.queue.processor.reconciler_queue"):
                with patch("app.llm.queue.processor.recorder_queue"):
                    process_llm_job(sample_job, mock_provider)

    # Verify loop was closed
    mock_loop.close.assert_called_once()


def test_process_llm_job_exception_with_loop_cleanup(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test that event loop is cleaned up even when exception occurs."""
    # Mock provider to raise error
    mock_provider.generate.side_effect = ValueError("Test error")

    # Mock the loop operations
    mock_loop = MagicMock()

    with patch("asyncio.new_event_loop", return_value=mock_loop):
        with patch("asyncio.set_event_loop"):
            with pytest.raises(ValueError):
                process_llm_job(sample_job, mock_provider)

    # Verify loop was closed even with exception
    mock_loop.close.assert_called_once()


def test_process_llm_job_provider_without_model_name(
    sample_job: LLMJob, sample_llm_response: LLMResponse
) -> None:
    """Test handling of provider without model_name attribute."""
    # Create provider without model_name
    mock_provider = MagicMock()
    mock_provider.model_name = None

    # Mock provider.generate to return a coroutine
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response

    mock_provider.generate.return_value = mock_generate()

    with patch("app.llm.queue.processor.reconciler_queue"):
        with patch("app.llm.queue.processor.recorder_queue"):
            result = process_llm_job(sample_job, mock_provider)

    assert result == sample_llm_response


def test_process_llm_job_claude_auth_error_provider_without_model_name(
    sample_job: LLMJob,
) -> None:
    """Test Claude auth error handling with provider without model_name."""
    from app.llm.providers.claude import ClaudeNotAuthenticatedException

    # Create provider without model_name
    mock_provider = MagicMock()
    mock_provider.model_name = None
    mock_provider.generate.side_effect = ClaudeNotAuthenticatedException(
        "Authentication required"
    )

    # Mock current job context
    mock_job = MagicMock()
    mock_job.meta = {}
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with patch("app.llm.queue.queues.llm_queue") as mock_llm_queue:
            mock_retry_job = MagicMock()
            mock_retry_job.id = "retry-job-123"
            mock_llm_queue.enqueue_in.return_value = mock_retry_job

            result = process_llm_job(sample_job, mock_provider)

    # Should use "claude" as fallback model name
    assert result.model == "claude"


def test_process_llm_job_quota_error_provider_without_model_name(
    sample_job: LLMJob,
) -> None:
    """Test Claude quota error handling with provider without model_name."""
    from app.llm.providers.claude import ClaudeQuotaExceededException

    # Create provider without model_name
    mock_provider = MagicMock()
    mock_provider.model_name = None
    mock_provider.generate.side_effect = ClaudeQuotaExceededException("Quota exceeded")

    # Mock current job context
    mock_job = MagicMock()
    mock_job.meta = {}
    mock_job.id = "current-job-123"
    mock_job.save_meta = MagicMock()  # Mock the save_meta method

    with patch("app.llm.queue.processor.get_current_job", return_value=mock_job):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.CLAUDE_QUOTA_RETRY_DELAY = 3600
            mock_settings.CLAUDE_QUOTA_MAX_DELAY = 14400
            mock_settings.CLAUDE_QUOTA_BACKOFF_MULTIPLIER = 1.5

            with patch("app.llm.queue.queues.llm_queue") as mock_llm_queue:
                mock_retry_job = MagicMock()
                mock_retry_job.id = "retry-job-123"
                mock_llm_queue.enqueue_in.return_value = mock_retry_job

                result = process_llm_job(sample_job, mock_provider)

    # Should use "claude" as fallback model name
    assert result.model == "claude"
