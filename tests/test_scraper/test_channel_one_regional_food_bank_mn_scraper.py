"""Tests for Channel One Regional Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.channel_one_regional_food_bank_mn_scraper import (
    ChannelOneRegionalFoodBankMnScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "101",
            "name": "Rochester Food Shelf",
            "address": "1201 S Broadway",
            "address2": "",
            "city": "Rochester",
            "state": "MN",
            "zip": "55904",
            "phone": "507-555-1234",
            "lat": "44.0121",
            "lng": "-92.4802",
            "hours": "<p>Mon-Fri 9am-4pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Olmsted County</p>",
        },
        {
            "id": "102",
            "name": "Winona Community Kitchen",
            "address": "200 E 3rd St",
            "address2": "",
            "city": "Winona",
            "state": "",
            "zip": "55987",
            "phone": "",
            "lat": "44.0499",
            "lng": "-91.6393",
            "hours": "",
            "url": "",
            "email": "",
            "description": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = ChannelOneRegionalFoodBankMnScraper()
    assert scraper.scraper_id == "channel_one_regional_food_bank_mn"
    assert "chfrb.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = ChannelOneRegionalFoodBankMnScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Rochester Food Shelf"
    assert loc["state"] == "MN"
    assert loc["latitude"] == 44.0121


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state with MN default."""
    scraper = ChannelOneRegionalFoodBankMnScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "MN"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = ChannelOneRegionalFoodBankMnScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "channel_one_regional_food_bank_mn"
    assert submitted[0]["food_bank"] == "Channel One Regional Food Bank"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_slp_response):
    """Test duplicate locations removed by ID."""
    scraper = ChannelOneRegionalFoodBankMnScraper(test_mode=True)

    async def mock_fetch(client):
        return mock_slp_response + mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 2


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = ChannelOneRegionalFoodBankMnScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
