"""Tests for Second Harvest Mahoning Valley OH scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.second_harvest_mahoning_valley_oh_scraper import (
    SecondHarvestMahoningValleyOhScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for Mahoning Valley."""
    return [
        {
            "id": "101",
            "store": "Youngstown Community Food Pantry",
            "address": "2805 Salt Springs Rd",
            "address2": "",
            "city": "Youngstown",
            "state": "OH",
            "zip": "44509",
            "phone": "330-555-1234",
            "lat": "41.0998",
            "lng": "-80.6496",
            "hours": "<p>Monday-Friday 9:00 AM - 3:00 PM</p>",
            "url": "https://example.org",
            "description": "<p>Serving Mahoning County families</p>",
            "distance": "0.5",
        },
        {
            "id": "102",
            "store": "Warren Area Food Center",
            "address": "200 Main Ave SW",
            "address2": "Suite B",
            "city": "Warren",
            "state": "",
            "zip": "44481",
            "phone": "",
            "lat": "41.2378",
            "lng": "-80.8184",
            "hours": '<table class="wpsl-hours"><tr><td>Tuesday</td><td>10am-2pm</td></tr></table>',
            "url": "",
            "description": "<p>Bring photo ID</p>",
            "distance": "15.0",
        },
        {
            "id": "103",
            "store": "Salem Area Food Assistance",
            "address": "100 E State St",
            "address2": "",
            "city": "Salem",
            "state": "OH",
            "zip": "44460",
            "phone": "330-555-9876",
            "lat": "40.9009",
            "lng": "-80.8565",
            "hours": "",
            "url": "",
            "description": "<p>1st Saturday 9:00 AM - 11:00 AM</p>",
            "distance": "25.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SecondHarvestMahoningValleyOhScraper()
    assert scraper.scraper_id == "second_harvest_mahoning_valley_oh"
    assert "mahoningvalleysecondharvest.org" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SecondHarvestMahoningValleyOhScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers Mahoning Valley area."""
    scraper = SecondHarvestMahoningValleyOhScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 40.7 <= lat <= 41.4
        assert -81.3 <= lng <= -80.3


@pytest.mark.asyncio
async def test_parse_location(mock_wpsl_response):
    """Test parsing raw WPSL response items."""
    scraper = SecondHarvestMahoningValleyOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Youngstown Community Food Pantry"
    assert loc["city"] == "Youngstown"
    assert loc["state"] == "OH"
    assert loc["zip"] == "44509"
    assert loc["latitude"] == 41.0998
    assert loc["longitude"] == -80.6496
    assert loc["phone"] == "330-555-1234"
    assert "Monday-Friday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_wpsl_response):
    """Test parsing handles empty state field with OH default."""
    scraper = SecondHarvestMahoningValleyOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "OH"


@pytest.mark.asyncio
async def test_parse_location_with_address2(mock_wpsl_response):
    """Test parsing includes address2 in full_address."""
    scraper = SecondHarvestMahoningValleyOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Suite B" in loc["full_address"]
    assert "200 Main Ave SW" in loc["full_address"]


@pytest.mark.asyncio
async def test_parse_location_hours_table(mock_wpsl_response):
    """Test parsing extracts text from HTML hours table."""
    scraper = SecondHarvestMahoningValleyOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Tuesday" in loc["hours"]
    assert "10am-2pm" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_hours_fallback_to_description(mock_wpsl_response):
    """Test hours falls back to description when hours field is empty."""
    scraper = SecondHarvestMahoningValleyOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[2])
    assert "Saturday" in loc["hours"]
    assert "9:00 AM" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None."""
    scraper = SecondHarvestMahoningValleyOhScraper()

    item = {
        "id": "999",
        "store": "No Coords Pantry",
        "address": "123 Main St",
        "address2": "",
        "city": "Youngstown",
        "state": "OH",
        "zip": "44501",
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
    """Test that duplicate locations from overlapping grid cells are removed."""
    scraper = SecondHarvestMahoningValleyOhScraper(test_mode=True)

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
    scraper = SecondHarvestMahoningValleyOhScraper(test_mode=True)

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
    assert submitted[0]["source"] == "second_harvest_mahoning_valley_oh"
    assert submitted[0]["food_bank"] == (
        "Second Harvest Food Bank of the Mahoning Valley"
    )


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_wpsl_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = SecondHarvestMahoningValleyOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "second_harvest_mahoning_valley_oh"
    assert summary["food_bank"] == ("Second Harvest Food Bank of the Mahoning Valley")
    assert summary["source"] == "https://mahoningvalleysecondharvest.org"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = SecondHarvestMahoningValleyOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
