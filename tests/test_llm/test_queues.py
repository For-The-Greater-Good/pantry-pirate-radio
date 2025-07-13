"""Tests for RQ queue definitions."""

import sys
import pytest
from unittest.mock import MagicMock, patch


def test_redis_connection_failure():
    """Test Redis connection failure handling."""
    # Remove module from cache if it exists
    if "app.llm.queue.queues" in sys.modules:
        del sys.modules["app.llm.queue.queues"]

    with patch("redis.Redis") as mock_redis_class, patch("os.getenv") as mock_getenv:

        # Mock environment
        mock_getenv.return_value = "redis://cache:6379/0"

        # Mock Redis client that fails ping
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("Connection failed")
        mock_redis_class.from_url.return_value = mock_client

        # This should raise the exception from the queues module
        with pytest.raises(ConnectionError, match="Connection failed"):
            import app.llm.queue.queues


def test_redis_url_configuration():
    """Test Redis URL configuration from environment."""
    # Remove module from cache if it exists
    if "app.llm.queue.queues" in sys.modules:
        del sys.modules["app.llm.queue.queues"]

    with patch("redis.Redis") as mock_redis_class, patch("os.getenv") as mock_getenv:

        # Mock environment variable
        mock_getenv.return_value = "redis://custom:6379/1"

        # Mock successful Redis client
        mock_client = MagicMock()
        mock_redis_class.from_url.return_value = mock_client

        # Import the module to trigger the configuration
        import app.llm.queue.queues

        # Verify Redis was configured with custom URL
        mock_redis_class.from_url.assert_called_with(
            "redis://custom:6379/1",
            decode_responses=False,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
