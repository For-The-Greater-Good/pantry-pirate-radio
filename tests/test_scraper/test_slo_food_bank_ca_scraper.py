"""Tests for SLO Food Bank CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.slo_food_bank_ca_scraper import (
    SloFoodBankCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>SLO Food Bank</h1>
<p>1180 Kendall Road, San Luis Obispo, CA 93401</p>
<p>Phone: (805) 238-4664</p>
<h2>Food Programs</h2>
<div>
<p>Paso Robles Community Food Pantry at 300 Spring St, Paso Robles, CA 93446.
   Open Wednesdays 10am-1pm. (805) 555-1234</p>
<p>Atascadero Food Distribution at 5400 Rosario Ave, Atascadero, CA 93422.
   First Thursday of each month.</p>
</div>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = SloFoodBankCaScraper()
    assert scraper.scraper_id == "slo_food_bank_ca"
    assert scraper.test_mode is False
    assert "slofoodbank.org" in scraper.base_url


def test_parse_locations_main() -> None:
    """Test main location is found."""
    scraper = SloFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert main["name"] == "SLO Food Bank"
    assert main["address"] == "1180 Kendall Road"
    assert main["city"] == "San Luis Obispo"
    assert main["zip"] == "93401"


def test_parse_locations_phone() -> None:
    """Test phone extraction."""
    scraper = SloFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(805) 238-4664"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits locations to queue."""
    scraper = SloFoodBankCaScraper()

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

    assert summary["scraper_id"] == "slo_food_bank_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "slo_food_bank_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication."""
    scraper = SloFoodBankCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "San Luis Obispo",
            "state": "CA",
            "zip": "93401",
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
