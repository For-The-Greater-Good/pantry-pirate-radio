"""Tests for Shared Harvest Foodbank OH scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.shared_harvest_foodbank_oh_scraper import (
    SharedHarvestFoodbankOhScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for Shared Harvest."""
    return [
        {
            "id": "601",
            "store": "Fairfield Community Pantry",
            "address": "5901 Dixie Hwy",
            "address2": "",
            "city": "Fairfield",
            "state": "OH",
            "zip": "45014",
            "phone": "513-555-1234",
            "lat": "39.3454",
            "lng": "-84.5603",
            "hours": "<p>Monday-Friday 9:00 AM - 4:00 PM</p>",
            "url": "https://example.org",
            "description": "<p>Serving Butler County families</p>",
            "distance": "0.5",
        },
        {
            "id": "602",
            "store": "Hamilton Food Assistance Center",
            "address": "200 High St",
            "address2": "",
            "city": "Hamilton",
            "state": "",
            "zip": "45011",
            "phone": "",
            "lat": "39.3995",
            "lng": "-84.5613",
            "hours": "",
            "url": "",
            "description": "<p>Wednesday 10 AM - 1 PM</p>",
            "distance": "10.0",
        },
        {
            "id": "603",
            "store": "Greenville Area Pantry",
            "address": "100 N Broadway",
            "address2": "",
            "city": "Greenville",
            "state": "OH",
            "zip": "45331",
            "phone": "937-555-9876",
            "lat": "40.1031",
            "lng": "-84.6330",
            "hours": "",
            "url": "",
            "description": "<p>1st and 3rd Tuesday 9:00 AM - 12:00 PM</p>",
            "distance": "40.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SharedHarvestFoodbankOhScraper()
    assert scraper.scraper_id == "shared_harvest_foodbank_oh"
    assert "sharedharvest.org" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SharedHarvestFoodbankOhScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers SW Ohio area."""
    scraper = SharedHarvestFoodbankOhScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 39.3 <= lat <= 40.2
        assert -84.9 <= lng <= -84.0


@pytest.mark.asyncio
async def test_parse_location(mock_wpsl_response):
    """Test parsing raw WPSL response items."""
    scraper = SharedHarvestFoodbankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Fairfield Community Pantry"
    assert loc["city"] == "Fairfield"
    assert loc["state"] == "OH"
    assert loc["zip"] == "45014"
    assert loc["latitude"] == 39.3454
    assert loc["longitude"] == -84.5603
    assert "Monday-Friday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_wpsl_response):
    """Test parsing handles empty state field with OH default."""
    scraper = SharedHarvestFoodbankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "OH"


@pytest.mark.asyncio
async def test_parse_location_hours_fallback(mock_wpsl_response):
    """Test hours falls back to description when hours field is empty."""
    scraper = SharedHarvestFoodbankOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Wednesday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None."""
    scraper = SharedHarvestFoodbankOhScraper()

    item = {
        "id": "999",
        "store": "No Coords",
        "address": "123 Main",
        "address2": "",
        "city": "Fairfield",
        "state": "OH",
        "zip": "45014",
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
    scraper = SharedHarvestFoodbankOhScraper(test_mode=True)

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
    scraper = SharedHarvestFoodbankOhScraper(test_mode=True)

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
    assert submitted[0]["source"] == "shared_harvest_foodbank_oh"
    assert submitted[0]["food_bank"] == "Shared Harvest Foodbank"


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_wpsl_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = SharedHarvestFoodbankOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "shared_harvest_foodbank_oh"
    assert summary["food_bank"] == "Shared Harvest Foodbank"
    assert summary["source"] == "https://www.sharedharvest.org"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = SharedHarvestFoodbankOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
