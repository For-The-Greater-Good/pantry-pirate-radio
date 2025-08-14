"""Tests for validator queue setup and configuration."""

from unittest.mock import MagicMock, patch, call

import pytest
from redis import Redis
from rq import Queue

from app.validator.queues import (
    validator_queue,
    get_validator_queue,
    setup_validator_queues,
    is_validator_enabled,
)


class TestValidatorQueueSetup:
    """Test validator queue setup and configuration."""

    def test_validator_queue_exists(self):
        """Test that validator_queue is properly defined."""
        assert validator_queue is not None
        assert isinstance(validator_queue, Queue)
        assert validator_queue.name == "validator"

    def test_get_validator_queue(self):
        """Test getting the validator queue."""
        queue = get_validator_queue()
        assert queue is not None
        assert isinstance(queue, Queue)
        assert queue.name == "validator"
        assert queue == validator_queue

    @patch("app.validator.queues.redis_pool")
    def test_validator_queue_uses_redis_pool(self, mock_redis_pool):
        """Test that validator queue uses the shared Redis connection pool."""
        from app.validator.queues import create_validator_queue
        
        queue = create_validator_queue()
        
        assert queue is not None
        # Should use the Redis pool
        mock_redis_pool.assert_called()

    def test_setup_validator_queues(self, mock_redis):
        """Test setting up validator queues."""
        with patch("app.validator.queues.Redis", return_value=mock_redis):
            queues = setup_validator_queues()
            
            assert "validator" in queues
            assert isinstance(queues["validator"], Queue)
            
            # Should also return reconciler queue for chaining
            assert "reconciler" in queues

    def test_validator_enabled_by_default(self):
        """Test that validator is enabled by default."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", True):
            assert is_validator_enabled() is True

    def test_validator_can_be_disabled(self):
        """Test that validator can be disabled via configuration."""
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            assert is_validator_enabled() is False

    @patch("app.validator.queues.redis_pool")
    def test_validator_queue_configuration(self, mock_redis_pool):
        """Test validator queue configuration settings."""
        from app.validator.queues import get_validator_queue_config
        
        config = get_validator_queue_config()
        
        assert config["name"] == "validator"
        assert config["default_timeout"] == "10m"  # 10 minutes default
        assert config["result_ttl"] == 3600  # 1 hour default
        assert config["failure_ttl"] == 86400  # 24 hours default

    def test_validator_queue_job_class(self):
        """Test that validator queue uses the correct job class."""
        from rq.job import Job
        
        assert validator_queue.job_class == Job

    def test_validator_queue_is_async(self):
        """Test that validator queue supports async operations."""
        # Validator queue should have is_async property
        assert hasattr(validator_queue, 'is_async')

    @patch("app.validator.queues.llm_queue")
    @patch("app.validator.queues.reconciler_queue")
    def test_queue_chain_configuration(self, mock_reconciler_queue, mock_llm_queue):
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

    @patch("app.core.config.settings")
    def test_validator_queue_redis_url(self, mock_settings):
        """Test that validator queue uses the correct Redis URL."""
        mock_settings.REDIS_URL = "redis://test-host:6379/0"
        
        from app.validator.queues import get_redis_connection
        
        with patch("redis.Redis.from_url") as mock_from_url:
            conn = get_redis_connection()
            mock_from_url.assert_called_with("redis://test-host:6379/0")

    def test_validator_queue_error_handling(self, mock_redis):
        """Test error handling in validator queue setup."""
        mock_redis.ping.side_effect = Exception("Connection failed")
        
        with patch("app.validator.queues.Redis", return_value=mock_redis):
            with pytest.raises(Exception) as exc_info:
                setup_validator_queues()
            
            assert "Connection failed" in str(exc_info.value)

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

    @patch("app.validator.queues.logger")
    def test_validator_queue_logging(self, mock_logger):
        """Test that validator queue setup logs appropriately."""
        from app.validator.queues import setup_validator_queues
        
        with patch("app.validator.queues.Redis"):
            setup_validator_queues()
            
            # Should log queue setup
            mock_logger.info.assert_called()
            calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("validator queue" in str(call).lower() for call in calls)