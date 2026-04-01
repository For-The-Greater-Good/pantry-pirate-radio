"""Tests for Imperial Valley Food Bank CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.imperial_valley_food_bank_ca_scraper import (
    ImperialValleyFoodBankCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Imperial Valley Food Bank</h1>
<p>486 W Aten Road, Imperial, CA 92251</p>
<p>Phone: (760) 370-0966</p>
<h2>Distribution Schedule</h2>
<div>
<p>El Centro Community Center food distribution at 300 S 1st St, El Centro, CA 92243.
   Every Tuesday 9am-11am. (760) 555-1234</p>
<p>Brawley Senior Center food pantry at 400 Main St, Brawley, CA 92227.
   Wednesdays 10am-12pm. (760) 555-5678</p>
</div>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = ImperialValleyFoodBankCaScraper()
    assert scraper.scraper_id == "imperial_valley_food_bank_ca"
    assert scraper.test_mode is False
    assert "ivfoodbank.com" in scraper.base_url


def test_parse_locations_main() -> None:
    """Test main location is found."""
    scraper = ImperialValleyFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert main["name"] == "Imperial Valley Food Bank"
    assert main["address"] == "486 W Aten Road"
    assert main["city"] == "Imperial"
    assert main["zip"] == "92251"


def test_parse_locations_phone() -> None:
    """Test phone extraction."""
    scraper = ImperialValleyFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(760) 370-0966"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits locations to queue."""
    scraper = ImperialValleyFoodBankCaScraper()

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

    assert summary["scraper_id"] == "imperial_valley_food_bank_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "imperial_valley_food_bank_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication of locations."""
    scraper = ImperialValleyFoodBankCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Imperial",
            "state": "CA",
            "zip": "92251",
            "phone": "",
            "hours": "",
            "description": "",
            "services": ["Food Bank"],
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


async def test_scrape_summary_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape returns valid JSON summary."""
    scraper = ImperialValleyFoodBankCaScraper()

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
