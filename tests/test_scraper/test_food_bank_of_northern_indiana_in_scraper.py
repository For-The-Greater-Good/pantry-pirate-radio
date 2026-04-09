"""Tests for Food Bank of Northern Indiana scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_northern_indiana_in_scraper import (
    FoodBankOfNorthernIndianaInScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP AJAX API response for Northern Indiana."""
    return [
        {
            "id": "101",
            "name": "South Bend Food Pantry",
            "address": "200 N Michigan St",
            "address2": "",
            "city": "South Bend",
            "state": "IN",
            "zip": "46601",
            "phone": "574-555-1234",
            "lat": "41.6764",
            "lng": "-86.2520",
            "hours": "<p>Mon-Fri 9am-4pm</p>",
            "url": "",
            "email": "info@sbpantry.org",
            "description": "<p>Serving St. Joseph County</p>",
            "tags": "",
        },
        {
            "id": "102",
            "name": "Elkhart Community Kitchen",
            "address": "300 S Main St",
            "address2": "Suite B",
            "city": "Elkhart",
            "state": "",
            "zip": "46516",
            "phone": "",
            "lat": "41.6820",
            "lng": "-85.9767",
            "hours": "",
            "url": "",
            "email": "",
            "description": "<p>Tue & Thu 10am-1pm</p>",
            "tags": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfNorthernIndianaInScraper()
    assert scraper.scraper_id == "food_bank_of_northern_indiana_in"
    assert "feedindiana.org" in scraper.ajax_url
    assert scraper.test_mode is False
    assert scraper.center_lat == 41.6764


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = FoodBankOfNorthernIndianaInScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfNorthernIndianaInScraper()
    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "South Bend Food Pantry"
    assert loc["city"] == "South Bend"
    assert loc["state"] == "IN"
    assert loc["latitude"] == 41.6764
    assert loc["longitude"] == -86.2520
    assert "Mon-Fri" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state field with IN default."""
    scraper = FoodBankOfNorthernIndianaInScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "IN"


@pytest.mark.asyncio
async def test_parse_location_with_address2(mock_slp_response):
    """Test parsing includes address2 in full_address."""
    scraper = FoodBankOfNorthernIndianaInScraper()
    loc = scraper._parse_location(mock_slp_response[1])
    assert "Suite B" in loc["full_address"]


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_slp_response):
    """Test that duplicate locations are removed by ID."""
    scraper = FoodBankOfNorthernIndianaInScraper(test_mode=True)
    duplicated = mock_slp_response + mock_slp_response

    async def mock_fetch(client):
        return duplicated

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_locations_found"] == 4
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test that scraped locations include correct metadata."""
    scraper = FoodBankOfNorthernIndianaInScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert len(submitted) == 1
    assert submitted[0]["source"] == "food_bank_of_northern_indiana_in"
    assert submitted[0]["food_bank"] == "Food Bank of Northern Indiana"


@pytest.mark.asyncio
async def test_fetch_locations_handles_dict_response():
    """Test fetch handles SLP dict response with 'response' key."""
    scraper = FoodBankOfNorthernIndianaInScraper()
    mock_response = httpx.Response(
        200,
        json={"response": [{"id": "1", "name": "Test"}]},
        request=httpx.Request("POST", scraper.ajax_url),
    )
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations(client)
            assert len(result) == 1


@pytest.mark.asyncio
async def test_fetch_locations_handles_error():
    """Test fetch gracefully handles errors."""
    scraper = FoodBankOfNorthernIndianaInScraper()
    with patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.ConnectError("Connection failed"),
    ):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations(client)
            assert result == []


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response."""
    scraper = FoodBankOfNorthernIndianaInScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
