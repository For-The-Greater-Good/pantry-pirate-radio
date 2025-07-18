"""Tests for LLM queue initialization."""

from unittest.mock import patch, MagicMock

import pytest
import redis


class TestQueueInitialization:
    """Test queue initialization and error handling."""

    @patch.dict("os.environ", {"REDIS_URL": "redis://test:6379/0"}, clear=False)
    @patch("app.llm.queue.queues.redis.Redis.from_url")
    def test_redis_connection_failure(self, mock_redis_from_url):
        """Test queue initialization when Redis connection fails."""
        # Mock Redis client that fails to ping
        mock_client = MagicMock()
        mock_client.ping.side_effect = redis.ConnectionError("Connection failed")
        mock_redis_from_url.return_value = mock_client

        # This should raise an exception during module import
        with pytest.raises(redis.ConnectionError):
            # Force reimport to trigger connection logic
            import importlib
            import app.llm.queue.queues

            importlib.reload(app.llm.queue.queues)

    @patch.dict("os.environ", {"REDIS_URL": "redis://test:6379/0"}, clear=False)
    @patch("app.llm.queue.queues.redis.Redis.from_url")
    def test_redis_connection_success(self, mock_redis_from_url):
        """Test successful queue initialization."""
        # Mock successful Redis client
        mock_client = MagicMock()
        mock_client.ping.return_value = True  # Successful ping
        mock_redis_from_url.return_value = mock_client

        # Force reimport to trigger connection logic
        import importlib
        import app.llm.queue.queues

        importlib.reload(app.llm.queue.queues)

        # Verify ping was called
        mock_client.ping.assert_called_once()

        # Verify connection was established
        assert app.llm.queue.queues.connection == mock_client

    def test_queue_objects_exist(self):
        """Test that queue objects are properly created."""
        from app.llm.queue.queues import (
            llm_queue,
            reconciler_queue,
            recorder_queue,
            QueueType,
        )
        from rq import Queue

        # Check that queues are Queue instances
        assert isinstance(llm_queue, Queue)
        assert isinstance(reconciler_queue, Queue)
        assert isinstance(recorder_queue, Queue)

        # Check queue names
        assert llm_queue.name == "llm"
        assert reconciler_queue.name == "reconciler"
        assert recorder_queue.name == "recorder"

        # Check QueueType alias
        assert QueueType == Queue
