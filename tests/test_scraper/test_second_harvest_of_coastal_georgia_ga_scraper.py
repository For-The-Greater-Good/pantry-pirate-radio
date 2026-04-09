"""Tests for Second Harvest of Coastal Georgia scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.second_harvest_of_coastal_georgia_ga_scraper import (
    SecondHarvestOfCoastalGeorgiaGaScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for Coastal Georgia."""
    return [
        {
            "id": "401",
            "store": "Savannah Food Pantry",
            "address": "100 Abercorn St",
            "address2": "",
            "city": "Savannah",
            "state": "GA",
            "zip": "31401",
            "phone": "912-555-1234",
            "lat": "32.0809",
            "lng": "-81.0912",
            "hours": "<p>Mon-Fri 9am-4pm</p>",
            "url": "",
            "description": "<p>Serving Chatham County</p>",
            "distance": "0.5",
        },
        {
            "id": "402",
            "store": "Brunswick Helping Hands",
            "address": "200 Gloucester St",
            "address2": "",
            "city": "Brunswick",
            "state": "",
            "zip": "31520",
            "phone": "",
            "lat": "31.1499",
            "lng": "-81.4915",
            "hours": "",
            "url": "",
            "description": "<p>Wednesday 10am-1pm</p>",
            "distance": "10.0",
        },
    ]


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = SecondHarvestOfCoastalGeorgiaGaScraper()
    assert scraper.scraper_id == "second_harvest_of_coastal_georgia_ga"
    assert "helpendhunger.org" in scraper.ajax_url


def test_generate_grid_points() -> None:
    """Test grid covers Coastal Georgia service area."""
    scraper = SecondHarvestOfCoastalGeorgiaGaScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 30.7 <= lat <= 32.8
        assert -82.8 <= lng <= -80.8


def test_parse_location(mock_wpsl_response) -> None:
    """Test parsing raw WPSL response items."""
    scraper = SecondHarvestOfCoastalGeorgiaGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[0])

    assert loc["name"] == "Savannah Food Pantry"
    assert loc["city"] == "Savannah"
    assert loc["state"] == "GA"
    assert "Mon-Fri" in loc["hours"]


def test_parse_location_empty_state(mock_wpsl_response) -> None:
    """Test parsing defaults empty state to GA."""
    scraper = SecondHarvestOfCoastalGeorgiaGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "GA"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_wpsl_response) -> None:
    """Test duplicate locations removed by ID."""
    scraper = SecondHarvestOfCoastalGeorgiaGaScraper(test_mode=True)

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
    scraper = SecondHarvestOfCoastalGeorgiaGaScraper(test_mode=True)
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
    assert submitted[0]["source"] == "second_harvest_of_coastal_georgia_ga"
    assert submitted[0]["food_bank"] == "Second Harvest of Coastal Georgia"
