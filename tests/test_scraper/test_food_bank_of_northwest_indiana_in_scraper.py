"""Tests for Food Bank of Northwest Indiana scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_northwest_indiana_in_scraper import (
    FoodBankOfNorthwestIndianaInScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "201",
            "name": "Merrillville Food Pantry",
            "address": "100 Broadway",
            "address2": "",
            "city": "Merrillville",
            "state": "IN",
            "zip": "46410",
            "phone": "219-555-1234",
            "lat": "41.4828",
            "lng": "-87.3328",
            "hours": "<p>Mon-Wed 9am-3pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Lake County</p>",
        },
        {
            "id": "202",
            "name": "Gary Community Center",
            "address": "500 5th Ave",
            "address2": "",
            "city": "Gary",
            "state": "",
            "zip": "46402",
            "phone": "",
            "lat": "41.5934",
            "lng": "-87.3464",
            "hours": "",
            "url": "",
            "email": "",
            "description": "<p>Thursdays 10am-12pm</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfNorthwestIndianaInScraper()
    assert scraper.scraper_id == "food_bank_of_northwest_indiana_in"
    assert "foodbanknwi.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfNorthwestIndianaInScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Merrillville Food Pantry"
    assert loc["city"] == "Merrillville"
    assert loc["state"] == "IN"
    assert loc["latitude"] == 41.4828


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state with IN default."""
    scraper = FoodBankOfNorthwestIndianaInScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "IN"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_slp_response):
    """Test duplicate locations removed by ID."""
    scraper = FoodBankOfNorthwestIndianaInScraper(test_mode=True)

    async def mock_fetch(client):
        return mock_slp_response + mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 2


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = FoodBankOfNorthwestIndianaInScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "food_bank_of_northwest_indiana_in"
    assert submitted[0]["food_bank"] == "Food Bank of Northwest Indiana"


@pytest.mark.asyncio
async def test_fetch_locations_handles_error():
    """Test fetch gracefully handles errors."""
    scraper = FoodBankOfNorthwestIndianaInScraper()
    with patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.ConnectError("fail"),
    ):
        async with httpx.AsyncClient() as client:
            assert await scraper.fetch_locations(client) == []


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = FoodBankOfNorthwestIndianaInScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
