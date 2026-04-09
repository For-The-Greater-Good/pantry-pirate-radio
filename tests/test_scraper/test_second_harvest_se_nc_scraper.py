"""Tests for Second Harvest Food Bank of SE North Carolina scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.second_harvest_se_nc_scraper import (
    SecondHarvestSeNcScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "101",
            "name": "Fayetteville Food Pantry",
            "address": "200 Hay St",
            "address2": "",
            "city": "Fayetteville",
            "state": "NC",
            "zip": "28301",
            "phone": "910-555-1234",
            "lat": "35.0527",
            "lng": "-78.8784",
            "hours": "<p>Mon-Fri 9am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Cumberland County</p>",
        },
        {
            "id": "102",
            "name": "Lumberton Food Bank",
            "address": "300 Elm St",
            "address2": "",
            "city": "Lumberton",
            "state": "",
            "zip": "28358",
            "phone": "",
            "lat": "34.6182",
            "lng": "-79.0086",
            "hours": "",
            "url": "",
            "email": "",
            "description": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SecondHarvestSeNcScraper()
    assert scraper.scraper_id == "second_harvest_se_nc"
    assert "shfbenc.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = SecondHarvestSeNcScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Fayetteville Food Pantry"
    assert loc["state"] == "NC"


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state with NC default."""
    scraper = SecondHarvestSeNcScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "NC"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = SecondHarvestSeNcScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "second_harvest_se_nc"
    assert submitted[0]["food_bank"] == "Second Harvest Food Bank of SE North Carolina"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = SecondHarvestSeNcScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
