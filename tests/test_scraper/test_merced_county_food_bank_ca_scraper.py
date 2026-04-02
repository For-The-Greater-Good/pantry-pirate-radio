"""Tests for Merced County Food Bank CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.scraper.scrapers.merced_county_food_bank_ca_scraper import (
    MercedCountyFoodBankCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Merced County Food Bank</h1>
<p>2000 W Olive Ave, Merced, CA 95348. Phone: (209) 726-3663</p>
<h2>Partner Agencies</h2>
<ul>
<li>Atwater Community Food Pantry - 700 E Bellevue Rd, Atwater, CA 95301. (209) 555-1111. Open Mon-Fri.</li>
<li>Los Banos Food Distribution - 123 H St, Los Banos, CA 95340. Tuesdays 9-11am</li>
</ul>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = MercedCountyFoodBankCaScraper()
    assert scraper.scraper_id == "merced_county_food_bank_ca"
    assert scraper.test_mode is False
    assert "mmcfb.org" in scraper.base_url


def test_parse_locations_finds_sites() -> None:
    """Test parsing finds distribution sites from HTML."""
    scraper = MercedCountyFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    names = [loc["name"] for loc in locations]
    assert any("Atwater" in n or "Food" in n for n in names)


async def test_scrape_submits_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scrape submits locations to queue."""
    scraper = MercedCountyFoodBankCaScraper()

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

    assert summary["scraper_id"] == "merced_county_food_bank_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "merced_county_food_bank_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_with_browser_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scrape uses browser fallback and parses locations."""
    scraper = MercedCountyFoodBankCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    with patch(
        "app.scraper.scrapers.merced_county_food_bank_ca_scraper.fetch_with_browser_fallback",
        new_callable=AsyncMock,
        return_value=SAMPLE_HTML,
    ):
        result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 1
    first_job = json.loads(submitted[0])
    assert first_job["source"] == "merced_county_food_bank_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_empty_when_all_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scrape returns zero jobs when browser fallback fails."""
    scraper = MercedCountyFoodBankCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch_none(client: Any, url: str) -> None:
        return None

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch_none)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["total_jobs_created"] == 0
    assert len(submitted) == 0


async def test_scrape_deduplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test deduplication of locations."""
    scraper = MercedCountyFoodBankCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Merced",
            "state": "CA",
            "zip": "95348",
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
    assert len(submitted) == 1
