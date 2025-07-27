"""Tests for application configuration settings."""

import os
from unittest.mock import patch

import pytest

from app.core.config import Settings


class TestRedisConfigurationSettings:
    """Test Redis TTL configuration settings."""

    def test_should_have_correct_default_redis_ttl_seconds(self):
        """Test REDIS_TTL_SECONDS has correct default value."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.REDIS_TTL_SECONDS == 2592000  # 30 days

    def test_should_override_redis_ttl_via_environment(self):
        """Test REDIS_TTL_SECONDS can be overridden via environment."""
        # Arrange
        custom_ttl = 86400  # 24 hours

        # Act
        with patch.dict(os.environ, {"REDIS_TTL_SECONDS": str(custom_ttl)}):
            settings = Settings()

        # Assert
        assert settings.REDIS_TTL_SECONDS == custom_ttl

    def test_should_accept_zero_redis_ttl_seconds(self):
        """Test REDIS_TTL_SECONDS accepts zero value (no expiration)."""
        # Arrange & Act
        with patch.dict(os.environ, {"REDIS_TTL_SECONDS": "0"}):
            settings = Settings()

        # Assert
        assert settings.REDIS_TTL_SECONDS == 0

    def test_should_accept_large_redis_ttl_seconds(self):
        """Test REDIS_TTL_SECONDS accepts large values."""
        # Arrange
        large_ttl = 31536000  # 1 year

        # Act
        with patch.dict(os.environ, {"REDIS_TTL_SECONDS": str(large_ttl)}):
            settings = Settings()

        # Assert
        assert settings.REDIS_TTL_SECONDS == large_ttl

    def test_should_raise_validation_error_for_invalid_redis_ttl(self):
        """Test REDIS_TTL_SECONDS raises error for invalid values."""
        # Arrange & Act & Assert
        with patch.dict(os.environ, {"REDIS_TTL_SECONDS": "invalid_value"}):
            with pytest.raises(ValueError):
                Settings()

    def test_should_raise_validation_error_for_negative_redis_ttl(self):
        """Test REDIS_TTL_SECONDS raises error for negative values."""
        # Arrange & Act & Assert
        with patch.dict(os.environ, {"REDIS_TTL_SECONDS": "-1"}):
            with pytest.raises(ValueError):
                Settings()


class TestSettingsGeneralBehavior:
    """Test general Settings class behavior with Redis TTL."""

    def test_should_maintain_default_settings_when_redis_ttl_not_specified(self):
        """Test that other settings remain unchanged when REDIS_TTL_SECONDS is default."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.app_name == "Pantry Pirate Radio"
        assert settings.version == "0.1.0"
        assert settings.REDIS_TTL_SECONDS == 2592000
        # Don't check REDIS_URL as it may be overridden by environment

    def test_should_maintain_settings_when_redis_ttl_overridden(self):
        """Test that other settings remain unchanged when REDIS_TTL_SECONDS is overridden."""
        # Arrange & Act
        with patch.dict(os.environ, {"REDIS_TTL_SECONDS": "7200"}):
            settings = Settings()

        # Assert
        assert settings.app_name == "Pantry Pirate Radio"
        assert settings.version == "0.1.0"
        assert settings.REDIS_TTL_SECONDS == 7200
        # Don't check REDIS_URL as it may be overridden by environment

    def test_should_handle_multiple_environment_overrides(self):
        """Test settings work correctly with multiple environment variables."""
        # Arrange
        env_vars = {
            "REDIS_TTL_SECONDS": "3600",
            "REDIS_URL": "redis://custom:6379/1",
            "LOG_LEVEL": "DEBUG",
        }

        # Act
        with patch.dict(os.environ, env_vars):
            settings = Settings()

        # Assert
        assert settings.REDIS_TTL_SECONDS == 3600
        assert settings.REDIS_URL == "redis://custom:6379/1"
        assert settings.LOG_LEVEL == "DEBUG"
