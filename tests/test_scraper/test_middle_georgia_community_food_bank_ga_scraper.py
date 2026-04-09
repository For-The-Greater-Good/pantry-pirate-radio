"""Tests for Middle Georgia Community Food Bank scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.middle_georgia_community_food_bank_ga_scraper import (
    MiddleGeorgiaCommunityFoodBankGaScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for Middle Georgia."""
    return [
        {
            "id": "601",
            "store": "Macon Community Pantry",
            "address": "100 Cherry St",
            "address2": "",
            "city": "Macon",
            "state": "GA",
            "zip": "31201",
            "phone": "478-555-1234",
            "lat": "32.8407",
            "lng": "-83.6324",
            "hours": "<p>Mon-Fri 9am-3pm</p>",
            "url": "",
            "description": "<p>Serving Bibb County</p>",
            "distance": "0.5",
        },
        {
            "id": "602",
            "store": "Warner Robins Help Center",
            "address": "200 Watson Blvd",
            "address2": "",
            "city": "Warner Robins",
            "state": "",
            "zip": "31093",
            "phone": "",
            "lat": "32.6130",
            "lng": "-83.5988",
            "hours": "",
            "url": "",
            "description": "<p>Tue & Thu 10am-12pm</p>",
            "distance": "10.0",
        },
    ]


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = MiddleGeorgiaCommunityFoodBankGaScraper()
    assert scraper.scraper_id == "middle_georgia_community_food_bank_ga"
    assert "mgcfb.org" in scraper.ajax_url


def test_generate_grid_points() -> None:
    """Test grid covers Middle Georgia service area."""
    scraper = MiddleGeorgiaCommunityFoodBankGaScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 31.8 <= lat <= 33.4
        assert -84.2 <= lng <= -82.2


def test_parse_location(mock_wpsl_response) -> None:
    """Test parsing raw WPSL response items."""
    scraper = MiddleGeorgiaCommunityFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[0])

    assert loc["name"] == "Macon Community Pantry"
    assert loc["state"] == "GA"
    assert loc["latitude"] == 32.8407


def test_parse_location_empty_state(mock_wpsl_response) -> None:
    """Test parsing defaults empty state to GA."""
    scraper = MiddleGeorgiaCommunityFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "GA"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_wpsl_response) -> None:
    """Test duplicate locations removed by ID."""
    scraper = MiddleGeorgiaCommunityFoodBankGaScraper(test_mode=True)

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
    scraper = MiddleGeorgiaCommunityFoodBankGaScraper(test_mode=True)
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
    assert submitted[0]["source"] == "middle_georgia_community_food_bank_ga"
    assert submitted[0]["food_bank"] == "Middle Georgia Community Food Bank"
