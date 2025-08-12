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
    sample_job: LLMJob,
    mock_provider: MagicMock,
    sample_llm_response: LLMResponse,
) -> None:
    """Test successful processing of LLM job with coroutine result."""

    # Mock provider.generate to return a coroutine
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response

    mock_provider.generate.return_value = mock_generate()

    # Mock the queue operations
    with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler_queue:
        with patch("app.llm.queue.processor.recorder_queue") as mock_recorder_queue:
            with patch("app.content_store.config.get_content_store", return_value=None):
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
    sample_job: LLMJob,
    mock_provider: MagicMock,
    sample_llm_response: LLMResponse,
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
            with patch("app.content_store.config.get_content_store", return_value=None):
                result = process_llm_job(sample_job, mock_provider)

    # Verify result
    assert result == sample_llm_response

    # Verify follow-up jobs were enqueued
    mock_reconciler_queue.enqueue_call.assert_called_once()
    mock_recorder_queue.enqueue_call.assert_called_once()


def test_process_llm_job_claude_not_authenticated_updates_state(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of Claude authentication error updates state and raises."""
    from app.llm.providers.claude import ClaudeNotAuthenticatedException

    # Mock provider to raise authentication error
    auth_error = ClaudeNotAuthenticatedException(
        "Authentication required", retry_after=300
    )
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
                "Authentication required", retry_after=300
            )


def test_process_llm_job_claude_not_authenticated_always_raises(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test that auth errors always raise and update state."""
    from app.llm.providers.claude import ClaudeNotAuthenticatedException

    # Mock provider to raise authentication error
    auth_error = ClaudeNotAuthenticatedException("Authentication required")
    mock_provider.generate.side_effect = auth_error

    with patch("app.llm.queue.processor.llm_queue") as mock_queue:
        with patch("app.llm.queue.auth_state.AuthStateManager") as mock_auth_manager:
            mock_auth_instance = MagicMock()
            mock_auth_manager.return_value = mock_auth_instance

            with pytest.raises(ClaudeNotAuthenticatedException):
                process_llm_job(sample_job, mock_provider)

            # Verify auth state was updated
            mock_auth_manager.assert_called_once()


def test_process_llm_job_claude_quota_exceeded_updates_state(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of Claude quota exceeded error updates state and raises."""
    from app.llm.providers.claude import ClaudeQuotaExceededException

    # Mock provider to raise quota exceeded error
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


def test_process_llm_job_other_errors_do_not_update_state(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test that non-Claude errors don't update auth state."""
    # Mock provider to raise generic error
    generic_error = ValueError("Something went wrong")
    mock_provider.generate.side_effect = generic_error

    with patch("app.llm.queue.auth_state.AuthStateManager") as mock_auth_manager:
        # Should raise the generic exception
        with pytest.raises(ValueError, match="Something went wrong"):
            process_llm_job(sample_job, mock_provider)

        # Auth manager should not be instantiated for generic errors
        mock_auth_manager.assert_not_called()


def test_process_llm_job_generic_exception(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test handling of generic exceptions."""
    # Mock provider to raise generic error
    generic_error = ValueError("Generic error")
    mock_provider.generate.side_effect = generic_error

    with pytest.raises(ValueError, match="Generic error"):
        process_llm_job(sample_job, mock_provider)


def test_process_llm_job_event_loop_cleanup(
    sample_job: LLMJob,
    mock_provider: MagicMock,
    sample_llm_response: LLMResponse,
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
                    with patch(
                        "app.content_store.config.get_content_store", return_value=None
                    ):
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
            with patch("app.content_store.config.get_content_store", return_value=None):
                result = process_llm_job(sample_job, mock_provider)

    assert result == sample_llm_response


def test_process_llm_job_invalid_json_retry_succeeds(
    sample_job: LLMJob, mock_provider: MagicMock, sample_llm_response: LLMResponse
) -> None:
    """Test that invalid JSON response triggers retry and eventually succeeds."""
    # Create invalid and valid responses
    invalid_response = LLMResponse(
        text="Invalid JSON response",  # Triggers retry
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        raw={},
    )
    
    # First call returns invalid, second returns valid
    async def mock_generate_invalid(*args: Any, **kwargs: Any) -> LLMResponse:
        return invalid_response
    
    async def mock_generate_valid(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response
    
    mock_provider.generate.side_effect = [
        mock_generate_invalid(),
        mock_generate_valid(),
    ]
    
    with patch("app.llm.queue.processor.reconciler_queue"):
        with patch("app.llm.queue.processor.recorder_queue"):
            with patch("app.content_store.config.get_content_store") as mock_store_factory:
                mock_store = MagicMock()
                mock_store_factory.return_value = mock_store
                with patch("time.sleep"):  # Mock sleep to speed up test
                    result = process_llm_job(sample_job, mock_provider)
    
    # Should have retried and gotten valid response
    assert result == sample_llm_response
    assert mock_provider.generate.call_count == 2


def test_process_llm_job_invalid_json_max_retries(
    sample_job: LLMJob, mock_provider: MagicMock
) -> None:
    """Test that consistently invalid JSON responses fail after max retries."""
    invalid_response = LLMResponse(
        text="Invalid JSON response",
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        raw={},
    )
    
    # Always return invalid JSON
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return invalid_response
    
    mock_provider.generate.side_effect = [
        mock_generate(),
        mock_generate(),
        mock_generate(),
    ]
    
    with patch("time.sleep"):  # Mock sleep to speed up test
        with pytest.raises(ValueError, match="Invalid JSON response.*after 3 attempts"):
            process_llm_job(sample_job, mock_provider)
    
    assert mock_provider.generate.call_count == 3


def test_process_llm_job_content_store_error(
    sample_job: LLMJob, mock_provider: MagicMock, sample_llm_response: LLMResponse
) -> None:
    """Test that content store errors don't fail the job."""
    # Add content_hash to metadata
    sample_job.metadata = {"content_hash": "abc123def456"}
    
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response
    
    mock_provider.generate.return_value = mock_generate()
    
    with patch("app.llm.queue.processor.reconciler_queue"):
        with patch("app.llm.queue.processor.recorder_queue"):
            with patch("app.content_store.config.get_content_store") as mock_store_factory:
                mock_store = MagicMock()
                # Content store throws an error
                mock_store.store_result.side_effect = Exception("Storage failed")
                mock_store_factory.return_value = mock_store
                
                # Should not raise, just log the error
                result = process_llm_job(sample_job, mock_provider)
    
    # Job should still succeed
    assert result == sample_llm_response
    mock_store.store_result.assert_called_once()


def test_process_llm_job_recorder_failure(
    sample_job: LLMJob, mock_provider: MagicMock, sample_llm_response: LLMResponse
) -> None:
    """Test that recorder enqueue failure doesn't fail the job."""
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response
    
    mock_provider.generate.return_value = mock_generate()
    
    with patch("app.llm.queue.processor.reconciler_queue"):
        with patch("app.llm.queue.processor.recorder_queue") as mock_recorder:
            with patch("app.content_store.config.get_content_store", return_value=None):
                # Recorder enqueue fails
                mock_recorder.enqueue_call.side_effect = Exception("Queue error")
                
                # Should not raise
                result = process_llm_job(sample_job, mock_provider)
    
    # Job should still succeed
    assert result == sample_llm_response
    mock_recorder.enqueue_call.assert_called_once()


def test_process_llm_job_reconciler_failure(
    sample_job: LLMJob, mock_provider: MagicMock, sample_llm_response: LLMResponse
) -> None:
    """Test that reconciler enqueue failure raises an error."""
    async def mock_generate(*args: Any, **kwargs: Any) -> LLMResponse:
        return sample_llm_response
    
    mock_provider.generate.return_value = mock_generate()
    
    with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler:
        with patch("app.llm.queue.processor.recorder_queue"):
            with patch("app.content_store.config.get_content_store", return_value=None):
                # Reconciler enqueue fails
                mock_reconciler.enqueue_call.side_effect = Exception("Queue error")
                
                # Should raise a ValueError
                with pytest.raises(ValueError, match="Failed to enqueue reconciler job"):
                    process_llm_job(sample_job, mock_provider)