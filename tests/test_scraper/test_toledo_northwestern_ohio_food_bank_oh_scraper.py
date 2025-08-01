"""Tests for Toledo Northwestern Ohio Food Bank scraper."""

import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.toledo_northwestern_ohio_food_bank_oh_scraper import (
    ToledoNorthwesternOhioFoodBankOHScraper,
)


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    # TODO: Add actual HTML sample from the food bank website
    return """
    <html>
    <body>
        <div class="location">
            <h3>Sample Food Pantry</h3>
            <p class="address">123 Main St, City, OH 12345</p>
            <p class="phone">(555) 123-4567</p>
            <p class="hours">Mon-Fri 9am-5pm</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_json_response() -> Dict[str, Any]:
    """Sample StorePoint API response for testing."""
    return {
        "success": True,
        "results": {
            "locations": [
                {
                    "id": "1",
                    "name": "Sample Food Pantry",
                    "streetaddress": "123 Main St, Toledo, OH 43604",
                    "phone": "(555) 123-4567",
                    "description": "Mon-Fri 9am-5pm",
                    "loc_lat": 41.6528,
                    "loc_long": -83.5379,
                    "tags": "Food Pantry",
                    "website": "https://example.com",
                    "facebook": "https://facebook.com/example",
                    "email": "info@example.com",
                    "extra": "Additional notes",
                }
            ]
        },
    }


@pytest.fixture
def scraper() -> ToledoNorthwesternOhioFoodBankOHScraper:
    """Create scraper instance for testing."""
    return ToledoNorthwesternOhioFoodBankOHScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: ToledoNorthwesternOhioFoodBankOHScraper, mock_html_response: str
):
    """Test successful HTML download."""
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.text = mock_html_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = await scraper.download_html()

        assert result == mock_html_response
        mock_get.assert_called_once_with(
            scraper.url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=scraper.timeout,
        )


@pytest.mark.asyncio
async def test_download_html_failure(scraper: ToledoNorthwesternOhioFoodBankOHScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: ToledoNorthwesternOhioFoodBankOHScraper, mock_json_response: Dict[str, Any]
):
    """Test successful API data fetch."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = mock_json_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await scraper.fetch_api_data("locations")

        assert result == mock_json_response
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_api_data_failure(scraper: ToledoNorthwesternOhioFoodBankOHScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(
    scraper: ToledoNorthwesternOhioFoodBankOHScraper, mock_html_response: str
):
    """Test HTML parsing (not used in this scraper but required by base class)."""
    locations = scraper.parse_html(mock_html_response)

    # This scraper uses API, so HTML parsing returns empty
    assert len(locations) == 0


def test_parse_html_empty(scraper: ToledoNorthwesternOhioFoodBankOHScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: ToledoNorthwesternOhioFoodBankOHScraper, mock_json_response: Dict[str, Any]
):
    """Test API response processing."""
    locations = scraper.process_api_response(mock_json_response)

    assert len(locations) == 1
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St"
    assert locations[0]["city"] == "Toledo"
    assert locations[0]["state"] == "OH"
    assert locations[0]["zip"] == "43604"
    assert locations[0]["latitude"] == 41.6528
    assert locations[0]["longitude"] == -83.5379
    assert locations[0]["services"] == ["Food Pantry"]


def test_process_api_response_empty(scraper: ToledoNorthwesternOhioFoodBankOHScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: ToledoNorthwesternOhioFoodBankOHScraper, mock_json_response: Dict[str, Any]
):
    """Test complete API scraping flow."""
    # Mock API fetch
    scraper.fetch_api_data = AsyncMock(return_value=mock_json_response)

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
    assert summary["scraper_id"] == "toledo_northwestern_ohio_food_bank_oh"
    assert summary["food_bank"] == "Toledo Northwestern Ohio Food Bank"
    assert summary["total_locations_found"] == 1
    assert summary["unique_locations"] == 1
    assert summary["total_jobs_created"] == 1
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 1
    job = submitted_jobs[0]
    assert job["name"] == "Sample Food Pantry"
    assert job["latitude"] == 41.6528
    assert job["longitude"] == -83.5379
    assert job["source"] == "toledo_northwestern_ohio_food_bank_oh"
    assert job["food_bank"] == "Toledo Northwestern Ohio Food Bank"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: ToledoNorthwesternOhioFoodBankOHScraper,
):
    """Test scraping when geocoding fails."""
    # Create mock response without coordinates
    mock_response = {
        "success": True,
        "results": {
            "locations": [
                {
                    "id": "2",
                    "name": "Another Food Pantry",
                    "streetaddress": "456 Elm St, Toledo, OH 43604",
                    "phone": "(555) 987-6543",
                    "description": "Tue-Thu 10am-3pm",
                    "tags": "Food Pantry",
                    # No loc_lat/loc_long to test geocoding
                }
            ]
        },
    }

    # Mock API fetch
    scraper.fetch_api_data = AsyncMock(return_value=mock_response)

    # Mock geocoder to fail
    scraper.geocoder.geocode_address = Mock(side_effect=ValueError("Geocoding failed"))
    scraper.geocoder.get_default_coordinates = Mock(return_value=(41.6528, -83.5379))

    # Track submitted jobs
    submitted_jobs = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"

    scraper.submit_to_queue = Mock(side_effect=mock_submit)

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify fallback coordinates were used
    assert len(submitted_jobs) == 1
    job = submitted_jobs[0]
    assert job["latitude"] == 41.6528
    assert job["longitude"] == -83.5379

    # Verify geocoding stats
    assert summary["geocoding_stats"]["failed"] == 1
    assert summary["geocoding_stats"]["success"] == 0


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = ToledoNorthwesternOhioFoodBankOHScraper()
    assert scraper1.scraper_id == "toledo_northwestern_ohio_food_bank_oh"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = ToledoNorthwesternOhioFoodBankOHScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = ToledoNorthwesternOhioFoodBankOHScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode
