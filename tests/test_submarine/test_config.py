"""Tests for Submarine configuration settings."""

from app.core.config import settings


class TestSubmarineConfig:
    """Tests for submarine settings in the shared config."""

    def test_submarine_enabled_by_default(self):
        """Submarine is enabled by default (auto-dispatch after PR #404)."""
        assert settings.SUBMARINE_ENABLED is True

    def test_crawl_timeout_default(self):
        """Default crawl timeout is 30 seconds."""
        assert settings.SUBMARINE_CRAWL_TIMEOUT == 30

    def test_max_pages_default(self):
        """Default max pages per site is 3."""
        assert settings.SUBMARINE_MAX_PAGES_PER_SITE == 3

    def test_min_crawl_delay_default(self):
        """Default minimum delay between requests is 5 seconds."""
        assert settings.SUBMARINE_MIN_CRAWL_DELAY == 5

    def test_max_attempts_default(self):
        """Default max retry attempts is 3."""
        assert settings.SUBMARINE_MAX_ATTEMPTS == 3

    def test_cooldown_success_days_default(self):
        """Successful crawl cooldown is 30 days."""
        assert settings.SUBMARINE_COOLDOWN_SUCCESS_DAYS == 30

    def test_cooldown_no_data_days_default(self):
        """No-data crawl cooldown is 90 days (long backoff)."""
        assert settings.SUBMARINE_COOLDOWN_NO_DATA_DAYS == 90

    def test_cooldown_error_days_default(self):
        """Error crawl cooldown is 14 days (shorter, may be transient)."""
        assert settings.SUBMARINE_COOLDOWN_ERROR_DAYS == 14
