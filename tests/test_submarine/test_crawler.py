"""Tests for submarine web crawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.submarine.crawler import CrawlResult, SubmarineCrawler


class TestSubmarineCrawler:
    """Tests for the SubmarineCrawler class."""

    @pytest.fixture
    def crawler(self):
        return SubmarineCrawler(
            max_pages=3,
            timeout=10,
        )

    def test_crawl_result_model(self):
        """CrawlResult holds markdown content and metadata."""
        result = CrawlResult(
            url="https://foodbank.example.com",
            markdown="# Food Bank\nOpen Mon-Fri 9-5",
            pages_crawled=1,
            status="success",
        )
        assert result.url == "https://foodbank.example.com"
        assert "Mon-Fri" in result.markdown
        assert result.pages_crawled == 1

    def test_crawl_result_error(self):
        """CrawlResult can represent an error."""
        result = CrawlResult(
            url="https://down.example.com",
            markdown="",
            pages_crawled=0,
            status="error",
            error="Connection refused",
        )
        assert result.status == "error"
        assert result.error == "Connection refused"

    def test_relevant_link_patterns(self, crawler):
        """Crawler identifies relevant links to follow."""
        links = [
            ("https://foodbank.org/contact", "Contact Us"),
            ("https://foodbank.org/hours", "Hours & Locations"),
            ("https://foodbank.org/about", "About Us"),
            ("https://foodbank.org/services", "Our Services"),
            ("https://foodbank.org/blog/post-1", "Latest News"),
            ("https://foodbank.org/donate", "Donate Now"),
        ]
        relevant = crawler._filter_relevant_links(links)
        relevant_urls = [url for url, _ in relevant]
        # Should keep contact, hours, about, services
        assert "https://foodbank.org/contact" in relevant_urls
        assert "https://foodbank.org/hours" in relevant_urls
        assert "https://foodbank.org/about" in relevant_urls
        assert "https://foodbank.org/services" in relevant_urls
        # Should skip blog and donate
        assert "https://foodbank.org/blog/post-1" not in relevant_urls
        assert "https://foodbank.org/donate" not in relevant_urls

    def test_max_pages_respected(self, crawler):
        """Crawler respects the max_pages limit."""
        assert crawler.max_pages == 3

    def test_link_filtering_case_insensitive(self, crawler):
        """Link text matching is case-insensitive."""
        links = [
            ("https://foodbank.org/CONTACT", "CONTACT US"),
            ("https://foodbank.org/Hours", "Our Hours"),
        ]
        relevant = crawler._filter_relevant_links(links)
        assert len(relevant) == 2

    def test_link_filtering_handles_empty(self, crawler):
        """Empty link list returns empty."""
        assert crawler._filter_relevant_links([]) == []
