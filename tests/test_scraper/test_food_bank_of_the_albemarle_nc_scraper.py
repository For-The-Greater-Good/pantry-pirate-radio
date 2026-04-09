"""Tests for Food Bank of the Albemarle scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_the_albemarle_nc_scraper import (
    FoodBankOfTheAlbemarleNcScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "201",
            "name": "Elizabeth City Food Pantry",
            "address": "100 Main St",
            "address2": "",
            "city": "Elizabeth City",
            "state": "NC",
            "zip": "27909",
            "phone": "252-555-1234",
            "lat": "36.2946",
            "lng": "-76.2510",
            "hours": "<p>Mon & Wed 10am-2pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Pasquotank County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfTheAlbemarleNcScraper()
    assert scraper.scraper_id == "food_bank_of_the_albemarle_nc"
    assert "afoodbank.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfTheAlbemarleNcScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Elizabeth City Food Pantry"
    assert loc["state"] == "NC"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = FoodBankOfTheAlbemarleNcScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "food_bank_of_the_albemarle_nc"
    assert submitted[0]["food_bank"] == "Food Bank of the Albemarle"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = FoodBankOfTheAlbemarleNcScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
