"""Tests for Second Harvest North Central OH scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.second_harvest_north_central_oh_scraper import (
    SecondHarvestNorthCentralOhScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for North Central Ohio."""
    return [
        {
            "id": "301",
            "store": "Lorain County Food Pantry",
            "address": "5510 Baumhart Rd",
            "address2": "",
            "city": "Lorain",
            "state": "OH",
            "zip": "44053",
            "phone": "440-555-1234",
            "lat": "41.4528",
            "lng": "-82.1818",
            "hours": "<p>Monday-Friday 8:00 AM - 4:30 PM</p>",
            "url": "",
            "description": "<p>Serving Lorain County</p>",
            "distance": "0.5",
        },
        {
            "id": "302",
            "store": "Erie County Assistance",
            "address": "100 Columbus Ave",
            "address2": "",
            "city": "Sandusky",
            "state": "",
            "zip": "44870",
            "phone": "",
            "lat": "41.4490",
            "lng": "-82.7079",
            "hours": "",
            "url": "",
            "description": "<p>Wednesday 10 AM - 1 PM</p>",
            "distance": "20.0",
        },
        {
            "id": "303",
            "store": "Huron County Food Center",
            "address": "200 W Main St",
            "address2": "",
            "city": "Norwalk",
            "state": "OH",
            "zip": "44857",
            "phone": "419-555-9876",
            "lat": "41.2431",
            "lng": "-82.6157",
            "hours": "",
            "url": "",
            "description": "<p>1st and 3rd Friday 9 AM - 12 PM</p>",
            "distance": "25.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SecondHarvestNorthCentralOhScraper()
    assert scraper.scraper_id == "second_harvest_north_central_oh"
    assert "secondharvestfoodbank.org" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SecondHarvestNorthCentralOhScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers North Central Ohio area."""
    scraper = SecondHarvestNorthCentralOhScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 40.7 <= lat <= 41.5
        assert -83.2 <= lng <= -81.9


@pytest.mark.asyncio
async def test_parse_location(mock_wpsl_response):
    """Test parsing raw WPSL response items."""
    scraper = SecondHarvestNorthCentralOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Lorain County Food Pantry"
    assert loc["city"] == "Lorain"
    assert loc["state"] == "OH"
    assert loc["latitude"] == 41.4528
    assert loc["longitude"] == -82.1818
    assert "Monday-Friday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_wpsl_response):
    """Test parsing handles empty state field with OH default."""
    scraper = SecondHarvestNorthCentralOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "OH"


@pytest.mark.asyncio
async def test_parse_location_hours_fallback(mock_wpsl_response):
    """Test hours falls back to description when hours field is empty."""
    scraper = SecondHarvestNorthCentralOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Wednesday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None."""
    scraper = SecondHarvestNorthCentralOhScraper()

    item = {
        "id": "999",
        "store": "No Coords",
        "address": "123 Main",
        "address2": "",
        "city": "Lorain",
        "state": "OH",
        "zip": "44053",
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
    scraper = SecondHarvestNorthCentralOhScraper(test_mode=True)

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
    scraper = SecondHarvestNorthCentralOhScraper(test_mode=True)

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
    assert submitted[0]["source"] == "second_harvest_north_central_oh"
    assert submitted[0]["food_bank"] == (
        "Second Harvest Food Bank of North Central Ohio"
    )


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_wpsl_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = SecondHarvestNorthCentralOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "second_harvest_north_central_oh"
    assert summary["source"] == "https://www.secondharvestfoodbank.org"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = SecondHarvestNorthCentralOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
