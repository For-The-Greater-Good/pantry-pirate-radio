"""Tests for Food Bank of North Central Arkansas scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_north_central_arkansas_ar_scraper import (
    FoodBankOfNorthCentralArkansasArScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "101",
            "name": "Mountain Home Food Pantry",
            "address": "200 Hospital Dr",
            "address2": "",
            "city": "Mountain Home",
            "state": "AR",
            "zip": "72653",
            "phone": "870-555-1234",
            "lat": "36.3354",
            "lng": "-92.3844",
            "hours": "<p>Mon & Wed 9am-12pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Baxter County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfNorthCentralArkansasArScraper()
    assert scraper.scraper_id == "food_bank_of_north_central_arkansas_ar"
    assert "foodbanknca.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfNorthCentralArkansasArScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Mountain Home Food Pantry"
    assert loc["state"] == "AR"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = FoodBankOfNorthCentralArkansasArScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "food_bank_of_north_central_arkansas_ar"
    assert submitted[0]["food_bank"] == "Food Bank of North Central Arkansas"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = FoodBankOfNorthCentralArkansasArScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
