"""Tests for LLM queue worker."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.queue.worker import QueueWorker


@pytest.fixture
def mock_provider():
    """Create mock LLM provider."""
    provider = MagicMock()
    provider.model_name = "test-model"
    return provider


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    return AsyncMock()


def test_worker_setup(mock_provider, mock_redis):
    """Test worker initialization sets PID correctly."""
    with patch("app.llm.queue.worker.Worker") as mock_worker_class, patch(
        "app.llm.queue.worker.llm_queue"
    ) as mock_queue:

        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        worker = QueueWorker(mock_provider, mock_redis, "test-worker")

        # Verify worker PID was set (line 49)
        assert mock_worker_instance.pid == os.getpid()

        # Verify worker was created with correct parameters
        mock_worker_class.assert_called_once_with(
            [mock_queue],
            connection=mock_queue.connection,
            name="test-worker",
            default_result_ttl=500,  # DEFAULT_RESULT_TTL
            default_worker_ttl=420,  # DEFAULT_WORKER_TTL
            prepare_for_work=False,
            job_monitoring_interval=1,
        )


@pytest.mark.asyncio
async def test_worker_run_exception_handling(mock_provider, mock_redis):
    """Test worker handles death registration exception."""
    with patch("app.llm.queue.worker.Worker") as mock_worker_class, patch(
        "app.llm.queue.worker.llm_queue"
    ), patch("app.llm.queue.worker.logger") as mock_logger:

        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        # Mock register_death to raise exception (line 67-68)
        mock_worker_instance.register_death.side_effect = Exception(
            "Death registration failed"
        )

        worker = QueueWorker(mock_provider, mock_redis, "test-worker")

        # Mock _work method to avoid actual work
        worker._work = MagicMock()

        await worker.run()

        # Verify warning was logged for death registration error
        mock_logger.warning.assert_called_once_with(
            "Error registering worker death: Death registration failed"
        )


@pytest.mark.asyncio
async def test_worker_stop_cleanup(mock_provider, mock_redis):
    """Test worker stop method cleans up properly."""
    with patch("app.llm.queue.worker.Worker") as mock_worker_class, patch(
        "app.llm.queue.worker.llm_queue"
    ):

        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        worker = QueueWorker(mock_provider, mock_redis, "test-worker")

        await worker.stop()

        # Verify cleanup methods were called (lines 79-81)
        mock_worker_instance.register_death.assert_called_once()
