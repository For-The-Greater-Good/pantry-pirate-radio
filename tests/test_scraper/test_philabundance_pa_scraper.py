"""Tests for Philabundance scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.scraper.philabundance_pa_scraper import PhilabundancePaScraper


@pytest.fixture
def mock_wpsl_response() -> List[Dict[str, Any]]:
    """Sample WP Store Locator API response for testing."""
    return [
        {
            "id": "28056",
            "store": "Saint Mark's Food Cupboard",
            "address": "1625 Locust St",
            "city": "Philadelphia",
            "state": "PA",
            "zip": "19103",
            "phone": "215-735-1416",
            "lat": "39.948556",
            "lng": "-75.167084",
            "hours": "Thursday and Friday 9:30am-11am",
            "terms": "Food Cupboard",
            "url": "https://www.philabundance.org/stores/saint-marks-food-cupboard/",
            "description": "",
        },
        {
            "id": "27893",
            "store": "Broad Street Love (Broad Street Ministry)",
            "address": "315 S Broad St",
            "city": "Philadelphia",
            "state": "PA",
            "zip": "19107",
            "phone": "215-735-4847",
            "lat": "39.947223",
            "lng": "-75.164444",
            "hours": "",
            "terms": "Emergency Kitchen",
            "url": "",
            "description": "Provides meals and other services",
        },
    ]


@pytest.fixture
def mock_json_response() -> Dict[str, Any]:
    """Sample JSON response for generic API testing."""
    return {"success": True, "data": [{"id": "1", "name": "Test Location"}]}


@pytest.fixture
def scraper() -> PhilabundancePaScraper:
    """Create scraper instance for testing."""
    return PhilabundancePaScraper(test_mode=True)


@pytest.mark.asyncio
async def test_fetch_wpsl_locations_success(
    scraper: PhilabundancePaScraper, mock_wpsl_response: List[Dict[str, Any]]
):
    """Test successful WP Store Locator API fetch."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = mock_wpsl_response
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await scraper.fetch_wpsl_locations(40.0, -75.0, radius=50)

        assert result == mock_wpsl_response
        mock_client.get.assert_called_once_with(
            "https://www.philabundance.org/wp-admin/admin-ajax.php",
            params={
                "action": "store_search",
                "lat": "40.0",
                "lng": "-75.0",
                "max_results": "100",
                "search_radius": "50",
                "autoload": "1",
            },
        )


@pytest.mark.asyncio
async def test_fetch_wpsl_locations_failure(scraper: PhilabundancePaScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_wpsl_locations(40.0, -75.0)


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: PhilabundancePaScraper, mock_json_response: Dict[str, Any]
):
    """Test successful API data fetch."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = mock_json_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await scraper.fetch_api_data("test/endpoint", params={"key": "value"})

        assert result == mock_json_response
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_api_data_failure(scraper: PhilabundancePaScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_process_api_response(
    scraper: PhilabundancePaScraper, mock_wpsl_response: List[Dict[str, Any]]
):
    """Test WP Store Locator API response processing."""
    locations = scraper.process_api_response(mock_wpsl_response)

    assert len(locations) == 2

    # Check first location
    assert locations[0]["name"] == "Saint Mark's Food Cupboard"
    assert locations[0]["address"] == "1625 Locust St"
    assert locations[0]["city"] == "Philadelphia"
    assert locations[0]["state"] == "PA"
    assert locations[0]["zip"] == "19103"
    assert locations[0]["phone"] == "215-735-1416"
    assert locations[0]["latitude"] == 39.948556
    assert locations[0]["longitude"] == -75.167084
    assert locations[0]["hours"] == "Thursday and Friday 9:30am-11am"
    assert locations[0]["services"] == ["Food Cupboard"]

    # Check second location
    assert locations[1]["name"] == "Broad Street Love (Broad Street Ministry)"
    assert locations[1]["services"] == ["Emergency Kitchen"]
    assert locations[1]["notes"] == "Provides meals and other services"


def test_process_api_response_invalid_format(scraper: PhilabundancePaScraper):
    """Test processing API response with invalid format."""
    # WP Store Locator should return a list, not a dict
    locations = scraper.process_api_response({"error": "Invalid request"})
    assert locations == []


def test_process_api_response_empty(scraper: PhilabundancePaScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: PhilabundancePaScraper, mock_wpsl_response: List[Dict[str, Any]]
):
    """Test complete API scraping flow."""
    # Mock grid points
    mock_grid_points = [
        Mock(latitude=40.0, longitude=-75.0),
        Mock(latitude=40.5, longitude=-75.5),
    ]
    scraper.utils.get_state_grid_points = Mock(
        return_value=mock_grid_points[:1]
    )  # Test mode limits to 1

    # Mock API fetch
    scraper.fetch_wpsl_locations = AsyncMock(return_value=mock_wpsl_response)

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
    assert summary["scraper_id"] == "philabundance_pa"
    assert summary["food_bank"] == "Philabundance PA"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["jobs_created"] == 2
    # test_mode field was removed from summary in updated scrapers

    # Verify submitted jobs
    assert len(submitted_jobs) == 2
    job1 = submitted_jobs[0]
    assert job1["name"] == "Saint Mark's Food Cupboard"
    # Note: This scraper DOES extract coordinates when available from API
    assert job1["latitude"] == 39.948556
    assert job1["longitude"] == -75.167084
    assert "source" not in job1  # source not included in job data
    assert "food_bank" not in job1  # food_bank not included in job data


@pytest.mark.asyncio
async def test_scrape_with_api_error(scraper: PhilabundancePaScraper):
    """Test scraping when API call fails for a grid point."""
    # Mock grid points
    mock_grid_points = [
        Mock(latitude=40.0, longitude=-75.0),
        Mock(latitude=40.5, longitude=-75.5),
    ]
    scraper.utils.get_state_grid_points = Mock(return_value=mock_grid_points[:2])

    # Mock API fetch to fail first time, succeed second time
    scraper.fetch_wpsl_locations = AsyncMock(
        side_effect=[
            httpx.HTTPError("API error"),
            [
                {
                    "id": "1",
                    "store": "Test Location",
                    "address": "123 Test St",
                    "city": "Philadelphia",
                    "state": "PA",
                    "zip": "19103",
                    "lat": "40.0",
                    "lng": "-75.0",
                }
            ],
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

    # Verify only second grid point succeeded
    assert len(submitted_jobs) == 1
    assert submitted_jobs[0]["name"] == "Test Location"
    assert summary["total_locations_found"] == 1


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = PhilabundancePaScraper()
    assert scraper1.scraper_id == "philabundance_pa"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = PhilabundancePaScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = PhilabundancePaScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.1  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_with_no_locations(scraper: PhilabundancePaScraper):
    """Test scraping when no locations are found."""
    # Mock grid points
    mock_grid_points = [Mock(latitude=40.0, longitude=-75.0)]
    scraper.utils.get_state_grid_points = Mock(return_value=mock_grid_points)

    # Mock API fetch to return empty list
    scraper.fetch_wpsl_locations = AsyncMock(return_value=[])

    # Track submitted jobs
    submitted_jobs = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"

    scraper.submit_to_queue = Mock(side_effect=mock_submit)

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify no jobs were submitted
    assert len(submitted_jobs) == 0
    assert summary["total_locations_found"] == 0
    assert summary["jobs_created"] == 0
