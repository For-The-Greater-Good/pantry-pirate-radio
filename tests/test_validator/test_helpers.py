"""Helper utilities for validator tests."""

import sys
from unittest.mock import MagicMock, patch
from contextlib import contextmanager


@contextmanager
def mock_redis_at_import():
    """Mock Redis connections during module imports.

    This context manager prevents Redis connection attempts during imports
    by mocking the redis module before any validator modules are imported.
    """
    # Create mock Redis objects
    mock_redis_client = MagicMock()
    mock_redis_client.ping.return_value = True

    mock_redis_pool = MagicMock()
    mock_redis_class = MagicMock()
    mock_redis_class.return_value = mock_redis_client

    mock_queue = MagicMock()
    mock_queue.name = "validator"

    # Mock the redis module
    with patch.dict(
        "sys.modules",
        {"redis": MagicMock(Redis=mock_redis_class, ConnectionPool=MagicMock())},
    ):
        with patch("redis.Redis", mock_redis_class):
            with patch("redis.ConnectionPool.from_url", return_value=mock_redis_pool):
                # Mock RQ Queue
                with patch("rq.Queue", return_value=mock_queue):
                    # Clear any cached imports
                    if "app.llm.queue.queues" in sys.modules:
                        del sys.modules["app.llm.queue.queues"]
                    if "app.validator.queues" in sys.modules:
                        del sys.modules["app.validator.queues"]
                    if "app.validator.job_processor" in sys.modules:
                        del sys.modules["app.validator.job_processor"]

                    yield {
                        "redis_client": mock_redis_client,
                        "redis_pool": mock_redis_pool,
                        "queue": mock_queue,
                    }


def create_mock_validator_queue():
    """Create a mock validator queue for testing."""
    mock_queue = MagicMock()
    mock_queue.name = "validator"
    mock_queue.is_async = True
    mock_queue.default_timeout = "10m"
    mock_queue.job_class = MagicMock()
    mock_queue.enqueue_call = MagicMock(return_value=MagicMock(id="test-job-id"))
    return mock_queue


def create_mock_redis_connection():
    """Create a mock Redis connection for testing."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    return mock_redis
