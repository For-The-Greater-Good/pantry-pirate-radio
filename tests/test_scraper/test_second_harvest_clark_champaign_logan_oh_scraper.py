"""Tests for Second Harvest Clark, Champaign & Logan OH scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.second_harvest_clark_champaign_logan_oh_scraper import (
    SecondHarvestClarkChampaignLoganOhScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for Clark/Champaign/Logan."""
    return [
        {
            "id": "201",
            "store": "Springfield Community Food Pantry",
            "address": "20 N Murray St",
            "address2": "",
            "city": "Springfield",
            "state": "OH",
            "zip": "45503",
            "phone": "937-555-1234",
            "lat": "39.9242",
            "lng": "-83.8088",
            "hours": "<p>Tuesday-Thursday 10:00 AM - 2:00 PM</p>",
            "url": "",
            "description": "<p>Serving Clark County families</p>",
            "distance": "0.5",
        },
        {
            "id": "202",
            "store": "Urbana Food Distribution",
            "address": "300 Scioto St",
            "address2": "",
            "city": "Urbana",
            "state": "",
            "zip": "43078",
            "phone": "",
            "lat": "40.1084",
            "lng": "-83.7524",
            "hours": "",
            "url": "",
            "description": "<p>2nd and 4th Wednesday 9 AM - 12 PM</p>",
            "distance": "20.0",
        },
        {
            "id": "203",
            "store": "Bellefontaine Area Pantry",
            "address": "100 S Main St",
            "address2": "",
            "city": "Bellefontaine",
            "state": "OH",
            "zip": "43311",
            "phone": "937-555-9876",
            "lat": "40.3612",
            "lng": "-83.7594",
            "hours": "",
            "url": "",
            "description": "<p>Monday and Friday 1:00 PM - 4:00 PM</p>",
            "distance": "30.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    assert scraper.scraper_id == "second_harvest_clark_champaign_logan_oh"
    assert "theshfb.org" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers Clark/Champaign/Logan area."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 39.7 <= lat <= 40.4
        assert -84.1 <= lng <= -83.3


@pytest.mark.asyncio
async def test_parse_location(mock_wpsl_response):
    """Test parsing raw WPSL response items."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Springfield Community Food Pantry"
    assert loc["city"] == "Springfield"
    assert loc["state"] == "OH"
    assert loc["zip"] == "45503"
    assert loc["latitude"] == 39.9242
    assert loc["longitude"] == -83.8088
    assert "Tuesday-Thursday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_wpsl_response):
    """Test parsing handles empty state field with OH default."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "OH"


@pytest.mark.asyncio
async def test_parse_location_hours_fallback(mock_wpsl_response):
    """Test hours falls back to description when hours field is empty."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Wednesday" in loc["hours"]
    assert "9 AM" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper()

    item = {
        "id": "999",
        "store": "No Coords",
        "address": "123 Main",
        "address2": "",
        "city": "Springfield",
        "state": "OH",
        "zip": "45503",
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
    scraper = SecondHarvestClarkChampaignLoganOhScraper(test_mode=True)

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
    scraper = SecondHarvestClarkChampaignLoganOhScraper(test_mode=True)

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
    assert submitted[0]["source"] == "second_harvest_clark_champaign_logan_oh"
    assert submitted[0]["food_bank"] == (
        "Second Harvest Food Bank of Clark, Champaign & Logan Counties"
    )


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_wpsl_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "second_harvest_clark_champaign_logan_oh"
    assert summary["source"] == "https://www.theshfb.org"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
