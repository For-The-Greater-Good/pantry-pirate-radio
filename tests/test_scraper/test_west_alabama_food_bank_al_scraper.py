"""Tests for West Alabama Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.west_alabama_food_bank_al_scraper import (
    WestAlabamaFoodBankAlScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "401",
            "name": "Tuscaloosa Food Pantry",
            "address": "300 University Blvd",
            "address2": "",
            "city": "Tuscaloosa",
            "state": "AL",
            "zip": "35401",
            "phone": "205-555-4321",
            "lat": "33.2098",
            "lng": "-87.5692",
            "hours": "<p>Mon & Wed 9am-1pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Tuscaloosa County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = WestAlabamaFoodBankAlScraper()
    assert scraper.scraper_id == "west_alabama_food_bank_al"
    assert "westalabamafoodbank.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = WestAlabamaFoodBankAlScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Tuscaloosa Food Pantry"
    assert loc["state"] == "AL"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = WestAlabamaFoodBankAlScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "west_alabama_food_bank_al"
    assert submitted[0]["food_bank"] == "West Alabama Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = WestAlabamaFoodBankAlScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
