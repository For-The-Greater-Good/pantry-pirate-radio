"""Tests for Second Harvest of South Georgia scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.second_harvest_of_south_georgia_ga_scraper import (
    SecondHarvestOfSouthGeorgiaGaScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for South Georgia."""
    return [
        {
            "id": "301",
            "store": "Valdosta Food Pantry",
            "address": "100 S Patterson St",
            "address2": "",
            "city": "Valdosta",
            "state": "GA",
            "zip": "31601",
            "phone": "229-555-1234",
            "lat": "30.8327",
            "lng": "-83.2785",
            "hours": "<p>Monday-Friday 9am-3pm</p>",
            "url": "",
            "description": "<p>Serving Lowndes County</p>",
            "distance": "0.5",
        },
        {
            "id": "302",
            "store": "Tifton Community Pantry",
            "address": "200 Main St",
            "address2": "",
            "city": "Tifton",
            "state": "",
            "zip": "31794",
            "phone": "",
            "lat": "31.4502",
            "lng": "-83.5085",
            "hours": "",
            "url": "",
            "description": "<p>Tuesday 10am-12pm</p>",
            "distance": "10.0",
        },
    ]


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = SecondHarvestOfSouthGeorgiaGaScraper()
    assert scraper.scraper_id == "second_harvest_of_south_georgia_ga"
    assert "feedingsga.org" in scraper.ajax_url
    assert scraper.test_mode is False


def test_generate_grid_points() -> None:
    """Test grid covers South Georgia service area."""
    scraper = SecondHarvestOfSouthGeorgiaGaScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 20
    for lat, lng in points:
        assert 30.6 <= lat <= 32.2
        assert -84.5 <= lng <= -82.0


def test_parse_location(mock_wpsl_response) -> None:
    """Test parsing raw WPSL response items."""
    scraper = SecondHarvestOfSouthGeorgiaGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[0])

    assert loc["name"] == "Valdosta Food Pantry"
    assert loc["city"] == "Valdosta"
    assert loc["state"] == "GA"
    assert loc["latitude"] == 30.8327
    assert "Monday-Friday" in loc["hours"]


def test_parse_location_empty_state(mock_wpsl_response) -> None:
    """Test parsing defaults empty state to GA."""
    scraper = SecondHarvestOfSouthGeorgiaGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "GA"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_wpsl_response) -> None:
    """Test duplicate locations removed by ID."""
    scraper = SecondHarvestOfSouthGeorgiaGaScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response + mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 2


@pytest.mark.asyncio
async def test_scrape_metadata(mock_wpsl_response) -> None:
    """Test scraped locations include correct metadata."""
    scraper = SecondHarvestOfSouthGeorgiaGaScraper(test_mode=True)
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
    assert submitted[0]["source"] == "second_harvest_of_south_georgia_ga"
    assert submitted[0]["food_bank"] == "Second Harvest of South Georgia"


@pytest.mark.asyncio
async def test_scrape_empty_response() -> None:
    """Test scrape handles empty API response."""
    scraper = SecondHarvestOfSouthGeorgiaGaScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
