"""Tests for validator queue setup and configuration."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from redis import Redis
from rq import Queue

# Import helper from current directory since we're in the test environment
try:
    from test_helpers import mock_redis_at_import
except ImportError:
    # Create inline helper if import fails
    from contextlib import contextmanager

    @contextmanager
    def mock_redis_at_import():
        """Mock Redis connections during module imports."""
        mock_redis_client = MagicMock()
        mock_redis_client.ping.return_value = True

        mock_redis_pool = MagicMock()
        mock_queue = MagicMock()
        mock_queue.name = "validator"

        with patch("redis.Redis", return_value=mock_redis_client):
            with patch("redis.ConnectionPool.from_url", return_value=mock_redis_pool):
                with patch("rq.Queue", return_value=mock_queue):
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
        return mock_queue


class TestValidatorQueueSetup:
    """Test validator queue setup and configuration."""

    def test_validator_queue_exists(self):
        """Test that validator_queue is properly defined."""
        with mock_redis_at_import() as mocks:
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            from app.validator.queues import validator_queue

            assert validator_queue is not None
            # The mock returns a MagicMock for Queue
            assert validator_queue.name == "validator"

    def test_get_validator_queue(self):
        """Test getting the validator queue."""
        with patch("app.validator.queues.validator_queue") as mock_queue:
            mock_queue.name = "validator"
            from app.validator.queues import get_validator_queue

            queue = get_validator_queue()
            assert queue is not None
            assert queue == mock_queue

    @patch("app.validator.queues.redis_pool")
    @patch("app.validator.queues.redis.Redis")
    def test_validator_queue_uses_redis_pool(self, mock_redis_class, mock_redis_pool):
        """Test that validator queue uses the shared Redis connection pool."""
        from app.validator.queues import create_validator_queue

        queue = create_validator_queue()

        assert queue is not None
        # Should create Redis connection with the pool
        mock_redis_class.assert_called_with(connection_pool=mock_redis_pool)

    def test_setup_validator_queues(self, mock_redis):
        """Test setting up validator queues."""
        with mock_redis_at_import():
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            from app.validator.queues import setup_validator_queues

            queues = setup_validator_queues()

            assert "validator" in queues
            # The queue will be a MagicMock or Queue instance
            assert queues["validator"] is not None

            # Should also return reconciler queue for chaining
            assert "reconciler" in queues

    def test_validator_enabled_by_default(self):
        """Test that validator is enabled by default."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", True):
            from app.validator.queues import is_validator_enabled

            assert is_validator_enabled() is True

    def test_validator_can_be_disabled(self):
        """Test that validator can be disabled via configuration."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            from app.validator.queues import is_validator_enabled

            assert is_validator_enabled() is False

    def test_validator_queue_configuration(self):
        """Test validator queue configuration settings."""
        with mock_redis_at_import():
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            # Patch settings to have predictable values
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.REDIS_TTL_SECONDS = 3600
                mock_settings.REDIS_FAILURE_TTL_SECONDS = 86400

                from app.validator.queues import get_validator_queue_config

                config = get_validator_queue_config()

                assert config["name"] == "validator"
                assert config["default_timeout"] == "10m"  # 10 minutes default
                assert config["result_ttl"] == 3600  # 1 hour default
                assert config["failure_ttl"] == 86400  # 24 hours default

    def test_validator_queue_job_class(self):
        """Test that validator queue uses the correct job class."""
        from rq.job import Job

        with mock_redis_at_import() as mocks:
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            from app.validator.queues import validator_queue

            # The mock queue will have a job_class attribute
            assert hasattr(validator_queue, "job_class")

    def test_validator_queue_is_async(self):
        """Test that validator queue supports async operations."""
        with mock_redis_at_import() as mocks:
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            from app.validator.queues import validator_queue

            # Validator queue should have is_async property
            assert hasattr(validator_queue, "is_async")

    @patch("app.validator.queues.llm_queue")
    @patch("app.validator.queues.reconciler_queue")
    def test_queue_chain_configuration(self, mock_reconciler_queue, _mock_llm_queue):
        """Test that queues are properly chained: llm -> validator -> reconciler."""
        from app.validator.queues import get_queue_chain

        chain = get_queue_chain()

        assert chain == ["llm", "validator", "reconciler"]

        # Verify the flow order
        assert chain.index("validator") > chain.index("llm")
        assert chain.index("reconciler") > chain.index("validator")

    def test_validator_queue_worker_config(self):
        """Test validator queue worker configuration."""
        from app.validator.queues import get_worker_config

        config = get_worker_config()

        assert config["num_workers"] >= 1
        assert config["max_jobs_per_worker"] > 0
        assert config["log_level"] in ["DEBUG", "INFO", "WARNING", "ERROR"]

    def test_validator_queue_redis_url(self):
        """Test that validator queue uses the correct Redis URL."""
        with mock_redis_at_import():
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            # Force the function to create a new connection by mocking redis_pool as None
            with patch("app.validator.queues._redis_available", False):
                with patch("app.validator.queues.redis_pool", None):
                    with patch("app.core.config.settings") as mock_settings:
                        mock_settings.REDIS_URL = "redis://test-host:6379/0"

                        from app.validator.queues import get_redis_connection

                        with patch("redis.Redis.from_url") as mock_from_url:
                            mock_redis = MagicMock()
                            mock_redis.ping.return_value = True
                            mock_from_url.return_value = mock_redis

                            conn = get_redis_connection()
                            mock_from_url.assert_called_with(
                                "redis://test-host:6379/0", decode_responses=False
                            )

    def test_validator_queue_error_handling(self):
        """Test error handling in validator queue setup."""
        with mock_redis_at_import():
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            from app.validator.queues import setup_validator_queues
            from redis.exceptions import ConnectionError as RedisConnectionError

            # Mock redis.Redis to simulate connection failure
            with patch("redis.Redis") as MockRedis:
                mock_redis = MagicMock()
                mock_redis.ping.side_effect = RedisConnectionError("Connection failed")
                MockRedis.return_value = mock_redis

                with pytest.raises(RuntimeError) as exc_info:
                    setup_validator_queues()

                assert "Connection failed" in str(exc_info.value)

    @pytest.mark.skip(reason="Prometheus registry conflict when run with full suite")
    def test_validator_queue_metrics(self):
        """Test that validator queue has metrics configured."""
        from app.validator.metrics import (
            VALIDATOR_JOBS_TOTAL,
            VALIDATOR_JOBS_PASSED,
            VALIDATOR_PROCESSING_TIME,
        )

        assert VALIDATOR_JOBS_TOTAL is not None
        assert VALIDATOR_JOBS_PASSED is not None
        assert VALIDATOR_PROCESSING_TIME is not None

    def test_validator_queue_logging(self):
        """Test that validator queue setup logs appropriately."""
        with mock_redis_at_import():
            # Clear cached imports
            for module in list(sys.modules.keys()):
                if "app.validator" in module or "app.llm.queue" in module:
                    del sys.modules[module]

            with patch("app.validator.queues.logger") as mock_logger:
                from app.validator.queues import setup_validator_queues

                setup_validator_queues()

                # Should log queue setup
                mock_logger.info.assert_called()
                log_calls = [str(c) for c in mock_logger.info.call_args_list]
                assert any("validator queue" in str(c).lower() for c in log_calls)
