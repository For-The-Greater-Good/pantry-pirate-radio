"""Tests for Forgotten Harvest scraper."""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.scraper.scrapers.forgotten_harvest_mi_scraper import (
    ForgottenHarvestMiScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response."""
    return [
        {
            "id": "21978",
            "store": "Avalon Village",
            "address": "24 Avalon",
            "address2": "",
            "city": "Highland Park",
            "state": "MI",
            "zip": "48203",
            "phone": "",
            "lat": "42.400087",
            "lng": "-83.094577",
            "hours": "",
            "url": "",
            "description": "<p>1st &amp; 3rd Saturdays<br />9:00 AM - 11:00 AM</p>",
            "distance": "0.3",
        },
        {
            "id": "21009",
            "store": "MP-Prayer Temple of Love",
            "address": "12375 Woodward Ave",
            "address2": "",
            "city": "Highland Park",
            "state": "",
            "zip": "48203",
            "phone": "",
            "lat": "42.397647",
            "lng": "-83.092203",
            "hours": '<table class="wpsl-opening-hours"><tr><td>Monday</td><td>10am-1pm</td></tr></table>',
            "url": "",
            "description": "<p>2nd Monday of the month<br />10:00 am-1:00 pm</p>",
            "distance": "0.4",
        },
        {
            "id": "21117",
            "store": "Cass Community Social Services",
            "address": "11850 Woodrow Wilson St",
            "address2": "Suite A",
            "city": "Detroit",
            "state": "MI",
            "zip": "48206",
            "phone": "313-883-2277",
            "lat": "42.388677",
            "lng": "-83.104548",
            "hours": "",
            "url": "https://casscommunity.org",
            "description": "<p>Serving Daily 8:00am-7:00pm</p>",
            "distance": "0.8",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = ForgottenHarvestMiScraper()
    assert scraper.scraper_id == "forgotten_harvest_mi"
    assert "forgottenharvest.org" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = ForgottenHarvestMiScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers metro Detroit area."""
    scraper = ForgottenHarvestMiScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 50
    # Verify points are in metro Detroit area
    for lat, lng in points:
        assert 42.0 <= lat <= 42.8
        assert -83.6 <= lng <= -82.7


@pytest.mark.asyncio
async def test_parse_location(mock_wpsl_response):
    """Test parsing raw WPSL response items."""
    scraper = ForgottenHarvestMiScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Avalon Village"
    assert loc["city"] == "Highland Park"
    assert loc["state"] == "MI"
    assert loc["latitude"] == 42.400087
    assert loc["longitude"] == -83.094577
    assert "Saturdays" in loc["description"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_wpsl_response):
    """Test parsing handles empty state field."""
    scraper = ForgottenHarvestMiScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "MI"  # Defaults to MI


@pytest.mark.asyncio
async def test_parse_location_with_address2(mock_wpsl_response):
    """Test parsing includes address2 in full_address."""
    scraper = ForgottenHarvestMiScraper()

    loc = scraper._parse_location(mock_wpsl_response[2])
    assert "Suite A" in loc["full_address"]


@pytest.mark.asyncio
async def test_parse_location_hours_table(mock_wpsl_response):
    """Test parsing extracts text from HTML hours table."""
    scraper = ForgottenHarvestMiScraper()

    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Monday" in loc["hours"]
    assert "10am-1pm" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None (validator handles geocoding)."""
    scraper = ForgottenHarvestMiScraper()

    item = {
        "id": "999",
        "store": "No Coords Pantry",
        "address": "123 Main St",
        "address2": "",
        "city": "Detroit",
        "state": "MI",
        "zip": "48201",
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
    scraper = ForgottenHarvestMiScraper(test_mode=True)

    # Simulate two grid points returning overlapping results
    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    # Even though we query 3 grid points (test_mode), each returning 3 items,
    # dedup by ID means we only get 3 unique locations
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3


@pytest.mark.asyncio
async def test_scrape_metadata(mock_wpsl_response):
    """Test that scraped locations include correct metadata."""
    scraper = ForgottenHarvestMiScraper(test_mode=True)

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
    assert submitted[0]["source"] == "forgotten_harvest_mi"
    assert submitted[0]["food_bank"] == "Forgotten Harvest"


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_wpsl_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = ForgottenHarvestMiScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "forgotten_harvest_mi"
    assert summary["food_bank"] == "Forgotten Harvest"
    assert summary["source"] == "https://www.forgottenharvest.org/find-food/"
