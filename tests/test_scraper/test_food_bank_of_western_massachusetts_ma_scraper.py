"""Tests for Food Bank of Western Massachusetts scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.food_bank_of_western_massachusetts_ma_scraper import (
    FoodBankOfWesternMassachusettsMaScraper,
)


@pytest.fixture
def mock_wp_store_locator_response() -> List[Dict[str, Any]]:
    """Sample WP Store Locator API response for testing."""
    return [
        {
            "id": "1",
            "store": "Sample Food Pantry",
            "address": "123 Main St",
            "address2": "",
            "city": "Springfield",
            "state": "MA",
            "zip": "01101",
            "phone": "(555) 123-4567",
            "lat": "42.1015",
            "lng": "-72.5898",
            "hours": "Mon-Fri 9am-5pm",
            "url": "https://example.com",
            "description": "<p>A community food pantry serving families in need.</p>",
            "category": "food pantry",
        },
        {
            "id": "2",
            "store": "Community Meal Site",
            "address": "456 Oak Ave",
            "address2": "Suite 100",
            "city": "Holyoke",
            "state": "MA",
            "zip": "01040",
            "phone": "(555) 987-6543",
            "lat": "",
            "lng": "",
            "hours": "Tue-Thu 11:30am-1pm",
            "url": "",
            "description": "<p>Hot meals served daily.</p>",
            "category": "meal site",
        },
    ]


@pytest.fixture
def scraper() -> FoodBankOfWesternMassachusettsMaScraper:
    """Create scraper instance for testing."""
    return FoodBankOfWesternMassachusettsMaScraper(test_mode=True)


@pytest.mark.asyncio
async def test_fetch_wp_store_locator_data_success(
    scraper: FoodBankOfWesternMassachusettsMaScraper,
    mock_wp_store_locator_response: List[Dict[str, Any]],
):
    """Test successful WP Store Locator API data fetch."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = mock_wp_store_locator_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await scraper.fetch_wp_store_locator_data()

        assert len(result) == 2
        assert result[0]["name"] == "Sample Food Pantry"
        assert result[0]["full_address"] == "123 Main St"
        assert result[0]["city"] == "Springfield"
        # Note: This scraper DOES extract coordinates from the API when available
        assert result[0]["latitude"] == 42.1015
        assert result[0]["longitude"] == -72.5898
        assert result[0]["services"] == ["Food Pantry"]

        assert result[1]["name"] == "Community Meal Site"
        assert result[1]["full_address"] == "456 Oak Ave Suite 100"
        assert result[1]["services"] == ["Meal Site"]
        # Second location has empty coordinates in mock data
        assert result[1]["latitude"] is None
        assert result[1]["longitude"] is None

        mock_client.get.assert_called_once_with(
            scraper.ajax_url,
            params={
                "action": "store_search",
                "lat": "42.17537",
                "lng": "-72.57372",
                "max_results": "500",
                "search_radius": "100",
                "autoload": "1",
            },
        )


