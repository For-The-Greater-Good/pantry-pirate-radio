"""Tests for Community Food Bank of San Benito County CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.community_food_bank_of_san_benito_county_ca_scraper import (
    CommunityFoodBankOfSanBenitoCountyCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Community Food Bank of San Benito County</h1>
<p>Call us at (831) 637-0340</p>
<h2>Distribution Sites</h2>
<div>
<p>Main Food Bank, 1133 San Felipe Road, Hollister, CA 95023</p>
</div>
<h3>Hollister Food Pantry</h3>
<p>123 Main St, Hollister, CA 95023. Open Mon-Fri 9am-5pm. (831) 555-1234.
   Food pantry serving San Benito County residents.</p>
<h3>San Juan Bautista Distribution</h3>
<p>456 Third St, San Juan Bautista, CA 95045. Food distribution every Tuesday.</p>
</body>
</html>
"""

SAMPLE_HTML_EMPTY = """
<html><body><h1>Under Construction</h1></body></html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()
    assert scraper.scraper_id == "community_food_bank_of_san_benito_county_ca"
    assert scraper.test_mode is False
    assert "communityfoodbankofsbc.org" in scraper.base_url


def test_scraper_init_test_mode() -> None:
    """Test scraper initializes correctly in test mode."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations_finds_main_location() -> None:
    """Test that the main food bank location is always included."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert main["name"] == FOOD_BANK_NAME
    assert main["address"] == "1133 San Felipe Road"
    assert main["city"] == "Hollister"
    assert main["state"] == "CA"
    assert main["zip"] == "95023"


def test_parse_locations_extracts_phone() -> None:
    """Test phone number extraction from page text."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(831) 637-0340"


def test_parse_locations_empty_html() -> None:
    """Test parsing handles minimal HTML gracefully."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_EMPTY)
    # Should still have main location
    assert len(locations) >= 1
    assert locations[0]["name"] == FOOD_BANK_NAME


async def test_fetch_page_success() -> None:
    """Test successful page fetch."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = SAMPLE_HTML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await scraper._fetch_page(mock_client, scraper.base_url)
    assert result == SAMPLE_HTML


async def test_fetch_page_http_error() -> None:
    """Test that HTTP errors propagate correctly."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Server error"))

    with pytest.raises(httpx.HTTPError):
        await scraper._fetch_page(mock_client, scraper.base_url)


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that scrape submits locations to the queue."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "community_food_bank_of_san_benito_county_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1
    assert len(submitted_jobs) >= 1

    # Verify metadata
    first_job = json.loads(submitted_jobs[0])
    assert first_job["source"] == "community_food_bank_of_san_benito_county_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that duplicate locations are removed."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        return [
            {
                "name": "Test Pantry",
                "address": "100 Main St",
                "city": "Hollister",
                "state": "CA",
                "zip": "95023",
                "phone": "",
                "hours": "",
                "description": "",
                "services": ["Food Pantry"],
            },
            {
                "name": "Test Pantry",
                "address": "100 Main St",
                "city": "Hollister",
                "state": "CA",
                "zip": "95023",
                "phone": "",
                "hours": "",
                "description": "",
                "services": ["Food Pantry"],
            },
        ]

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

    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 1
    assert len(submitted) == 1


async def test_scrape_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper handles empty page content."""
    scraper = CommunityFoodBankOfSanBenitoCountyCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML_EMPTY

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Should still get at least the main location
    assert summary["total_jobs_created"] >= 1
