"""Tests for Northeast Iowa Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.northeast_iowa_food_bank_ia_scraper import (
    NortheastIowaFoodBankIaScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "201",
            "name": "Waterloo Food Pantry",
            "address": "500 Sycamore St",
            "address2": "",
            "city": "Waterloo",
            "state": "IA",
            "zip": "50703",
            "phone": "319-555-1234",
            "lat": "42.4928",
            "lng": "-92.3426",
            "hours": "<p>Mon-Wed 9am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Black Hawk County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = NortheastIowaFoodBankIaScraper()
    assert scraper.scraper_id == "northeast_iowa_food_bank_ia"
    assert "northeastiowafoodbank.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = NortheastIowaFoodBankIaScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Waterloo Food Pantry"
    assert loc["state"] == "IA"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = NortheastIowaFoodBankIaScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "northeast_iowa_food_bank_ia"
    assert submitted[0]["food_bank"] == "Northeast Iowa Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = NortheastIowaFoodBankIaScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
