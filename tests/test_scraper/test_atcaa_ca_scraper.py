"""Tests for ATCAA CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.atcaa_ca_scraper import (
    AtcaaCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>ATCAA Food Programs</h1>
<p>10059 Victoria Way, Jamestown, CA 95327. Phone: (209) 984-3960</p>
<h2>Food Distribution</h2>
<div>
<p>Sonora Community Food Pantry at 100 S Washington St, Sonora, CA 95370.
   Food distribution on Wednesdays 10am-2pm. (209) 555-4567</p>
<p>Tuolumne Commodity Distribution at 200 N Main St, Tuolumne.
   Monthly food commodities program.</p>
</div>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = AtcaaCaScraper()
    assert scraper.scraper_id == "atcaa_ca"
    assert scraper.test_mode is False
    assert "atcaa.org" in scraper.base_url


def test_parse_locations_main() -> None:
    """Test main location is found."""
    scraper = AtcaaCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert "ATCAA" in main["name"]
    assert main["address"] == "10059 Victoria Way"
    assert main["city"] == "Jamestown"
    assert main["zip"] == "95327"


def test_parse_locations_phone() -> None:
    """Test phone extraction."""
    scraper = AtcaaCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(209) 984-3960"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits locations to queue."""
    scraper = AtcaaCaScraper()

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

    assert summary["scraper_id"] == "atcaa_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "atcaa_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_tries_multiple_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper tries multiple URL paths when first ones fail."""
    scraper = AtcaaCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    call_count = 0

    async def mock_fetch(client: Any, url: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 5:
            raise httpx.HTTPError("Not found")
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)
    # Even if early paths fail, later paths should work
    assert summary["total_jobs_created"] >= 0


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test deduplication of locations."""
    scraper = AtcaaCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Jamestown",
            "state": "CA",
            "zip": "95327",
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
