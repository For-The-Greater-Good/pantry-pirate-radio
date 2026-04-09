"""Tests for The Foodbank, Inc. (Dayton) OH scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.the_foodbank_inc_oh_scraper import (
    TheFoodbankIncOhScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for The Foodbank Dayton."""
    return [
        {
            "id": "701",
            "store": "Dayton Community Food Pantry",
            "address": "56 Armor Pl",
            "address2": "",
            "city": "Dayton",
            "state": "OH",
            "zip": "45417",
            "phone": "937-555-1234",
            "lat": "39.7589",
            "lng": "-84.2008",
            "hours": "<p>Monday-Friday 8:30 AM - 4:30 PM</p>",
            "url": "https://example.org",
            "description": "<p>Serving Montgomery County</p>",
            "distance": "0.5",
        },
        {
            "id": "702",
            "store": "Xenia Area Food Center",
            "address": "100 N Detroit St",
            "address2": "",
            "city": "Xenia",
            "state": "",
            "zip": "45385",
            "phone": "",
            "lat": "39.6845",
            "lng": "-83.9296",
            "hours": '<table class="wpsl-hours"><tr><td>Tuesday</td><td>9am-12pm</td></tr></table>',
            "url": "",
            "description": "<p>Bring photo ID and proof of address</p>",
            "distance": "15.0",
        },
        {
            "id": "703",
            "store": "Eaton Food Assistance",
            "address": "200 N Barron St",
            "address2": "Suite A",
            "city": "Eaton",
            "state": "OH",
            "zip": "45320",
            "phone": "937-555-9876",
            "lat": "39.7437",
            "lng": "-84.6366",
            "hours": "",
            "url": "",
            "description": "<p>1st and 3rd Thursday 10 AM - 1 PM</p>",
            "distance": "30.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = TheFoodbankIncOhScraper()
    assert scraper.scraper_id == "the_foodbank_inc_oh"
    assert "thefoodbankdayton.org" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = TheFoodbankIncOhScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers Dayton area."""
    scraper = TheFoodbankIncOhScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 39.5 <= lat <= 40.0
        assert -84.8 <= lng <= -83.8


@pytest.mark.asyncio
async def test_parse_location(mock_wpsl_response):
    """Test parsing raw WPSL response items."""
    scraper = TheFoodbankIncOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Dayton Community Food Pantry"
    assert loc["city"] == "Dayton"
    assert loc["state"] == "OH"
    assert loc["zip"] == "45417"
    assert loc["latitude"] == 39.7589
    assert loc["longitude"] == -84.2008
    assert "Monday-Friday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_wpsl_response):
    """Test parsing handles empty state field with OH default."""
    scraper = TheFoodbankIncOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "OH"


@pytest.mark.asyncio
async def test_parse_location_with_address2(mock_wpsl_response):
    """Test parsing includes address2 in full_address."""
    scraper = TheFoodbankIncOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[2])
    assert "Suite A" in loc["full_address"]


@pytest.mark.asyncio
async def test_parse_location_hours_table(mock_wpsl_response):
    """Test parsing extracts text from HTML hours table."""
    scraper = TheFoodbankIncOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Tuesday" in loc["hours"]
    assert "9am-12pm" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_hours_fallback(mock_wpsl_response):
    """Test hours falls back to description when hours field is empty."""
    scraper = TheFoodbankIncOhScraper()

    loc = scraper._parse_location(mock_wpsl_response[2])
    assert "Thursday" in loc["hours"]
    assert "10 AM" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None."""
    scraper = TheFoodbankIncOhScraper()

    item = {
        "id": "999",
        "store": "No Coords",
        "address": "123 Main",
        "address2": "",
        "city": "Dayton",
        "state": "OH",
        "zip": "45417",
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
    scraper = TheFoodbankIncOhScraper(test_mode=True)

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
    scraper = TheFoodbankIncOhScraper(test_mode=True)

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
    assert submitted[0]["source"] == "the_foodbank_inc_oh"
    assert submitted[0]["food_bank"] == "The Foodbank, Inc."


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_wpsl_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = TheFoodbankIncOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "the_foodbank_inc_oh"
    assert summary["food_bank"] == "The Foodbank, Inc."
    assert summary["source"] == "https://thefoodbankdayton.org"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = TheFoodbankIncOhScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
