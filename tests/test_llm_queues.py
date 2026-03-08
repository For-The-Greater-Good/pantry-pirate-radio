"""Tests for LLM queue initialization."""

import importlib
import os
from unittest.mock import patch, MagicMock

import pytest
import redis


@pytest.fixture(autouse=True)
def _restore_queue_modules():
    """Restore real Redis connections after each test.

    Tests that reload app.llm.queue.queues under mocked Redis leave
    module-level queue objects holding mock connections. This fixture
    reloads the modules after each test (once patches are cleaned up)
    to prevent contamination of downstream tests.
    """
    original_redis_url = os.environ.get("REDIS_URL")
    yield
    if original_redis_url is not None:
        os.environ["REDIS_URL"] = original_redis_url
    else:
        os.environ.pop("REDIS_URL", None)
    try:
        import app.llm.queue.queues

        importlib.reload(app.llm.queue.queues)
    except Exception:  # noqa: S110
        pass
    try:
        import app.validator.queues

        importlib.reload(app.validator.queues)
    except Exception:  # noqa: S110
        pass


class TestQueueInitialization:
    """Test queue initialization and error handling."""

    def test_redis_connection_failure(self):
        """Test queue initialization when Redis connection fails."""
        mock_pool = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = redis.ConnectionError("Connection failed")

        with patch.dict("os.environ", {"REDIS_URL": "redis://test:6379/0"}):
            with patch.object(redis.ConnectionPool, "from_url", return_value=mock_pool):
                with patch.object(redis, "Redis", return_value=mock_client):
                    with pytest.raises(redis.ConnectionError):
                        import app.llm.queue.queues

                        importlib.reload(app.llm.queue.queues)

    def test_redis_connection_success(self):
        """Test successful queue initialization."""
        mock_pool = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch.dict("os.environ", {"REDIS_URL": "redis://test:6379/0"}):
            with patch.object(redis.ConnectionPool, "from_url", return_value=mock_pool):
                with patch.object(redis, "Redis", return_value=mock_client):
                    import app.llm.queue.queues

                    importlib.reload(app.llm.queue.queues)

                    mock_client.ping.assert_called_once()

    def test_queue_objects_exist(self):
        """Test that queue objects are properly created."""
        from app.llm.queue.queues import (
            llm_queue,
            reconciler_queue,
            recorder_queue,
            QueueType,
        )
        from rq import Queue

        assert isinstance(llm_queue, Queue)
        assert isinstance(reconciler_queue, Queue)
        assert isinstance(recorder_queue, Queue)

        assert llm_queue.name == "llm"
        assert reconciler_queue.name == "reconciler"
        assert recorder_queue.name == "recorder"

        assert QueueType == Queue
