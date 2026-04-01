"""Tests for Feeding the Valley Food Bank GA scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.feeding_the_valley_food_bank_ga_scraper import (
    FeedingTheValleyFoodBankGaScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for West Georgia."""
    return [
        {
            "id": "501",
            "store": "Columbus Community Pantry",
            "address": "100 Broadway",
            "address2": "",
            "city": "Columbus",
            "state": "GA",
            "zip": "31901",
            "phone": "706-555-1234",
            "lat": "32.4610",
            "lng": "-84.9877",
            "hours": "<p>Mon-Fri 8am-4pm</p>",
            "url": "",
            "description": "<p>Serving Muscogee County</p>",
            "distance": "0.5",
        },
        {
            "id": "502",
            "store": "LaGrange Food Distribution",
            "address": "200 Main St",
            "address2": "",
            "city": "LaGrange",
            "state": "",
            "zip": "30240",
            "phone": "",
            "lat": "33.0362",
            "lng": "-85.0322",
            "hours": "",
            "url": "",
            "description": "<p>1st Saturday 9am-11am</p>",
            "distance": "10.0",
        },
    ]


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FeedingTheValleyFoodBankGaScraper()
    assert scraper.scraper_id == "feeding_the_valley_food_bank_ga"
    assert "feedingthevalley.org" in scraper.ajax_url


def test_generate_grid_points() -> None:
    """Test grid covers West Georgia service area."""
    scraper = FeedingTheValleyFoodBankGaScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 31.4 <= lat <= 33.2
        assert -85.5 <= lng <= -83.5


def test_parse_location(mock_wpsl_response) -> None:
    """Test parsing raw WPSL response items."""
    scraper = FeedingTheValleyFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[0])

    assert loc["name"] == "Columbus Community Pantry"
    assert loc["state"] == "GA"
    assert loc["latitude"] == 32.4610


def test_parse_location_empty_state(mock_wpsl_response) -> None:
    """Test parsing defaults empty state to GA."""
    scraper = FeedingTheValleyFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "GA"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_wpsl_response) -> None:
    """Test duplicate locations removed by ID."""
    scraper = FeedingTheValleyFoodBankGaScraper(test_mode=True)

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
    scraper = FeedingTheValleyFoodBankGaScraper(test_mode=True)
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
    assert submitted[0]["source"] == "feeding_the_valley_food_bank_ga"
    assert submitted[0]["food_bank"] == "Feeding the Valley Food Bank"
