"""Tests for Second Harvest Food Bank of NW Pennsylvania scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.second_harvest_food_bank_of_nw_pennsylvania_pa_scraper import (
    SecondHarvestFoodBankOfNwPennsylvaniaPaScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for NW PA."""
    return [
        {
            "id": "101",
            "store": "Erie Food Pantry",
            "address": "100 Main St",
            "address2": "",
            "city": "Erie",
            "state": "PA",
            "zip": "16501",
            "phone": "814-555-1234",
            "lat": "42.1292",
            "lng": "-80.0851",
            "hours": "<p>Monday-Friday 9am-4pm</p>",
            "url": "",
            "description": "<p>Serving Erie County</p>",
            "distance": "0.5",
        },
        {
            "id": "102",
            "store": "Meadville Community Pantry",
            "address": "200 Chestnut St",
            "address2": "Suite B",
            "city": "Meadville",
            "state": "",
            "zip": "16335",
            "phone": "",
            "lat": "41.6414",
            "lng": "-80.1514",
            "hours": "",
            "url": "",
            "description": "<p>Tuesday and Thursday 10am-2pm</p>",
            "distance": "15.0",
        },
        {
            "id": "103",
            "store": "Warren Soup Kitchen",
            "address": "300 Market St",
            "address2": "",
            "city": "Warren",
            "state": "PA",
            "zip": "16365",
            "phone": "814-555-9876",
            "lat": "41.8431",
            "lng": "-79.1450",
            "hours": "<table><tr><td>Mon-Fri</td><td>11am-1pm</td></tr></table>",
            "url": "https://warrensoupkitchen.org",
            "description": "",
            "distance": "25.0",
        },
    ]


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()
    assert scraper.scraper_id == "second_harvest_food_bank_of_nw_pennsylvania_pa"
    assert "nwpafoodbank.org" in scraper.ajax_url
    assert scraper.test_mode is False


def test_scraper_test_mode() -> None:
    """Test scraper initializes in test mode."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


def test_generate_grid_points() -> None:
    """Test grid covers NW PA service area."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 20
    for lat, lng in points:
        assert 41.0 <= lat <= 42.3
        assert -80.6 <= lng <= -77.7


def test_parse_location(mock_wpsl_response) -> None:
    """Test parsing raw WPSL response items."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()

    loc = scraper._parse_location(mock_wpsl_response[0])
    assert loc["name"] == "Erie Food Pantry"
    assert loc["city"] == "Erie"
    assert loc["state"] == "PA"
    assert loc["zip"] == "16501"
    assert loc["latitude"] == 42.1292
    assert loc["longitude"] == -80.0851
    assert "Monday-Friday" in loc["hours"]


def test_parse_location_empty_state(mock_wpsl_response) -> None:
    """Test parsing handles empty state field with PA default."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "PA"


def test_parse_location_with_address2(mock_wpsl_response) -> None:
    """Test parsing includes address2 in full_address."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Suite B" in loc["full_address"]


def test_parse_location_hours_table(mock_wpsl_response) -> None:
    """Test parsing extracts text from HTML hours table."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()
    loc = scraper._parse_location(mock_wpsl_response[2])
    assert "Mon-Fri" in loc["hours"]
    assert "11am-1pm" in loc["hours"]


def test_parse_location_hours_fallback(mock_wpsl_response) -> None:
    """Test hours falls back to description when hours field empty."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Tuesday" in loc["hours"]


def test_parse_location_none_coords() -> None:
    """Test parsing handles None coordinates."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper()
    item = {
        "id": "999",
        "store": "No Coords",
        "address": "123 Main St",
        "address2": "",
        "city": "Erie",
        "state": "PA",
        "zip": "16501",
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
async def test_scrape_deduplication(mock_wpsl_response) -> None:
    """Test duplicate locations removed by ID."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3


@pytest.mark.asyncio
async def test_scrape_metadata(mock_wpsl_response) -> None:
    """Test scraped locations include correct metadata."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper(test_mode=True)

    submitted: list[str] = []

    def capture(data):
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response[:1]

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert len(submitted) >= 1
    assert submitted[0]["source"] == "second_harvest_food_bank_of_nw_pennsylvania_pa"
    assert (
        submitted[0]["food_bank"]
        == "Second Harvest Food Bank of Northwest Pennsylvania"
    )


@pytest.mark.asyncio
async def test_scrape_summary_format(mock_wpsl_response) -> None:
    """Test scrape returns valid summary with required fields."""
    scraper = SecondHarvestFoodBankOfNwPennsylvaniaPaScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "second_harvest_food_bank_of_nw_pennsylvania_pa"
    assert "total_locations_found" in summary
    assert "unique_locations" in summary
    assert "total_jobs_created" in summary
    assert summary["source"] == "https://nwpafoodbank.org/need-help/agency-locator/"
