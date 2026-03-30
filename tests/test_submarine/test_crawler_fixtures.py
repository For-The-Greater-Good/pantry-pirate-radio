"""Tests using the Grace Community Church test fixture site.

These tests verify the crawler's link filtering and content handling
using realistic food pantry HTML content.
"""

from pathlib import Path

import pytest

from app.submarine.crawler import CrawlResult, SubmarineCrawler

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "test_site"


class TestGraceChurchFixture:
    """Tests using the Grace Community Church test site."""

    @pytest.fixture
    def crawler(self):
        return SubmarineCrawler(max_pages=3, timeout=10)

    def test_fixture_files_exist(self):
        """Test site fixture files are present."""
        assert (FIXTURES_DIR / "index.html").exists()
        assert (FIXTURES_DIR / "food-pantry.html").exists()
        assert (FIXTURES_DIR / "contact.html").exists()
        assert (FIXTURES_DIR / "about.html").exists()

    def test_index_has_relevant_links(self, crawler):
        """Index page links to food pantry and contact pages."""
        # Simulate links that would be extracted from index.html
        links = [
            ("https://gracechurch.org/about.html", "About Us"),
            ("https://gracechurch.org/food-pantry.html", "Food Pantry"),
            ("https://gracechurch.org/contact.html", "Contact"),
            ("https://gracechurch.org/donate.html", "Donate"),
            ("https://gracechurch.org/events.html", "Events"),
        ]
        relevant = crawler._filter_relevant_links(links)
        relevant_urls = [url for url, _ in relevant]

        # Should follow food pantry, contact, about (relevant to extraction)
        assert "https://gracechurch.org/food-pantry.html" in relevant_urls
        assert "https://gracechurch.org/contact.html" in relevant_urls
        assert "https://gracechurch.org/about.html" in relevant_urls

        # Should skip donate and events (not useful for hours/phone/email)
        assert "https://gracechurch.org/donate.html" not in relevant_urls
        assert "https://gracechurch.org/events.html" not in relevant_urls

    def test_food_pantry_page_has_target_data(self):
        """The food-pantry.html page contains hours and address data."""
        content = (FIXTURES_DIR / "food-pantry.html").read_text()
        # Hours
        assert "Tuesday" in content
        assert "Thursday" in content
        assert "Saturday" in content
        assert "10:00 AM" in content
        # Address
        assert "742 Evergreen Terrace" in content
        assert "Springfield, IL 62704" in content

    def test_contact_page_has_target_data(self):
        """The contact.html page contains phone and email data."""
        content = (FIXTURES_DIR / "contact.html").read_text()
        # Phone
        assert "(555) 234-5678" in content
        assert "(555) 234-5679" in content
        # Email
        assert "info@gracechurchspringfield.org" in content
        assert "pantry@gracechurchspringfield.org" in content

    def test_about_page_has_description(self):
        """The about.html page contains a description of the food pantry."""
        content = (FIXTURES_DIR / "about.html").read_text()
        assert "food pantry" in content.lower()
        assert "Central Illinois Food Bank" in content

    def test_combined_markdown_for_extraction(self):
        """Simulated combined markdown contains all target fields."""
        # Simulate what the crawler would produce from all 3 pages
        pages = ["food-pantry.html", "contact.html", "about.html"]
        combined = ""
        for page in pages:
            content = (FIXTURES_DIR / page).read_text()
            combined += f"\n\n# Page: {page}\n\n{content}"

        # All target fields should be present in combined content
        assert "(555) 234-5678" in combined  # phone
        assert "info@gracechurchspringfield.org" in combined  # email
        assert "Tuesday" in combined  # hours
        assert "Central Illinois Food Bank" in combined  # description
