"""Tests for Feeding the Foothills CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.feeding_the_foothills_ca_scraper import (
    FeedingTheFoothillsCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Get Food</h1>
<p>Feeding the Foothills, 8284 Industrial Ave, Roseville, CA 95678. (916) 783-0481</p>
<div class="locations">
<h3>Auburn Food Closet</h3>
<p>Community food pantry at 100 Maple St, Auburn, CA 95603. (530) 555-1234.
   Open Mon-Wed 9am-12pm.</p>
<h3>Placerville Community Center</h3>
<p>Food distribution at 200 Main St, Placerville, CA 95667.
   Every Thursday 10am-1pm. (530) 555-5678</p>
</div>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FeedingTheFoothillsCaScraper()
    assert scraper.scraper_id == "feeding_the_foothills_ca"
    assert scraper.test_mode is False
    assert "feedingthefoothills.org" in scraper.find_food_url


def test_parse_locations_main_location() -> None:
    """Test that the main office is always included."""
    scraper = FeedingTheFoothillsCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert "Feeding the Foothills" in main["name"]
    assert main["address"] == "8284 Industrial Ave"
    assert main["city"] == "Roseville"
    assert main["zip"] == "95678"
    assert main["phone"] == "916-783-0481"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits jobs to queue."""
    scraper = FeedingTheFoothillsCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return f"job-{len(submitted)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "feeding_the_foothills_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "feeding_the_foothills_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication works."""
    scraper = FeedingTheFoothillsCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Roseville",
            "state": "CA",
            "zip": "95678",
            "phone": "",
            "hours": "",
            "description": "",
            "services": ["Food Pantry"],
        }
        return [loc, dict(loc)]

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "_parse_locations", mock_parse)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["unique_locations"] == 1


async def test_scrape_summary_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape returns valid JSON summary."""
    scraper = FeedingTheFoothillsCaScraper()

    def mock_submit(content: str) -> str:
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "unique_locations" in summary
    assert "total_jobs_created" in summary
    assert "source" in summary
