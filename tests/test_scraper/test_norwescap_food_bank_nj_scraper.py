"""Tests for NORWESCAP Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.norwescap_food_bank_nj_scraper import (
    NorwescapFoodBankNjScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "101",
            "name": "Phillipsburg Food Pantry",
            "address": "100 S Main St",
            "address2": "",
            "city": "Phillipsburg",
            "state": "NJ",
            "zip": "08865",
            "phone": "908-555-1234",
            "lat": "40.6934",
            "lng": "-75.1901",
            "hours": "<p>Mon & Wed 10am-2pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Warren County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = NorwescapFoodBankNjScraper()
    assert scraper.scraper_id == "norwescap_food_bank_nj"
    assert "norwescap.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = NorwescapFoodBankNjScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Phillipsburg Food Pantry"
    assert loc["state"] == "NJ"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = NorwescapFoodBankNjScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "norwescap_food_bank_nj"
    assert submitted[0]["food_bank"] == "NORWESCAP Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = NorwescapFoodBankNjScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
