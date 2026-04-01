"""Tests for West Ohio Food Bank OH scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.west_ohio_food_bank_oh_scraper import (
    WestOhioFoodBankOhScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for West Ohio."""
    return [
        {
            "id": "401",
            "store": "Lima Community Food Pantry",
            "address": "1380 E Kibby St",
            "address2": "",
            "city": "Lima",
            "state": "OH",
            "zip": "45804",
            "phone": "419-555-1234",
            "lat": "40.7309",
            "lng": "-84.0856",
            "hours": "<p>Monday-Friday 8:00 AM - 4:00 PM</p>",
            "url": "",
            "description": "<p>Serving Allen County families</p>",
            "distance": "0.5",
        },
        {
            "id": "402",
            "store": "Findlay Food Assistance",
            "address": "200 W Main Cross St",
            "address2": "Rm 3",
            "city": "Findlay",
            "state": "",
            "zip": "45840",
            "phone": "",
            "lat": "41.0442",
            "lng": "-83.6499",
            "hours": "",
            "url": "",
            "description": "<p>Tuesday and Thursday 10 AM - 2 PM</p>",
            "distance": "20.0",
        },
        {
            "id": "403",
            "store": "Van Wert Area Pantry",
            "address": "300 S Washington St",
            "address2": "",
            "city": "Van Wert",
            "state": "OH",
            "zip": "45891",
            "phone": "419-555-9876",
            "lat": "40.8695",
            "lng": "-84.5841",
            "hours": "",
            "url": "",
            "description": "",
            "distance": "30.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = WestOhioFoodBankOhScraper()
    assert scraper.scraper_id == "west_ohio_food_bank_oh"
    assert "wofb.org" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = WestOhioFoodBankOhScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers West Ohio area."""
    scraper = WestOhioFoodBankOhScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 20
    for lat, lng in points:
        assert 40.2 <= lat <= 41.2
        assert -84.8 <= lng <= -83.5


@pytest.mark.asyncio
async def test_parse_location(mock_wpsl_response):
    """Test parsing raw WPSL response items."""
    scraper = WestOhioFoodBankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Lima Community Food Pantry"
    assert loc["city"] == "Lima"
    assert loc["state"] == "OH"
    assert loc["zip"] == "45804"
    assert loc["latitude"] == 40.7309
    assert loc["longitude"] == -84.0856
    assert "Monday-Friday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_wpsl_response):
    """Test parsing handles empty state field with OH default."""
    scraper = WestOhioFoodBankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "OH"


@pytest.mark.asyncio
async def test_parse_location_with_address2(mock_wpsl_response):
    """Test parsing includes address2 in full_address."""
    scraper = WestOhioFoodBankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Rm 3" in loc["full_address"]


@pytest.mark.asyncio
async def test_parse_location_hours_fallback(mock_wpsl_response):
    """Test hours falls back to description when hours field is empty."""
    scraper = WestOhioFoodBankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Tuesday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_hours_and_description(mock_wpsl_response):
    """Test parsing handles both hours and description being empty."""
    scraper = WestOhioFoodBankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[2])
    assert loc["hours"] == ""
    assert loc["description"] == ""


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None."""
    scraper = WestOhioFoodBankOhScraper()

    item = {
        "id": "999",
        "store": "No Coords",
        "address": "123 Main",
        "address2": "",
        "city": "Lima",
        "state": "OH",
        "zip": "45804",
        "phone": "",
        "lat": None,
        "lng": None,
        "hours": "",
        "url": "",
        "description": "",
    }
    loc = scraper._parse_location(item)
    assert loc["latitude"] is None
    assert loc["longitude"] is None


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_wpsl_response):
    """Test that duplicate locations are removed."""
    scraper = WestOhioFoodBankOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3


@pytest.mark.asyncio
async def test_scrape_metadata(mock_wpsl_response):
    """Test that scraped locations include correct metadata."""
    scraper = WestOhioFoodBankOhScraper(test_mode=True)

    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response[:1]

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert len(submitted) >= 1
    assert submitted[0]["source"] == "west_ohio_food_bank_oh"
    assert submitted[0]["food_bank"] == "West Ohio Food Bank"


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_wpsl_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = WestOhioFoodBankOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "west_ohio_food_bank_oh"
    assert summary["food_bank"] == "West Ohio Food Bank"
    assert summary["source"] == "https://wofb.org"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = WestOhioFoodBankOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
