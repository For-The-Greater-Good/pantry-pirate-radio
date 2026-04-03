"""Tests for Interfaith Food Bank Amador County CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.interfaith_food_bank_amador_ca_scraper import (
    InterfaithFoodBankAmadorCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Interfaith Food Bank & Thrift Store</h1>
<p>12181 Airport Road, Jackson, CA 95642</p>
<p>Phone: (209) 223-1485</p>
<div>
<p>Serving Amador County with food assistance and thrift store services.</p>
<h3>Pine Grove Community Food Distribution</h3>
<p>456 Pine St, Pine Grove, CA 95665. Food distribution every Monday. (209) 555-2345</p>
</div>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = InterfaithFoodBankAmadorCaScraper()
    assert scraper.scraper_id == "interfaith_food_bank_amador_ca"
    assert scraper.test_mode is False
    assert "feedamador.org" in scraper.base_url


def test_parse_locations_main_location() -> None:
    """Test that the main food bank is always included."""
    scraper = InterfaithFoodBankAmadorCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert "Interfaith" in main["name"]
    assert main["address"] == "12181 Airport Road"
    assert main["city"] == "Jackson"
    assert main["zip"] == "95642"


def test_parse_locations_extracts_phone() -> None:
    """Test phone number extraction."""
    scraper = InterfaithFoodBankAmadorCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(209) 223-1485"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits jobs to queue."""
    scraper = InterfaithFoodBankAmadorCaScraper()

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

    assert summary["scraper_id"] == "interfaith_food_bank_amador_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "interfaith_food_bank_amador_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication of locations."""
    scraper = InterfaithFoodBankAmadorCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Jackson",
            "state": "CA",
            "zip": "95642",
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
