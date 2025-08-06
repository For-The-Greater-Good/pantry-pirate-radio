"""Integration tests for queue TTL configuration."""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.queue.processor import process_llm_job
from app.llm.providers.types import LLMResponse


@pytest.fixture
def sample_llm_job() -> LLMJob:
    """Create a sample LLM job for testing."""
    return LLMJob(
        id=str(uuid4()),
        prompt="Test prompt for TTL testing",
        format={"type": "object", "properties": {"answer": {"type": "string"}}},
        created_at=datetime.now(),
    )


@pytest.fixture
def sample_llm_response() -> LLMResponse:
    """Create a sample LLM response for testing."""
    return LLMResponse(
        text="Test response for TTL testing",
        model="test-model",
        usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        raw={"test": "ttl_data"},
    )


@pytest.fixture
def mock_provider() -> MagicMock:
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.model_name = "test-model-ttl"
    return provider


@pytest.fixture
def no_content_store(monkeypatch):
    """Disable content store for testing."""
    monkeypatch.setenv("CONTENT_STORE_ENABLED", "false")
    yield


class TestQueueTTLConfiguration:
    """Test that queue operations use the configured TTL values."""

    def test_should_use_configured_ttl_for_reconciler_queue(
        self,
        sample_llm_job: LLMJob,
        mock_provider: MagicMock,
        sample_llm_response: LLMResponse,
        no_content_store,
    ):
        """Test that reconciler queue jobs use the configured TTL values."""
        # Arrange
        custom_ttl = 7200  # 2 hours

        # Mock generate method to return a coroutine that resolves to sample_llm_response
        async def mock_generate(*args, **kwargs):
            return sample_llm_response

        mock_provider.generate = mock_generate

        # Mock the queues to capture enqueue_call arguments
        with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler_queue:
            with patch("app.llm.queue.processor.recorder_queue"):
                with patch(
                    "app.llm.queue.processor.settings.REDIS_TTL_SECONDS", custom_ttl
                ):
                    # Act
                    process_llm_job(sample_llm_job, mock_provider)

                    # Assert
                    mock_reconciler_queue.enqueue_call.assert_called_once()
                    call_args = mock_reconciler_queue.enqueue_call.call_args
                    assert call_args[1]["result_ttl"] == custom_ttl
                    assert call_args[1]["failure_ttl"] == custom_ttl

    def test_should_use_configured_ttl_for_recorder_queue(
        self,
        sample_llm_job: LLMJob,
        mock_provider: MagicMock,
        sample_llm_response: LLMResponse,
        no_content_store,
    ):
        """Test that recorder queue jobs use the configured TTL values."""
        # Arrange
        custom_ttl = 10800  # 3 hours

        # Mock generate method to return a coroutine that resolves to sample_llm_response
        async def mock_generate(*args, **kwargs):
            return sample_llm_response

        mock_provider.generate = mock_generate

        # Mock the queues to capture enqueue_call arguments
        with patch("app.llm.queue.processor.reconciler_queue"):
            with patch("app.llm.queue.processor.recorder_queue") as mock_recorder_queue:
                with patch(
                    "app.llm.queue.processor.settings.REDIS_TTL_SECONDS", custom_ttl
                ):
                    # Act
                    process_llm_job(sample_llm_job, mock_provider)

                    # Assert
                    mock_recorder_queue.enqueue_call.assert_called_once()
                    call_args = mock_recorder_queue.enqueue_call.call_args
                    assert call_args[1]["result_ttl"] == custom_ttl
                    assert call_args[1]["failure_ttl"] == custom_ttl

    def test_should_use_default_ttl_when_environment_not_set(
        self,
        sample_llm_job: LLMJob,
        mock_provider: MagicMock,
        sample_llm_response: LLMResponse,
        no_content_store,
    ):
        """Test that queues use default TTL when environment variable not set."""
        # Arrange
        default_ttl = 2592000  # 30 days default

        # Mock generate method to return a coroutine that resolves to sample_llm_response
        async def mock_generate(*args, **kwargs):
            return sample_llm_response

        mock_provider.generate = mock_generate

        # Mock the queues to capture enqueue_call arguments
        with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler_queue:
            with patch("app.llm.queue.processor.recorder_queue") as mock_recorder_queue:
                # Act - should use the default TTL without any special patching
                process_llm_job(sample_llm_job, mock_provider)

                # Assert
                reconciler_call_args = mock_reconciler_queue.enqueue_call.call_args
                recorder_call_args = mock_recorder_queue.enqueue_call.call_args

                assert reconciler_call_args[1]["result_ttl"] == default_ttl
                assert reconciler_call_args[1]["failure_ttl"] == default_ttl
                assert recorder_call_args[1]["result_ttl"] == default_ttl
                assert recorder_call_args[1]["failure_ttl"] == default_ttl

    def test_should_use_configured_ttl_for_auth_errors(
        self,
        sample_llm_job: LLMJob,
        mock_provider: MagicMock,
        no_content_store,
    ):
        """Test that auth errors update auth state correctly."""
        # Arrange
        from app.llm.providers.claude import ClaudeNotAuthenticatedException

        # Mock Claude authentication error
        auth_error = ClaudeNotAuthenticatedException(
            "Not authenticated", retry_after=300
        )
        mock_provider.generate.side_effect = auth_error

        with patch("app.llm.queue.processor.llm_queue") as mock_queue:
            with patch(
                "app.llm.queue.auth_state.AuthStateManager"
            ) as mock_auth_manager:
                mock_auth_instance = MagicMock()
                mock_auth_manager.return_value = mock_auth_instance

                # Act - Should raise the exception
                with pytest.raises(ClaudeNotAuthenticatedException):
                    process_llm_job(sample_llm_job, mock_provider)

                # Assert - Verify auth state was updated
                mock_auth_manager.assert_called_once_with(mock_queue.connection)
                mock_auth_instance.set_auth_failed.assert_called_once_with(
                    "Not authenticated", retry_after=300
                )

    def test_should_use_configured_ttl_for_quota_errors(
        self,
        sample_llm_job: LLMJob,
        mock_provider: MagicMock,
        no_content_store,
    ):
        """Test that quota errors update auth state correctly."""
        # Arrange
        from app.llm.providers.claude import ClaudeQuotaExceededException

        # Mock Claude quota exceeded error
        quota_error = ClaudeQuotaExceededException("Quota exceeded", retry_after=3600)
        mock_provider.generate.side_effect = quota_error

        with patch("app.llm.queue.processor.llm_queue") as mock_queue:
            with patch(
                "app.llm.queue.auth_state.AuthStateManager"
            ) as mock_auth_manager:
                mock_auth_instance = MagicMock()
                mock_auth_manager.return_value = mock_auth_instance

                # Act - Should raise the exception
                with pytest.raises(ClaudeQuotaExceededException):
                    process_llm_job(sample_llm_job, mock_provider)

                # Assert - Verify quota state was updated
                mock_auth_manager.assert_called_once_with(mock_queue.connection)
                mock_auth_instance.set_quota_exceeded.assert_called_once_with(
                    "Quota exceeded", retry_after=3600
                )


