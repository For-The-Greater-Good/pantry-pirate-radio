"""Tests for Community Harvest Food Bank of NE Indiana scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.community_harvest_food_bank_in_scraper import (
    CommunityHarvestFoodBankInScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "301",
            "name": "Fort Wayne Community Pantry",
            "address": "999 Tillman Rd",
            "address2": "",
            "city": "Fort Wayne",
            "state": "IN",
            "zip": "46816",
            "phone": "260-555-1234",
            "lat": "41.0793",
            "lng": "-85.1394",
            "hours": "<p>Mon-Fri 8am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Allen County</p>",
        },
        {
            "id": "302",
            "name": "Huntington Food Bank",
            "address": "100 N Jefferson St",
            "address2": "",
            "city": "Huntington",
            "state": "",
            "zip": "46750",
            "phone": "",
            "lat": "40.8831",
            "lng": "-85.4975",
            "hours": "",
            "url": "",
            "email": "",
            "description": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = CommunityHarvestFoodBankInScraper()
    assert scraper.scraper_id == "community_harvest_food_bank_in"
    assert "communityharvest.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = CommunityHarvestFoodBankInScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Fort Wayne Community Pantry"
    assert loc["state"] == "IN"
    assert loc["latitude"] == 41.0793


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state with IN default."""
    scraper = CommunityHarvestFoodBankInScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "IN"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_slp_response):
    """Test duplicate locations removed by ID."""
    scraper = CommunityHarvestFoodBankInScraper(test_mode=True)

    async def mock_fetch(client):
        return mock_slp_response + mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["unique_locations"] == 2


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = CommunityHarvestFoodBankInScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "community_harvest_food_bank_in"
    assert submitted[0]["food_bank"] == "Community Harvest Food Bank of NE Indiana"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = CommunityHarvestFoodBankInScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
