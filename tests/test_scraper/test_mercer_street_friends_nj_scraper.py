"""Tests for Mercer Street Friends Food Bank scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.mercer_street_friends_nj_scraper import (
    MercerStreetFriendsNjScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response."""
    return [
        {
            "id": "201",
            "name": "Trenton Food Pantry",
            "address": "120 S Broad St",
            "address2": "",
            "city": "Trenton",
            "state": "NJ",
            "zip": "08608",
            "phone": "609-555-1234",
            "lat": "40.2171",
            "lng": "-74.7429",
            "hours": "<p>Tue & Thu 10am-1pm</p>",
            "url": "",
            "email": "",
            "description": "<p>Serving Mercer County</p>",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = MercerStreetFriendsNjScraper()
    assert scraper.scraper_id == "mercer_street_friends_nj"
    assert "mercerstreetfriends.org" in scraper.ajax_url


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = MercerStreetFriendsNjScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Trenton Food Pantry"
    assert loc["state"] == "NJ"


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test scraped locations include correct metadata."""
    scraper = MercerStreetFriendsNjScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert submitted[0]["source"] == "mercer_street_friends_nj"
    assert submitted[0]["food_bank"] == "Mercer Street Friends Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = MercerStreetFriendsNjScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="j"):
            result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
