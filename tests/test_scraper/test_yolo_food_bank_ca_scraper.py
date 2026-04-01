"""Tests for Yolo Food Bank CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.yolo_food_bank_ca_scraper import (
    YoloFoodBankCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Yolo Food Bank</h1>
<p>233 Harter Avenue, Woodland, CA 95776. (530) 668-0690</p>
<h2>Food Distribution Sites</h2>
<div>
<p>Davis Community Meals food pantry at 100 F St, Davis, CA 95616.
   Open Mon, Wed, Fri 10am-12pm. (530) 555-1234</p>
<p>West Sacramento Food Distribution at 1110 West Capitol Ave, West Sacramento, CA 95691.
   Every Thursday 2-4pm. (916) 555-5678</p>
<p>Winters Community Food Pantry at 210 Railroad Ave, Winters, CA 95694.
   Tuesdays 9am-11am</p>
</div>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = YoloFoodBankCaScraper()
    assert scraper.scraper_id == "yolo_food_bank_ca"
    assert scraper.test_mode is False
    assert "yolofoodbank.org" in scraper.base_url


def test_parse_locations_main() -> None:
    """Test main location is found."""
    scraper = YoloFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert main["name"] == "Yolo Food Bank"
    assert main["address"] == "233 Harter Avenue"
    assert main["city"] == "Woodland"
    assert main["zip"] == "95776"


def test_parse_locations_phone() -> None:
    """Test phone extraction."""
    scraper = YoloFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(530) 668-0690"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits locations to queue."""
    scraper = YoloFoodBankCaScraper()

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

    assert summary["scraper_id"] == "yolo_food_bank_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "yolo_food_bank_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication of locations."""
    scraper = YoloFoodBankCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Woodland",
            "state": "CA",
            "zip": "95776",
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


async def test_scrape_summary_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape returns valid JSON summary."""
    scraper = YoloFoodBankCaScraper()

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
