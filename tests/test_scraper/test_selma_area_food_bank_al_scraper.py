"""Tests for Selma Area Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.selma_area_food_bank_al_scraper import (
    SelmaAreaFoodBankAlScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "301",
            "name": "Selma Food Pantry",
            "address": "100 Water Ave",
            "address2": "",
            "city": "Selma",
            "state": "AL",
            "zip": "36701",
            "phone": "334-555-9876",
            "lat": "32.4074",
            "lng": "-87.0211",
            "hours": "<p>Wed 10am-2pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Dallas County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SelmaAreaFoodBankAlScraper()
    assert scraper.scraper_id == "selma_area_food_bank_al"
    assert "selmafoodbank.com" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = SelmaAreaFoodBankAlScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Selma Food Pantry"
    assert loc["state"] == "AL"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = SelmaAreaFoodBankAlScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "selma_area_food_bank_al"
    assert submitted[0]["food_bank"] == "Selma Area Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = SelmaAreaFoodBankAlScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
