"""Tests for River Valley Regional Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.river_valley_regional_food_bank_ar_scraper import (
    RiverValleyRegionalFoodBankArScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "201",
            "name": "Fort Smith Food Pantry",
            "address": "100 Garrison Ave",
            "address2": "",
            "city": "Fort Smith",
            "state": "AR",
            "zip": "72901",
            "phone": "479-555-1234",
            "lat": "35.3859",
            "lng": "-94.3985",
            "hours": "<p>Mon-Fri 8am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Sebastian County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = RiverValleyRegionalFoodBankArScraper()
    assert scraper.scraper_id == "river_valley_regional_food_bank_ar"
    assert "rvfoodbank.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = RiverValleyRegionalFoodBankArScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Fort Smith Food Pantry"
    assert loc["state"] == "AR"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = RiverValleyRegionalFoodBankArScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "river_valley_regional_food_bank_ar"
    assert submitted[0]["food_bank"] == "River Valley Regional Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = RiverValleyRegionalFoodBankArScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
