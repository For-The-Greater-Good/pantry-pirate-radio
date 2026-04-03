"""Tests for South Michigan Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.south_michigan_food_bank_mi_scraper import (
    SouthMichiganFoodBankMiScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "101",
            "name": "Battle Creek Food Pantry",
            "address": "200 Michigan Ave W",
            "address2": "",
            "city": "Battle Creek",
            "state": "MI",
            "zip": "49017",
            "phone": "269-555-1234",
            "lat": "42.3212",
            "lng": "-85.1797",
            "hours": "<p>Mon-Fri 9am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Calhoun County</p>",
        },
        {
            "id": "102",
            "name": "Kalamazoo Community Kitchen",
            "address": "300 E Michigan Ave",
            "address2": "",
            "city": "Kalamazoo",
            "state": "",
            "zip": "49007",
            "phone": "",
            "lat": "42.2917",
            "lng": "-85.5872",
            "hours": "",
            "url": "",
            "email": "",
            "description": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SouthMichiganFoodBankMiScraper()
    assert scraper.scraper_id == "south_michigan_food_bank_mi"
    assert "smfb.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = SouthMichiganFoodBankMiScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Battle Creek Food Pantry"
    assert loc["state"] == "MI"


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state with MI default."""
    scraper = SouthMichiganFoodBankMiScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "MI"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = SouthMichiganFoodBankMiScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "south_michigan_food_bank_mi"
    assert submitted[0]["food_bank"] == "South Michigan Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = SouthMichiganFoodBankMiScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
