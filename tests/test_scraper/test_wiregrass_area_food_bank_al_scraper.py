"""Tests for Wiregrass Area Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.wiregrass_area_food_bank_al_scraper import (
    WiregrassAreaFoodBankAlScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "101",
            "name": "Dothan Food Pantry",
            "address": "123 Main St",
            "address2": "",
            "city": "Dothan",
            "state": "AL",
            "zip": "36301",
            "phone": "334-555-1234",
            "lat": "31.2232",
            "lng": "-85.3905",
            "hours": "<p>Mon-Fri 9am-3pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Houston County</p>",
        },
        {
            "id": "102",
            "name": "Enterprise Food Bank",
            "address": "456 Boll Weevil Cir",
            "address2": "",
            "city": "Enterprise",
            "state": "",
            "zip": "36330",
            "phone": "",
            "lat": "31.3310",
            "lng": "-85.8550",
            "hours": "",
            "url": "",
            "email": "",
            "description": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = WiregrassAreaFoodBankAlScraper()
    assert scraper.scraper_id == "wiregrass_area_food_bank_al"
    assert "wiregrassfoodbank.com" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = WiregrassAreaFoodBankAlScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Dothan Food Pantry"
    assert loc["state"] == "AL"


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state with AL default."""
    scraper = WiregrassAreaFoodBankAlScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "AL"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = WiregrassAreaFoodBankAlScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "wiregrass_area_food_bank_al"
    assert submitted[0]["food_bank"] == "Wiregrass Area Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = WiregrassAreaFoodBankAlScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
