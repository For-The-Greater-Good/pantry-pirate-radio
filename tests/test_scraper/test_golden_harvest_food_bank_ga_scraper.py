"""Tests for Golden Harvest Food Bank GA scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.golden_harvest_food_bank_ga_scraper import (
    GoldenHarvestFoodBankGaScraper,
)


@pytest.fixture
def mock_wpsl_response():
    """Mock WP Store Locator API response for Augusta area."""
    return [
        {
            "id": "701",
            "store": "Augusta Community Pantry",
            "address": "100 Broad St",
            "address2": "",
            "city": "Augusta",
            "state": "GA",
            "zip": "30901",
            "phone": "706-555-1234",
            "lat": "33.4735",
            "lng": "-81.9748",
            "hours": "<p>Mon-Fri 9am-4pm</p>",
            "url": "",
            "description": "<p>Serving Richmond County</p>",
            "distance": "0.5",
        },
        {
            "id": "702",
            "store": "Aiken Food Pantry",
            "address": "200 Laurens St",
            "address2": "",
            "city": "Aiken",
            "state": "SC",
            "zip": "29801",
            "phone": "",
            "lat": "33.5604",
            "lng": "-81.7196",
            "hours": "",
            "url": "",
            "description": "<p>Saturday 9am-11am</p>",
            "distance": "15.0",
        },
    ]


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = GoldenHarvestFoodBankGaScraper()
    assert scraper.scraper_id == "golden_harvest_food_bank_ga"
    assert "goldenharvest.org" in scraper.ajax_url


def test_generate_grid_points() -> None:
    """Test grid covers GA/SC service area around Augusta."""
    scraper = GoldenHarvestFoodBankGaScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 10
    for lat, lng in points:
        assert 32.4 <= lat <= 34.2
        assert -83.5 <= lng <= -81.5


def test_parse_location(mock_wpsl_response) -> None:
    """Test parsing raw WPSL response items."""
    scraper = GoldenHarvestFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[0])

    assert loc["name"] == "Augusta Community Pantry"
    assert loc["state"] == "GA"
    assert loc["latitude"] == 33.4735


def test_parse_location_sc_state(mock_wpsl_response) -> None:
    """Test parsing preserves SC state for cross-border locations."""
    scraper = GoldenHarvestFoodBankGaScraper()
    loc = scraper._parse_location(mock_wpsl_response[1])
    assert loc["state"] == "SC"
    assert loc["city"] == "Aiken"


def test_parse_location_none_coords() -> None:
    """Test parsing handles None coordinates."""
    scraper = GoldenHarvestFoodBankGaScraper()
    item = {
        "id": "999",
        "store": "No Coords Pantry",
        "address": "123 Main St",
        "address2": "",
        "city": "Augusta",
        "state": "GA",
        "zip": "30901",
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
    scraper = GoldenHarvestFoodBankGaScraper(test_mode=True)

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
    scraper = GoldenHarvestFoodBankGaScraper(test_mode=True)
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
    assert submitted[0]["source"] == "golden_harvest_food_bank_ga"
    assert submitted[0]["food_bank"] == "Golden Harvest Food Bank"
