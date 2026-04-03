"""Tests for Hoosier Hills Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.hoosier_hills_food_bank_in_scraper import (
    HoosierHillsFoodBankInScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "401",
            "name": "Bloomington Food Pantry",
            "address": "2333 W Industrial Park Dr",
            "address2": "",
            "city": "Bloomington",
            "state": "IN",
            "zip": "47404",
            "phone": "812-334-8374",
            "lat": "39.1653",
            "lng": "-86.5264",
            "hours": "<p>Mon-Fri 8am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Monroe County</p>",
        },
        {
            "id": "402",
            "name": "Bedford Community Kitchen",
            "address": "100 J St",
            "address2": "",
            "city": "Bedford",
            "state": "",
            "zip": "47421",
            "phone": "",
            "lat": "38.8611",
            "lng": "-86.4872",
            "hours": "",
            "url": "",
            "email": "",
            "description": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = HoosierHillsFoodBankInScraper()
    assert scraper.scraper_id == "hoosier_hills_food_bank_in"
    assert "hhfoodbank.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = HoosierHillsFoodBankInScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Bloomington Food Pantry"
    assert loc["state"] == "IN"
    assert loc["latitude"] == 39.1653


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state with IN default."""
    scraper = HoosierHillsFoodBankInScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "IN"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = HoosierHillsFoodBankInScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "hoosier_hills_food_bank_in"
    assert submitted[0]["food_bank"] == "Hoosier Hills Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = HoosierHillsFoodBankInScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
