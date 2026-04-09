"""Tests for Greater Lansing Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.greater_lansing_food_bank_mi_scraper import (
    GreaterLansingFoodBankMiScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "201",
            "name": "Lansing Food Pantry",
            "address": "300 S Washington Square",
            "address2": "",
            "city": "Lansing",
            "state": "MI",
            "zip": "48933",
            "phone": "517-555-1234",
            "lat": "42.7325",
            "lng": "-84.5555",
            "hours": "<p>Mon-Fri 8am-5pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Ingham County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = GreaterLansingFoodBankMiScraper()
    assert scraper.scraper_id == "greater_lansing_food_bank_mi"
    assert "greaterlansingfoodbank.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = GreaterLansingFoodBankMiScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Lansing Food Pantry"
    assert loc["state"] == "MI"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = GreaterLansingFoodBankMiScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "greater_lansing_food_bank_mi"
    assert submitted[0]["food_bank"] == "Greater Lansing Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = GreaterLansingFoodBankMiScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
