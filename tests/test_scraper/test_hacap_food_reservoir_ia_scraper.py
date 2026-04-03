"""Tests for HACAP Food Reservoir scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.hacap_food_reservoir_ia_scraper import (
    HacapFoodReservoirIaScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "301",
            "name": "Cedar Rapids Food Pantry",
            "address": "1515 Hawkeye Dr",
            "address2": "",
            "city": "Cedar Rapids",
            "state": "IA",
            "zip": "52402",
            "phone": "319-555-5678",
            "lat": "41.9779",
            "lng": "-91.6656",
            "hours": "<p>Tue & Thu 10am-2pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Linn County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = HacapFoodReservoirIaScraper()
    assert scraper.scraper_id == "hacap_food_reservoir_ia"
    assert "hacap.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = HacapFoodReservoirIaScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Cedar Rapids Food Pantry"
    assert loc["state"] == "IA"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = HacapFoodReservoirIaScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "hacap_food_reservoir_ia"
    assert submitted[0]["food_bank"] == "HACAP Food Reservoir"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = HacapFoodReservoirIaScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
