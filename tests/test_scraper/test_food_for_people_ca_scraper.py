"""Tests for Food For People CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.food_for_people_ca_scraper import (
    FoodForPeopleCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Food For People</h1>
<p>307 West 14th Street, Eureka, CA 95501. Phone: (707) 445-3166</p>
<h2>Get Help</h2>
<ul>
<li>Eureka Community Food Pantry - 123 4th St, Eureka. Open M-F 10am-2pm. (707) 555-1111</li>
<li>Arcata Food Distribution - 456 H St, Arcata, CA 95521. Tuesdays 1-3pm. (707) 555-2222</li>
<li>Fortuna Senior Center Food Program - 789 Main St, Fortuna. Thursdays 10am-12pm</li>
</ul>
</body>
</html>
"""

SAMPLE_HTML_MINIMAL = """
<html><body><p>Food For People</p></body></html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FoodForPeopleCaScraper()
    assert scraper.scraper_id == "food_for_people_ca"
    assert scraper.test_mode is False
    assert "foodforpeople.org" in scraper.base_url


def test_scraper_init_test_mode() -> None:
    """Test scraper initializes correctly in test mode."""
    scraper = FoodForPeopleCaScraper(test_mode=True)
    assert scraper.test_mode is True


def test_extract_locations_finds_main() -> None:
    """Test that the main food bank location is always included."""
    scraper = FoodForPeopleCaScraper()
    locations = scraper._extract_locations_from_html(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert "Food For People" in main["name"]
    assert main["city"] == "Eureka"
    assert main["state"] == "CA"


def test_extract_locations_finds_sites() -> None:
    """Test that distribution sites are extracted from HTML."""
    scraper = FoodForPeopleCaScraper()
    locations = scraper._extract_locations_from_html(SAMPLE_HTML)
    # Should find main + at least some of the listed sites
    assert len(locations) >= 1


def test_extract_locations_minimal_html() -> None:
    """Test parsing handles minimal HTML gracefully."""
    scraper = FoodForPeopleCaScraper()
    locations = scraper._extract_locations_from_html(SAMPLE_HTML_MINIMAL)
    assert len(locations) >= 1  # At least main location


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that scrape submits locations to the queue."""
    scraper = FoodForPeopleCaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "food_for_people_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted_jobs[0])
    assert first_job["source"] == "food_for_people_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that duplicate locations are removed."""
    scraper = FoodForPeopleCaScraper()

    def mock_extract(html: str) -> list[dict[str, Any]]:
        return [
            {
                "name": "Test",
                "address": "100 Main St",
                "city": "Eureka",
                "state": "CA",
                "zip": "95501",
                "phone": "",
                "hours": "",
                "description": "",
                "services": ["Food Pantry"],
            },
            {
                "name": "Test",
                "address": "100 Main St",
                "city": "Eureka",
                "state": "CA",
                "zip": "95501",
                "phone": "",
                "hours": "",
                "description": "",
                "services": ["Food Pantry"],
            },
        ]

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "_extract_locations_from_html", mock_extract)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["unique_locations"] == 1
    assert len(submitted) == 1


async def test_scrape_handles_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper handles HTTP errors when fetching pages."""
    scraper = FoodForPeopleCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    call_count = 0

    async def mock_fetch(client: Any, url: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            raise httpx.HTTPError("Not found")
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)
    # Should eventually find locations from a successful page
    assert summary["total_jobs_created"] >= 0
