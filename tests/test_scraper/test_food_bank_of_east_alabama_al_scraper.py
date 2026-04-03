"""Tests for Food Bank of East Alabama scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_east_alabama_al_scraper import (
    FoodBankOfEastAlabamaAlScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "201",
            "name": "Auburn Food Pantry",
            "address": "200 Opelika Rd",
            "address2": "",
            "city": "Auburn",
            "state": "AL",
            "zip": "36830",
            "phone": "334-555-5678",
            "lat": "32.6099",
            "lng": "-85.4808",
            "hours": "<p>Tue & Thu 9am-12pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Lee County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfEastAlabamaAlScraper()
    assert scraper.scraper_id == "food_bank_of_east_alabama_al"
    assert "foodbankofeastalabama.com" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfEastAlabamaAlScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Auburn Food Pantry"
    assert loc["state"] == "AL"
    assert loc["latitude"] == 32.6099


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = FoodBankOfEastAlabamaAlScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "food_bank_of_east_alabama_al"
    assert submitted[0]["food_bank"] == "Food Bank of East Alabama"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = FoodBankOfEastAlabamaAlScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
