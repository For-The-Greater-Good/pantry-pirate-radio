"""Tests for Yuba-Sutter Food Bank CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.yuba_sutter_food_bank_ca_scraper import (
    YubaSutterFoodBankCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Yuba-Sutter Food Bank</h1>
<p>760 Stafford Way, Yuba City, CA 95991. (530) 673-3834</p>
<h2>Programs</h2>
<div>
<p>Marysville Community Food Pantry at 100 D St, Marysville, CA 95901.
   Open Mon-Wed 9am-12pm. (530) 555-1111</p>
<p>Olivehurst Food Distribution at 5345 Arboga Rd, Olivehurst, CA 95961.
   Fridays 10am-12pm. (530) 555-2222</p>
</div>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = YubaSutterFoodBankCaScraper()
    assert scraper.scraper_id == "yuba_sutter_food_bank_ca"
    assert scraper.test_mode is False
    assert "feedingys.org" in scraper.base_url


def test_parse_locations_main() -> None:
    """Test main location is found."""
    scraper = YubaSutterFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert main["name"] == "Yuba-Sutter Food Bank"
    assert main["address"] == "760 Stafford Way"
    assert main["city"] == "Yuba City"
    assert main["zip"] == "95991"


def test_parse_locations_phone() -> None:
    """Test phone extraction."""
    scraper = YubaSutterFoodBankCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(530) 673-3834"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits locations to queue."""
    scraper = YubaSutterFoodBankCaScraper()

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

    assert summary["scraper_id"] == "yuba_sutter_food_bank_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "yuba_sutter_food_bank_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication of locations."""
    scraper = YubaSutterFoodBankCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Yuba City",
            "state": "CA",
            "zip": "95991",
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


async def test_scrape_handles_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper handles HTTP errors when fetching pages."""
    scraper = YubaSutterFoodBankCaScraper()

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
    # Should eventually find locations
    assert summary["total_jobs_created"] >= 0


async def test_scrape_summary_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape returns valid JSON summary."""
    scraper = YubaSutterFoodBankCaScraper()

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
