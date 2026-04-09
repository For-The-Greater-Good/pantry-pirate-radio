"""Tests for The Resource Connection Food Bank CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.resource_connection_food_bank_ca_scraper import (
    ResourceConnectionFoodBankCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Food and Nutrition Resources</h1>
<table>
<tr>
<td><strong>Calaveras County Food Bank</strong><br>
59 N Main St, San Andreas, CA 95249<br>
Phone: (209) 754-1257<br>
Food bank serving Calaveras County residents with nutrition assistance.</td>
</tr>
<tr>
<td><strong>Angels Camp Food Pantry</strong><br>
100 Market St, Angels Camp, CA 95222<br>
Phone: (209) 555-3456<br>
Community food distribution on Tuesdays and Thursdays.</td>
</tr>
</table>
</body>
</html>
"""

SAMPLE_HTML_EMPTY = """
<html><body><h1>Resource Directory</h1><p>No results found.</p></body></html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = ResourceConnectionFoodBankCaScraper()
    assert scraper.scraper_id == "resource_connection_food_bank_ca"
    assert scraper.test_mode is False
    assert "trcac.org" in scraper.directory_url


def test_parse_directory_finds_food_sites() -> None:
    """Test directory parsing finds food-related entries."""
    scraper = ResourceConnectionFoodBankCaScraper()
    locations = scraper._parse_directory(SAMPLE_HTML)
    assert len(locations) >= 1
    # Check that locations have required fields
    for loc in locations:
        assert "name" in loc
        assert "address" in loc
        assert loc["state"] == "CA"


def test_parse_directory_extracts_details() -> None:
    """Test that phone and city are extracted."""
    scraper = ResourceConnectionFoodBankCaScraper()
    locations = scraper._parse_directory(SAMPLE_HTML)
    assert len(locations) >= 1
    # At least one should have a phone
    phones = [loc["phone"] for loc in locations if loc["phone"]]
    assert len(phones) >= 1


def test_parse_directory_empty_page() -> None:
    """Test fallback when no food locations found."""
    scraper = ResourceConnectionFoodBankCaScraper()
    locations = scraper._parse_directory(SAMPLE_HTML_EMPTY)
    # Should return fallback location
    assert len(locations) >= 1
    assert locations[0]["name"] == FOOD_BANK_NAME


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits locations to queue."""
    scraper = ResourceConnectionFoodBankCaScraper()

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

    assert summary["scraper_id"] == "resource_connection_food_bank_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "resource_connection_food_bank_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_falls_back_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that scraper falls back when directory URL fails."""
    scraper = ResourceConnectionFoodBankCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    call_count = 0

    async def mock_fetch(client: Any, url: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPError("Not found")
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Should still get results from fallback URL
    assert summary["total_jobs_created"] >= 1


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication of directory entries."""
    scraper = ResourceConnectionFoodBankCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test Food Bank",
            "address": "100 Main St",
            "city": "San Andreas",
            "state": "CA",
            "zip": "95249",
            "phone": "",
            "hours": "",
            "description": "",
            "services": ["Food Assistance"],
        }
        return [loc, dict(loc)]

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "_parse_directory", mock_parse)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["unique_locations"] == 1
    assert len(submitted) == 1
