"""Tests for validator service configuration."""

import os
from unittest.mock import patch, MagicMock

import pytest

from app.validator.config import (
    ValidatorConfig,
    get_validator_config,
    is_validator_enabled,
    should_log_data_flow,
    get_validation_thresholds,
)


class TestValidatorConfiguration:
    """Test validator service configuration."""

    def test_validator_config_defaults(self):
        """Test default validator configuration values."""
        config = ValidatorConfig()

        assert config.enabled is True  # Enabled by default
        assert config.queue_name == "validator"
        assert config.redis_ttl == 3600  # 1 hour
        assert config.log_data_flow is False  # Don't log by default for performance
        assert config.only_hsds is True  # Only validate HSDS jobs by default
        assert config.confidence_threshold == 0.7  # 70% confidence threshold

    @patch.dict(os.environ, {}, clear=True)  # Clear environment variables
    def test_validator_config_from_settings(self):
        """Test loading validator config from settings."""
        # Use MagicMock which automatically handles hasattr
        mock_settings = MagicMock()
        mock_settings.VALIDATOR_ENABLED = False
        mock_settings.VALIDATOR_QUEUE_NAME = "custom_validator"
        mock_settings.VALIDATOR_REDIS_TTL = 7200
        mock_settings.VALIDATOR_LOG_DATA_FLOW = True
        mock_settings.VALIDATOR_ONLY_HSDS = False
        mock_settings.VALIDATOR_CONFIDENCE_THRESHOLD = 0.8
        mock_settings.VALIDATOR_MAX_RETRIES = 5
        mock_settings.VALIDATOR_RETRY_DELAY = 2
        mock_settings.VALIDATOR_BATCH_SIZE = 50
        mock_settings.VALIDATOR_TIMEOUT = 300

        # Patch where settings is imported inside get_validator_config
        with patch("app.core.config.settings", mock_settings):
            config = get_validator_config()

            assert config.enabled is False
            assert config.queue_name == "custom_validator"
            assert config.redis_ttl == 7200
            assert config.log_data_flow is True
            assert config.only_hsds is False
            assert config.confidence_threshold == 0.8
            assert config.max_retries == 5
            assert config.retry_delay == 2
            assert config.batch_size == 50
            assert config.timeout == 300

    @patch.dict(os.environ, {}, clear=True)  # Clear environment variables
    def test_is_validator_enabled(self):
        """Test checking if validator is enabled."""
        # Test with enabled = True
        mock_settings = MagicMock()
        mock_settings.VALIDATOR_ENABLED = True
        # Set all other required attributes to defaults
        mock_settings.VALIDATOR_QUEUE_NAME = "validator"
        mock_settings.VALIDATOR_REDIS_TTL = 3600
        mock_settings.VALIDATOR_LOG_DATA_FLOW = False
        mock_settings.VALIDATOR_ONLY_HSDS = True
        mock_settings.VALIDATOR_CONFIDENCE_THRESHOLD = 0.7
        mock_settings.VALIDATOR_MAX_RETRIES = 3
        mock_settings.VALIDATOR_RETRY_DELAY = 1
        mock_settings.VALIDATOR_BATCH_SIZE = 100
        mock_settings.VALIDATOR_TIMEOUT = 600

        with patch("app.core.config.settings", mock_settings):
            assert is_validator_enabled() is True

        # Test with enabled = False
        mock_settings = MagicMock()
        mock_settings.VALIDATOR_ENABLED = False
        # Set all other required attributes to defaults
        mock_settings.VALIDATOR_QUEUE_NAME = "validator"
        mock_settings.VALIDATOR_REDIS_TTL = 3600
        mock_settings.VALIDATOR_LOG_DATA_FLOW = False
        mock_settings.VALIDATOR_ONLY_HSDS = True
        mock_settings.VALIDATOR_CONFIDENCE_THRESHOLD = 0.7
        mock_settings.VALIDATOR_MAX_RETRIES = 3
        mock_settings.VALIDATOR_RETRY_DELAY = 1
        mock_settings.VALIDATOR_BATCH_SIZE = 100
        mock_settings.VALIDATOR_TIMEOUT = 600

        with patch("app.core.config.settings", mock_settings):
            assert is_validator_enabled() is False

    @patch.dict(os.environ, {}, clear=True)  # Clear environment variables
    def test_should_log_data_flow(self):
        """Test checking if data flow logging is enabled."""
        # Test with log_data_flow = True
        mock_settings = MagicMock()
        mock_settings.VALIDATOR_LOG_DATA_FLOW = True
        # Set all other required attributes to defaults
        mock_settings.VALIDATOR_ENABLED = True
        mock_settings.VALIDATOR_QUEUE_NAME = "validator"
        mock_settings.VALIDATOR_REDIS_TTL = 3600
        mock_settings.VALIDATOR_ONLY_HSDS = True
        mock_settings.VALIDATOR_CONFIDENCE_THRESHOLD = 0.7
        mock_settings.VALIDATOR_MAX_RETRIES = 3
        mock_settings.VALIDATOR_RETRY_DELAY = 1
        mock_settings.VALIDATOR_BATCH_SIZE = 100
        mock_settings.VALIDATOR_TIMEOUT = 600

        with patch("app.core.config.settings", mock_settings):
            assert should_log_data_flow() is True

        # Test with log_data_flow = False
        mock_settings = MagicMock()
        mock_settings.VALIDATOR_LOG_DATA_FLOW = False
        # Set all other required attributes to defaults
        mock_settings.VALIDATOR_ENABLED = True
        mock_settings.VALIDATOR_QUEUE_NAME = "validator"
        mock_settings.VALIDATOR_REDIS_TTL = 3600
        mock_settings.VALIDATOR_ONLY_HSDS = True
        mock_settings.VALIDATOR_CONFIDENCE_THRESHOLD = 0.7
        mock_settings.VALIDATOR_MAX_RETRIES = 3
        mock_settings.VALIDATOR_RETRY_DELAY = 1
        mock_settings.VALIDATOR_BATCH_SIZE = 100
        mock_settings.VALIDATOR_TIMEOUT = 600

        with patch("app.core.config.settings", mock_settings):
            assert should_log_data_flow() is False

    def test_get_validation_thresholds(self):
        """Test getting validation thresholds."""
        thresholds = get_validation_thresholds()

        assert "confidence" in thresholds
        assert "geocoding_accuracy" in thresholds
        assert "data_completeness" in thresholds

        assert 0 <= thresholds["confidence"] <= 1
        assert thresholds["geocoding_accuracy"] > 0
        assert 0 <= thresholds["data_completeness"] <= 1

    def test_validator_config_validation(self):
        """Test that validator config validates input."""
        # Valid config
        config = ValidatorConfig(enabled=True, confidence_threshold=0.5, redis_ttl=3600)
        assert config.confidence_threshold == 0.5

        # Invalid confidence threshold (should raise error or clamp)
        with pytest.raises(ValueError):
            ValidatorConfig(confidence_threshold=1.5)  # > 1.0

        with pytest.raises(ValueError):
            ValidatorConfig(confidence_threshold=-0.1)  # < 0.0

    def test_validator_config_environment_override(self):
        """Test that environment variables override defaults."""
        import os

        # Set environment variables
        os.environ["VALIDATOR_ENABLED"] = "false"
        os.environ["VALIDATOR_CONFIDENCE_THRESHOLD"] = "0.9"

        try:
            config = get_validator_config()
            assert config.enabled is False
            assert config.confidence_threshold == 0.9
        finally:
            # Clean up
            del os.environ["VALIDATOR_ENABLED"]
            del os.environ["VALIDATOR_CONFIDENCE_THRESHOLD"]

    def test_validator_config_json_serialization(self):
        """Test that validator config can be serialized to JSON."""
        config = ValidatorConfig()
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert "enabled" in config_dict
        assert "queue_name" in config_dict
        assert "confidence_threshold" in config_dict

        # Should be JSON serializable
        import json

        json_str = json.dumps(config_dict)
        assert json_str is not None

    def test_validator_feature_flags(self):
        """Test validator feature flags."""
        from app.validator.config import get_feature_flags

        flags = get_feature_flags()

        assert "validate_geocoding" in flags
        assert "validate_phone_numbers" in flags
        assert "validate_schedules" in flags
        assert "validate_services" in flags

        # All flags should be boolean
        for _, value in flags.items():
            assert isinstance(value, bool)

    def test_validator_queue_config(self):
        """Test validator queue-specific configuration."""
        from app.validator.config import get_queue_config

        config = get_queue_config()

        assert "name" in config
        assert "connection" in config
        assert "default_timeout" in config
        assert "result_ttl" in config
        assert "failure_ttl" in config
        assert "max_jobs" in config

        assert config["name"] == "validator"
        assert config["default_timeout"] == "600s"  # 10 minutes (600 seconds)
        assert config["result_ttl"] >= 3600  # At least 1 hour
        assert config["failure_ttl"] >= 86400  # At least 24 hours

    def test_validator_worker_config(self):
        """Test validator worker configuration."""
        from app.validator.config import get_worker_config

        config = get_worker_config()

        assert "num_workers" in config
        assert "max_jobs_per_worker" in config
        assert "log_level" in config
        assert "burst_mode" in config

        assert config["num_workers"] >= 1
        assert config["max_jobs_per_worker"] > 0
        assert config["log_level"] in ["DEBUG", "INFO", "WARNING", "ERROR"]

    def test_validator_pipeline_config(self):
        """Test pipeline configuration with validator."""
        from app.validator.config import get_pipeline_config

        # With validator enabled
        with patch("app.core.config.settings.VALIDATOR_ENABLED", True):
            config = get_pipeline_config()
            assert config["stages"] == ["scraper", "llm", "validator", "reconciler"]
            assert config["stage_configs"]["validator"]["enabled"] is True

        # With validator disabled
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False):
            config = get_pipeline_config()
            assert config["stages"] == ["scraper", "llm", "reconciler"]
            assert "validator" not in config["stages"]
