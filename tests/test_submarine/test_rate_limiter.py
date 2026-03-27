"""Tests for submarine rate limiter — per-domain throttling."""

import time

import pytest

from app.submarine.rate_limiter import SubmarineRateLimiter


class TestPerDomainThrottle:
    """Tests for per-domain request throttling."""

    @pytest.fixture
    def limiter(self):
        return SubmarineRateLimiter(min_delay_seconds=5)

    def test_first_request_no_delay(self, limiter):
        """First request to a domain has no delay."""
        delay = limiter.get_delay("https://foodbank.example.com/contact")
        assert delay == 0

    def test_second_request_has_delay(self, limiter):
        """Second request to same domain within window gets delayed."""
        limiter.record_request("https://foodbank.example.com/page1")
        delay = limiter.get_delay("https://foodbank.example.com/page2")
        assert delay > 0
        assert delay <= 5

    def test_different_domains_independent(self, limiter):
        """Requests to different domains don't affect each other."""
        limiter.record_request("https://foodbank-a.org/page")
        delay = limiter.get_delay("https://foodbank-b.org/page")
        assert delay == 0

    def test_delay_expires_after_min_delay(self, limiter):
        """After min_delay seconds, no more delay needed."""
        fast_limiter = SubmarineRateLimiter(min_delay_seconds=0.01)
        fast_limiter.record_request("https://foodbank.example.com/page1")
        time.sleep(0.02)
        delay = fast_limiter.get_delay("https://foodbank.example.com/page2")
        assert delay == 0

    def test_extract_domain(self, limiter):
        """Domain extraction works for various URL formats."""
        assert (
            limiter._extract_domain("https://www.foodbank.org/contact")
            == "www.foodbank.org"
        )
        assert limiter._extract_domain("http://foodbank.org") == "foodbank.org"
        assert (
            limiter._extract_domain("https://foodbank.org:8080/page")
            == "foodbank.org:8080"
        )

    def test_record_updates_timestamp(self, limiter):
        """Recording a request updates the domain timestamp."""
        limiter.record_request("https://example.com/page1")
        first_delay = limiter.get_delay("https://example.com/page2")
        time.sleep(0.01)
        limiter.record_request("https://example.com/page2")
        second_delay = limiter.get_delay("https://example.com/page3")
        # Second delay should be >= first delay since we just recorded
        assert second_delay >= first_delay - 0.02  # Allow small timing slack


class TestUserAgent:
    """Tests for user agent identification."""

    def test_user_agent_identifies_project(self):
        limiter = SubmarineRateLimiter(min_delay_seconds=5)
        assert "PantryPirateRadio" in limiter.user_agent
        assert "food-bank" in limiter.user_agent.lower()
