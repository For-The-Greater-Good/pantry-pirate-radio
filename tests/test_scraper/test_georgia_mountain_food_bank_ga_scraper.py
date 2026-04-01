"""Tests for Georgia Mountain Food Bank scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.georgia_mountain_food_bank_ga_scraper import (
    GeorgiaMountainFoodBankGaScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for NE Georgia."""
    return [
        {
            "id": "801",
            "store": "Gainesville Community Pantry",
            "address": "100 Spring St",
            "address2": "",
            "city": "Gainesville",
            "state": "GA",
            "zip": "30501",
            "phone": "770-555-1234",
            "lat": "34.2979",
            "lng": "-83.8241",
            "hours": "<p>Mon-Thu 9am-4pm</p>",
            "url": "",
            "description": "<p>Serving Hall County</p>",
            "distance": "0.5",
        },
        {
            "id": "802",
            "store": "Dahlonega Food Center",
            "address": "200 Main St",
            "address2": "Unit C",
            "city": "Dahlonega",
            "state": "",
            "zip": "30533",
            "phone": "",
            "lat": "34.5328",
            "lng": "-83.9849",
            "hours": "",
            "url": "",
            "description": "<p>Friday 10am-12pm</p>",
            "distance": "10.0",
        },
    ]


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = GeorgiaMountainFoodBankGaScraper()
    assert scraper.scraper_id == "georgia_mountain_food_bank_ga"
    assert "gamountainfoodbank.org" in scraper.ajax_url


def test_generate_grid_points() -> None:
    """Test grid covers NE Georgia 5-county area."""
    scraper = GeorgiaMountainFoodBankGaScraper()
    points = scraper._generate_grid_points()
    # Smaller area, finer grid, should have reasonable count
    assert len(points) > 15
    for lat, lng in points:
        assert 34.1 <= lat <= 34.9
        assert -84.3 <= lng <= -83.5


def test_parse_location(mock_wpsl_response) -> None:
    """Test parsing raw WPSL response items."""
    scraper = GeorgiaMountainFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[0])

    assert loc["name"] == "Gainesville Community Pantry"
    assert loc["state"] == "GA"
    assert loc["latitude"] == 34.2979


def test_parse_location_empty_state(mock_wpsl_response) -> None:
    """Test parsing defaults empty state to GA."""
    scraper = GeorgiaMountainFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "GA"


def test_parse_location_with_address2(mock_wpsl_response) -> None:
    """Test parsing includes address2 in full_address."""
    scraper = GeorgiaMountainFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert "Unit C" in loc["full_address"]


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_wpsl_response) -> None:
    """Test duplicate locations removed by ID."""
    scraper = GeorgiaMountainFoodBankGaScraper(test_mode=True)

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
    scraper = GeorgiaMountainFoodBankGaScraper(test_mode=True)
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
    assert submitted[0]["source"] == "georgia_mountain_food_bank_ga"
    assert submitted[0]["food_bank"] == "Georgia Mountain Food Bank"


@pytest.mark.asyncio
async def test_scrape_empty_response() -> None:
    """Test scrape handles empty API response."""
    scraper = GeorgiaMountainFoodBankGaScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return []

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0


@pytest.mark.asyncio
async def test_scrape_summary_format(mock_wpsl_response) -> None:
    """Test scrape returns valid JSON summary."""
    scraper = GeorgiaMountainFoodBankGaScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_wpsl_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "georgia_mountain_food_bank_ga"
    assert summary["food_bank"] == "Georgia Mountain Food Bank"
    assert "total_locations_found" in summary
    assert "unique_locations" in summary
    assert "total_jobs_created" in summary