class TestQueueTTLConsistency:
    """Test that TTL values are consistently applied across different queue operations."""

    def test_should_use_same_ttl_for_result_and_failure(
        self,
        sample_llm_job: LLMJob,
        mock_provider: MagicMock,
        sample_llm_response: LLMResponse,
        no_content_store,
    ):
        """Test that result_ttl and failure_ttl use the same configured value."""
        # Arrange
        custom_ttl = 21600  # 6 hours

        # Mock generate method to return a coroutine that resolves to sample_llm_response
        async def mock_generate(*args, **kwargs):
            return sample_llm_response

        mock_provider.generate = mock_generate

        # Mock the queues to capture enqueue_call arguments
        with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler_queue:
            with patch("app.llm.queue.processor.recorder_queue") as mock_recorder_queue:
                with patch(
                    "app.content_store.config.get_content_store", return_value=None
                ):
                    with patch(
                        "app.llm.queue.processor.settings.REDIS_TTL_SECONDS", custom_ttl
                    ):
                        # Act
                        process_llm_job(sample_llm_job, mock_provider)

                    # Assert
                    # Check reconciler queue
                    reconciler_args = mock_reconciler_queue.enqueue_call.call_args[1]
                    assert (
                        reconciler_args["result_ttl"]
                        == reconciler_args["failure_ttl"]
                        == custom_ttl
                    )

                    # Check recorder queue
                    recorder_args = mock_recorder_queue.enqueue_call.call_args[1]
                    assert (
                        recorder_args["result_ttl"]
                        == recorder_args["failure_ttl"]
                        == custom_ttl
                    )

    def test_should_handle_zero_ttl_configuration(
        self,
        sample_llm_job: LLMJob,
        mock_provider: MagicMock,
        sample_llm_response: LLMResponse,
        no_content_store,
    ):
        """Test that zero TTL (no expiration) is properly handled."""
        # Arrange
        zero_ttl = 0  # No expiration

        # Mock generate method to return a coroutine that resolves to sample_llm_response
        async def mock_generate(*args, **kwargs):
            return sample_llm_response

        mock_provider.generate = mock_generate

        # Mock the queues to capture enqueue_call arguments
        with patch("app.llm.queue.processor.reconciler_queue") as mock_reconciler_queue:
            with patch("app.llm.queue.processor.recorder_queue") as mock_recorder_queue:
                with patch(
                    "app.llm.queue.processor.settings.REDIS_TTL_SECONDS", zero_ttl
                ):
                    # Act
                    process_llm_job(sample_llm_job, mock_provider)

                    # Assert
                    reconciler_call_args = mock_reconciler_queue.enqueue_call.call_args
                    recorder_call_args = mock_recorder_queue.enqueue_call.call_args

                    assert reconciler_call_args[1]["result_ttl"] == zero_ttl
                    assert reconciler_call_args[1]["failure_ttl"] == zero_ttl
                    assert recorder_call_args[1]["result_ttl"] == zero_ttl
                    assert recorder_call_args[1]["failure_ttl"] == zero_ttl
