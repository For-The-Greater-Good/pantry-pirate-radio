"""Tests for RQ queue definitions."""

import sys
import pytest
from unittest.mock import MagicMock, patch


def test_redis_connection_failure():
    """Test Redis connection failure handling and error logging."""
    # Remove module from cache if it exists
    if "app.llm.queue.queues" in sys.modules:
        del sys.modules["app.llm.queue.queues"]

    with patch("redis.ConnectionPool.from_url") as mock_pool_from_url:
        with patch("redis.Redis") as mock_redis_class:
            with patch("logging.getLogger") as mock_get_logger:
                # Mock logger
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger

                # Mock connection pool
                mock_pool = MagicMock()
                mock_pool_from_url.return_value = mock_pool

                # Mock Redis client that fails ping
                mock_client = MagicMock()
                mock_client.ping.side_effect = ConnectionError("Connection failed")
                mock_redis_class.return_value = mock_client

                # This should raise the exception from the queues module
                with pytest.raises(ConnectionError):
                    import app.llm.queue.queues

                # Verify error was logged
                mock_logger.error.assert_called_once()


def test_redis_url_configuration():
    """Test Redis URL configuration from environment."""
    # Remove module from cache if it exists
    if "app.llm.queue.queues" in sys.modules:
        del sys.modules["app.llm.queue.queues"]

    with patch("os.getenv") as mock_getenv:
        with patch("redis.ConnectionPool.from_url") as mock_pool_from_url:
            with patch("redis.Redis") as mock_redis_class:
                # Mock environment variable
                mock_getenv.return_value = "redis://custom:6379/1"

                # Mock connection pool
                mock_pool = MagicMock()
                mock_pool_from_url.return_value = mock_pool

                # Mock successful Redis client
                mock_client = MagicMock()
                mock_client.ping.return_value = True
                mock_redis_class.return_value = mock_client

                # Import the module to trigger the configuration
                import app.llm.queue.queues

                # Verify ConnectionPool was configured with custom URL
                mock_pool_from_url.assert_called_with(
                    "redis://custom:6379/1",
                    max_connections=50,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
