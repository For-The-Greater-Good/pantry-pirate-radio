"""Tests for Food Bank of South Jersey scraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_south_jersey_nj_scraper import (
    FoodBankOfSouthJerseyNjScraper,
)


@pytest.fixture
def mock_asl_response():
    """Mock ASL API response."""
    return [
        {
            "id": "1",
            "title": "Camden Food Pantry",
            "street": "100 Broadway",
            "city": "Camden",
            "state": "NJ",
            "postal_code": "08101",
            "lat": "39.9259",
            "lng": "-75.1196",
            "phone": "856-555-1234",
            "description_2": "Mon-Fri 9am-3pm",
            "description": "Serving Camden County",
            "categories": "Food Pantry",
        },
        {
            "id": "2",
            "title": "Vineland Distribution Center",
            "street": "200 Landis Ave",
            "city": "Vineland",
            "state": "",
            "postal_code": "08360",
            "lat": "39.4864",
            "lng": "-75.0260",
            "phone": "",
            "description_2": "",
            "description": "",
            "categories": "",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfSouthJerseyNjScraper()
    assert scraper.scraper_id == "food_bank_of_south_jersey_nj"
    assert "foodbanksj.org" in scraper.asl_url


@pytest.mark.asyncio
async def test_parse_asl_location(mock_asl_response):
    """Test parsing ASL store data."""
    scraper = FoodBankOfSouthJerseyNjScraper()
    loc = scraper._parse_asl_location(mock_asl_response[0])
    assert loc["name"] == "Camden Food Pantry"
    assert loc["city"] == "Camden"
    assert loc["state"] == "NJ"
    assert loc["latitude"] == 39.9259


@pytest.mark.asyncio
async def test_parse_asl_location_empty_state(mock_asl_response):
    """Test parsing handles empty state with NJ default."""
    scraper = FoodBankOfSouthJerseyNjScraper()
    loc = scraper._parse_asl_location(mock_asl_response[1])
    assert loc["state"] == "NJ"


@pytest.mark.asyncio
async def test_scrape_with_asl_data(mock_asl_response):
    """Test scrape uses ASL data when available."""
    scraper = FoodBankOfSouthJerseyNjScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_asl_fetch(client):
        return mock_asl_response

    with patch.object(scraper, "_fetch_asl_stores", side_effect=mock_asl_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["asl_count"] == 2
    assert submitted[0]["source"] == "food_bank_of_south_jersey_nj"
    assert submitted[0]["food_bank"] == "Food Bank of South Jersey"


@pytest.mark.asyncio
async def test_scrape_empty_asl_falls_back():
    """Test scrape falls back to HTML when ASL is empty."""
    scraper = FoodBankOfSouthJerseyNjScraper(test_mode=True)

    async def mock_asl_fetch(client):
        return []

    async def mock_html_fetch(client):
        return [{"name": "HTML Location", "state": "NJ"}]

    with patch.object(scraper, "_fetch_asl_stores", side_effect=mock_asl_fetch):
        with patch.object(
            scraper, "_fetch_html_locations", side_effect=mock_html_fetch
        ):
            with patch.object(scraper, "submit_to_queue", return_value="j"):
                result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["asl_count"] == 0
    assert summary["unique_locations"] == 1


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles fully empty response."""
    scraper = FoodBankOfSouthJerseyNjScraper(test_mode=True)

    async def mock_asl_fetch(client):
        return []

    async def mock_html_fetch(client):
        return []

    with patch.object(scraper, "_fetch_asl_stores", side_effect=mock_asl_fetch):
        with patch.object(
            scraper, "_fetch_html_locations", side_effect=mock_html_fetch
        ):
            with patch.object(scraper, "submit_to_queue", return_value="j"):
                result = await scraper.scrape()

    assert json.loads(result)["total_jobs_created"] == 0
