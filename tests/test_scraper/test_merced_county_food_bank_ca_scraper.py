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
<main>
<h1>Emergency Food Site Referral List</h1>
<h2>Emergency Food Programs Merced</h2>
<p>APOSTOLIC TABERNACLE</p>
<p>2745 E. Highway 140</p>
<p>Merced, California</p>
<p>(209) 723-0545</p>
<p>Fridays 12 PM - 1 PM</p>

<p>HARVEST TIME</p>
<p>1155 W 10th St.</p>
<p>Merced, California</p>
<p>(209) 564-7638</p>
<p>Food giveaway 2nd and 4th Thursday of every month 8:00 AM - 10:00 AM</p>

<h2>Emergency Food Programs Atwater</h2>
<p>MT. OLIVE BAPTIST CHURCH</p>
<p>559 Broadway Avenue</p>
<p>Atwater, CA</p>
<p>(209) 358-3031</p>
<p>Food giveaway 2nd Wednesday of every month 10AM-11AM</p>

<h2>Emergency Food Programs Los Banos</h2>
<p>BETHEL COMMUNITY CHURCH</p>
<p>415 "I" Street</p>
<p>Los Banos, CA</p>
<p>(209) 827-0797</p>
<p>Drive-thru Food Box Distribution Tuesdays 10AM-12PM</p>
</main>
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
    assert len(locations) >= 2
    names = [loc["name"] for loc in locations]
    assert any("APOSTOLIC" in n or "HARVEST" in n for n in names)


def test_parse_locations_extracts_phone() -> None:
    """Test that phone numbers are extracted."""
    scraper = MercedCountyFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    phones = [loc.get("phone", "") for loc in locations]
    assert any("209" in p for p in phones)


def test_parse_locations_extracts_city() -> None:
    """Test that city is extracted from section headers."""
    scraper = MercedCountyFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    cities = [loc.get("city", "") for loc in locations]
    assert any("Merced" in c for c in cities)


def test_parse_locations_sets_state() -> None:
    """Test that state defaults to CA."""
    scraper = MercedCountyFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    for loc in locations:
        assert loc["state"] == "CA"


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