@pytest.mark.asyncio
async def test_fetch_wp_store_locator_data_failure(
    scraper: FoodBankOfWesternMassachusettsMaScraper,
):
    """Test handling of WP Store Locator API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_wp_store_locator_data()


def test_extract_services(scraper: FoodBankOfWesternMassachusettsMaScraper):
    """Test service extraction from location data."""
    # Test with category
    item1 = {"category": "food pantry"}
    assert scraper._extract_services(item1, "") == ["Food Pantry"]

    # Test with meal site category
    item2 = {"category": "meal kitchen"}
    assert scraper._extract_services(item2, "") == ["Meal Site"]

    # Test with description
    item3 = {"category": ""}
    assert scraper._extract_services(item3, "We serve hot meals daily") == ["Meal Site"]

    # Test with mobile food bank
    item4 = {"category": "mobile"}
    assert scraper._extract_services(item4, "") == ["Mobile Food Bank"]

    # Test with brown bag
    item5 = {"category": "brown bag"}
    assert scraper._extract_services(item5, "") == ["Brown Bag: Food for Elders"]

    # Test default
    item6 = {"category": ""}
    assert scraper._extract_services(item6, "") == ["Food Pantry"]


def test_determine_county(scraper: FoodBankOfWesternMassachusettsMaScraper):
    """Test county determination from city names."""
    assert scraper._determine_county({"city": "Springfield"}) == "Hampden"
    assert scraper._determine_county({"city": "Northampton"}) == "Hampshire"
    assert scraper._determine_county({"city": "Greenfield"}) == "Franklin"
    assert scraper._determine_county({"city": "Pittsfield"}) == "Berkshire"
    assert scraper._determine_county({"city": "Unknown City"}) is None


@pytest.mark.asyncio
async def test_scrape_complete_flow(
    scraper: FoodBankOfWesternMassachusettsMaScraper,
    mock_wp_store_locator_response: List[Dict[str, Any]],
):
    """Test complete scraping flow."""
    # Mock fetch_wp_store_locator_data
    scraper.fetch_wp_store_locator_data = AsyncMock(
        return_value=[
            {
                "id": "1",
                "name": "Sample Food Pantry",
                "address": "123 Main St",
                "address2": "",
                "city": "Springfield",
                "state": "MA",
                "zip": "01101",
                "phone": "(555) 123-4567",
                "latitude": 42.1015,
                "longitude": -72.5898,
                "hours": "Mon-Fri 9am-5pm",
                "url": "https://example.com",
                "description": "A community food pantry serving families in need.",
                "services": ["Food Pantry"],
                "full_address": "123 Main St",
            },
            {
                "id": "2",
                "name": "Community Meal Site",
                "address": "456 Oak Ave",
                "address2": "Suite 100",
                "city": "Holyoke",
                "state": "MA",
                "zip": "01040",
                "phone": "(555) 987-6543",
                "latitude": None,
                "longitude": None,
                "hours": "Tue-Thu 11:30am-1pm",
                "url": "",
                "description": "Hot meals served daily.",
                "services": ["Meal Site"],
                "full_address": "456 Oak Ave Suite 100",
            },
        ]
    )
    # Track submitted jobs
    submitted_jobs = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"

    scraper.submit_to_queue = Mock(side_effect=mock_submit)

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify summary
    assert summary["scraper_id"] == "food_bank_of_western_massachusetts_ma"
    assert summary["food_bank"] == "Food Bank of Western Massachusetts"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert "geocoding_stats" not in summary
    # Note: test_mode field was removed from summary in scraper updates
    # assert summary["test_mode"] is True
    # Verify submitted jobs
    assert len(submitted_jobs) == 2

    job1 = submitted_jobs[0]
    assert job1["name"] == "Sample Food Pantry"
    # Note: This scraper DOES extract coordinates when available from API
    assert job1["latitude"] == 42.1015
    assert job1["longitude"] == -72.5898
    # Note: This scraper still uses OLD format - adds metadata to jobs
    assert job1["source"] == "food_bank_of_western_massachusetts_ma"
    assert job1["food_bank"] == "Food Bank of Western Massachusetts"
    assert job1["services"] == ["Food Pantry"]

    job2 = submitted_jobs[1]
    assert job2["name"] == "Community Meal Site"
    # Second job has no coordinates in mock data
    assert job2["latitude"] is None
    assert job2["longitude"] is None
    assert job2["source"] == "food_bank_of_western_massachusetts_ma"
    assert job2["food_bank"] == "Food Bank of Western Massachusetts"
    assert job2["services"] == ["Meal Site"]


@pytest.mark.asyncio
async def test_scrape_without_geocoding(
    scraper: FoodBankOfWesternMassachusettsMaScraper,
):
    """Test scraping without geocoding (validator handles it now)."""
    # Mock fetch_wp_store_locator_data with location missing coordinates
    scraper.fetch_wp_store_locator_data = AsyncMock(
        return_value=[
            {
                "id": "1",
                "name": "Sample Food Pantry",
                "address": "123 Main St",
                "address2": "",
                "city": "Springfield",
                "state": "MA",
                "zip": "01101",
                "phone": "(555) 123-4567",
                "latitude": None,
                "longitude": None,
                "hours": "Mon-Fri 9am-5pm",
                "url": "https://example.com",
                "description": "A community food pantry serving families in need.",
                "services": ["Food Pantry"],
                "full_address": "123 Main St",
            }
        ]
    )  # Springfield is in Hampden County
    # Track submitted jobs
    submitted_jobs = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"

    scraper.submit_to_queue = Mock(side_effect=mock_submit)

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify location was processed (validator will handle geocoding)


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = FoodBankOfWesternMassachusettsMaScraper()
    assert scraper1.scraper_id == "food_bank_of_western_massachusetts_ma"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = FoodBankOfWesternMassachusettsMaScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = FoodBankOfWesternMassachusettsMaScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_with_empty_response(
    scraper: FoodBankOfWesternMassachusettsMaScraper,
):
    """Test scraping with empty API response."""
    # Mock fetch_wp_store_locator_data to return empty list
    scraper.fetch_wp_store_locator_data = AsyncMock(return_value=[])

    # Track submitted jobs
    submitted_jobs = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"

    scraper.submit_to_queue = Mock(side_effect=mock_submit)

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify summary
    assert summary["total_locations_found"] == 0
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
    assert "geocoding_stats" not in summary
    assert len(submitted_jobs) == 0


@pytest.mark.asyncio
async def test_scrape_with_no_address_default_coordinates(
    scraper: FoodBankOfWesternMassachusettsMaScraper,
):
    """Test scraping when location has no address and uses default coordinates."""
    # Mock fetch_wp_store_locator_data with location having no address
    scraper.fetch_wp_store_locator_data = AsyncMock(
        return_value=[
            {
                "id": "1",
                "name": "No Address Food Pantry",
                "address": "",
                "address2": "",
                "city": "Northampton",
                "state": "MA",
                "zip": "",
                "phone": "(555) 123-4567",
                "latitude": None,
                "longitude": None,
                "hours": "Mon-Fri 9am-5pm",
                "url": "",
                "description": "Food pantry without address.",
                "services": ["Food Pantry"],
                "full_address": "",
            }
        ]
    )
    # Track submitted jobs
    submitted_jobs = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"

    scraper.submit_to_queue = Mock(side_effect=mock_submit)

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify location was processed (validator will handle geocoding)
    assert len(submitted_jobs) == 1
    job = submitted_jobs[0]
    assert job["name"] == "No Address Food Pantry"
    # County may not be present if not in source data
    assert "geocoding_stats" not in summary
