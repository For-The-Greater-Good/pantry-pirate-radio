"""Tests for Food Bank of Siouxland scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_siouxland_ia_scraper import (
    FoodBankOfSiouxlandIaScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "101",
            "name": "Sioux City Food Pantry",
            "address": "1313 Nebraska St",
            "address2": "",
            "city": "Sioux City",
            "state": "IA",
            "zip": "51105",
            "phone": "712-555-1234",
            "lat": "42.4963",
            "lng": "-96.4003",
            "hours": "<p>Mon-Fri 8am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Woodbury County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfSiouxlandIaScraper()
    assert scraper.scraper_id == "food_bank_of_siouxland_ia"
    assert "siouxlandfoodbank.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfSiouxlandIaScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Sioux City Food Pantry"
    assert loc["state"] == "IA"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = FoodBankOfSiouxlandIaScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "food_bank_of_siouxland_ia"
    assert submitted[0]["food_bank"] == "The Food Bank of Siouxland"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = FoodBankOfSiouxlandIaScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
