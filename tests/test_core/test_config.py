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

        # Act - clear existing env vars and set new ones
        with patch.dict(os.environ, env_vars, clear=True):
            # Re-add required vars that Settings might need
            os.environ["DATABASE_URL"] = "postgresql://user:password@localhost/db"
            settings = Settings()

        # Assert
        assert settings.REDIS_TTL_SECONDS == 3600
        assert settings.REDIS_URL == "redis://custom:6379/1"
        assert settings.LOG_LEVEL == "DEBUG"


class TestCORSValidation:
    """Test CORS origin validation in Settings."""

    def test_should_replace_wildcard_with_defaults(self):
        """Test that wildcard CORS origins are replaced with defaults."""
        # Arrange & Act
        settings = Settings(cors_origins=["*"])

        # Assert - the validator should replace ["*"] with localhost defaults
        assert settings.cors_origins == [
            "http://localhost",
            "http://localhost:8000",
            "http://localhost:3000",
        ]

    def test_should_keep_custom_cors_origins(self):
        """Test that custom CORS origins are preserved."""
        # Arrange
        custom_origins = ["https://example.com", "https://api.example.com"]

        # Act
        settings = Settings(cors_origins=custom_origins)

        # Assert
        assert settings.cors_origins == custom_origins


class TestTestEnvironmentConfiguration:
    """Test test environment configuration logic."""

    def test_should_use_provided_test_database_url(self):
        """Test that TEST_DATABASE_URL is used when provided."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "true",
                "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                "TEST_DATABASE_URL": "postgresql://user:pass@localhost/custom_test",
            },
            clear=True,  # Clear environment to control all variables
        ):
            settings = Settings()

        # Assert - should use the provided TEST_DATABASE_URL
        assert settings.DATABASE_URL == "postgresql://user:pass@localhost/custom_test"

    def test_should_use_provided_test_redis_url(self):
        """Test that TEST_REDIS_URL is used when provided."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "true",
                "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                "REDIS_URL": "redis://localhost:6379/0",
                "TEST_REDIS_URL": "redis://localhost:6379/5",
            },
            clear=True,
        ):
            settings = Settings()

        # Assert - should use the provided TEST_REDIS_URL
        assert settings.REDIS_URL == "redis://localhost:6379/5"

    def test_should_not_modify_urls_when_testing_false(self):
        """Test that URLs are not modified when TESTING is not true."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "false",
                "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                "REDIS_URL": "redis://localhost:6379/0",
            },
            clear=True,
        ):
            settings = Settings()

        # Assert - should not modify URLs
        assert "test_" not in settings.DATABASE_URL
        assert settings.REDIS_URL == "redis://localhost:6379/0"

    def test_should_handle_redis_url_without_database(self):
        """Test Redis URL without database specification when TESTING=true."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "true",
                "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                "REDIS_URL": "redis://localhost:6379",
            },
            clear=True,
        ):
            settings = Settings()

        # Assert - should add /1
        assert settings.REDIS_URL == "redis://localhost:6379/1"

    def test_should_handle_redis_url_with_trailing_slash(self):
        """Test Redis URL with trailing slash when TESTING=true."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "true",
                "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                "REDIS_URL": "redis://localhost:6379/",
            },
            clear=True,
        ):
            settings = Settings()

        # Assert - should add 1 after slash
        assert settings.REDIS_URL == "redis://localhost:6379/1"

    def test_should_not_double_prefix_test_database(self):
        """Test that test_ prefix is not added twice."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "true",
                "DATABASE_URL": "postgresql://user:pass@localhost/test_mydb",
                "REDIS_URL": "redis://localhost:6379/0",
            },
            clear=True,
        ):
            settings = Settings()

        # Assert - should not add another test_ prefix
        assert settings.DATABASE_URL == "postgresql://user:pass@localhost/test_mydb"
        assert settings.DATABASE_URL.count("test_") == 1

    def test_should_not_modify_redis_db1_when_testing(self):
        """Test that Redis database 1 is not modified when TESTING=true."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "true",
                "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                "REDIS_URL": "redis://localhost:6379/1",
            },
            clear=True,
        ):
            settings = Settings()

        # Assert - should keep database 1
        assert settings.REDIS_URL == "redis://localhost:6379/1"

    def test_should_add_test_prefix_when_testing_true(self):
        """Test that test_ prefix is added to database name when TESTING=true."""
        # Arrange & Act
        with patch.dict(
            os.environ,
            {
                "TESTING": "true",
                "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                "REDIS_URL": "redis://localhost:6379/0",
            },
            clear=True,
        ):
            settings = Settings()

        # Assert - should add test_ prefix and switch redis db
        assert "test_mydb" in settings.DATABASE_URL
        assert settings.REDIS_URL == "redis://localhost:6379/1"


class TestValidationSettings:
    """Test validation-related settings."""

    def test_should_have_correct_default_rejection_threshold(self):
        """Test VALIDATION_REJECTION_THRESHOLD has correct default."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.VALIDATION_REJECTION_THRESHOLD == 10

    def test_should_validate_rejection_threshold_range(self):
        """Test VALIDATION_REJECTION_THRESHOLD validates range."""
        # Test valid values
        with patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "50"}):
            settings = Settings()
            assert settings.VALIDATION_REJECTION_THRESHOLD == 50

        # Test boundary values
        with patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "0"}):
            settings = Settings()
            assert settings.VALIDATION_REJECTION_THRESHOLD == 0

        with patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "100"}):
            settings = Settings()
            assert settings.VALIDATION_REJECTION_THRESHOLD == 100

    def test_should_reject_invalid_rejection_threshold(self):
        """Test VALIDATION_REJECTION_THRESHOLD rejects invalid values."""
        # Test negative value
        with patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "-1"}):
            with pytest.raises(ValueError):
                Settings()

        # Test value over 100
        with patch.dict(os.environ, {"VALIDATION_REJECTION_THRESHOLD": "101"}):
            with pytest.raises(ValueError):
                Settings()


class TestReconcilerSettings:
    """Test reconciler-related settings."""

    def test_should_have_correct_default_location_tolerance(self):
        """Test RECONCILER_LOCATION_TOLERANCE has correct default."""
        # Arrange & Act
        settings = Settings()

        # Assert
        assert settings.RECONCILER_LOCATION_TOLERANCE == 0.0001

    def test_should_validate_location_tolerance_range(self):
        """Test RECONCILER_LOCATION_TOLERANCE validates range."""
        # Test valid values
        with patch.dict(os.environ, {"RECONCILER_LOCATION_TOLERANCE": "0.001"}):
            settings = Settings()
            assert settings.RECONCILER_LOCATION_TOLERANCE == 0.001

        # Test boundary values
        with patch.dict(os.environ, {"RECONCILER_LOCATION_TOLERANCE": "0.00001"}):
            settings = Settings()
            assert settings.RECONCILER_LOCATION_TOLERANCE == 0.00001

        with patch.dict(os.environ, {"RECONCILER_LOCATION_TOLERANCE": "0.01"}):
            settings = Settings()
            assert settings.RECONCILER_LOCATION_TOLERANCE == 0.01

    def test_should_reject_invalid_location_tolerance(self):
        """Test RECONCILER_LOCATION_TOLERANCE rejects invalid values."""
        # Test too small value
        with patch.dict(os.environ, {"RECONCILER_LOCATION_TOLERANCE": "0.000001"}):
            with pytest.raises(ValueError):
                Settings()

        # Test too large value
        with patch.dict(os.environ, {"RECONCILER_LOCATION_TOLERANCE": "0.1"}):
            with pytest.raises(ValueError):
                Settings()
