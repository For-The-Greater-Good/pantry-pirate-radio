"""Tests for Second Harvest of Silicon Valley scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.second_harvest_of_silicon_valley_ca_scraper import (
    SecondHarvestOfSiliconValleyCaScraper,
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
            <p class="address">123 Main St, City, CA 12345</p>
            <p class="phone">(555) 123-4567</p>
            <p class="hours">Mon-Fri 9am-5pm</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_json_response() -> Dict[str, Any]:
    """Sample JSON response for testing."""
    # Actual API response format
    return {
        "locations": {
            "0011I00001IrFHvQAN": {
                "siteId": "0011I00001IrFHvQAN",
                "name": "Sample Food Pantry",
                "street": "123 Main St",
                "city": "San Jose",
                "county": "Santa Clara",
                "state": "CA",
                "zip": "95112",
                "lat": 37.3541,
                "lng": -121.9552,
                "phone": "(555) 123-4567",
            }
        },
        "campaigns": {
            "7018W0000003tfKQAQ": {
                "siteId": "0011I00001IrFHvQAN",
                "type": "Free Groceries",
                "isActive": True,
                "driveThru": False,
                "distributionAccess": "Walk Up Only",
                "documentationReqs": "None",
                "programEligibility": "All",
                "howOftenCanClientsGo": "Weekly",
                "specialInstructions": "Test instructions",
            }
        },
        "schedules": {
            "0011I00001IrFHvQAN_7018W0000003tfKQAQ": [
                {"day": "Monday", "start_time": "9:00 AM", "end_time": "5:00 PM"},
                {"day": "Friday", "start_time": "9:00 AM", "end_time": "5:00 PM"},
            ]
        },
    }


@pytest.fixture
def scraper() -> SecondHarvestOfSiliconValleyCaScraper:
    """Create scraper instance for testing."""
    return SecondHarvestOfSiliconValleyCaScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: SecondHarvestOfSiliconValleyCaScraper, mock_html_response: str
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
async def test_download_html_failure(scraper: SecondHarvestOfSiliconValleyCaScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: SecondHarvestOfSiliconValleyCaScraper, mock_json_response: Dict[str, Any]
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
async def test_fetch_api_data_failure(scraper: SecondHarvestOfSiliconValleyCaScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(
    scraper: SecondHarvestOfSiliconValleyCaScraper, mock_html_response: str
):
    """Test HTML parsing."""
    # This scraper uses API, not HTML parsing
    locations = scraper.parse_html(mock_html_response)
    assert len(locations) == 0  # HTML parsing not implemented for API-based scraper


def test_parse_html_empty(scraper: SecondHarvestOfSiliconValleyCaScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: SecondHarvestOfSiliconValleyCaScraper,
    mock_json_response: Dict[str, Any],
):
    """Test API response processing."""
    locations = scraper.process_api_response(mock_json_response)

    assert len(locations) == 1
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St"
    assert locations[0]["city"] == "San Jose"
    assert locations[0]["state"] == "CA"
    assert locations[0]["zip"] == "95112"
    assert locations[0]["latitude"] == 37.3541
    assert locations[0]["longitude"] == -121.9552
    assert (
        locations[0]["hours"] == "Monday: 9:00 AM - 5:00 PM; Friday: 9:00 AM - 5:00 PM"
    )
    assert "Free Groceries" in locations[0]["services"]
    assert "No documents required" in locations[0]["services"]
    assert "Walk up" in locations[0]["services"]


def test_process_api_response_empty(scraper: SecondHarvestOfSiliconValleyCaScraper):
    """Test processing empty API response."""
    empty_response = {"locations": {}, "campaigns": {}, "schedules": {}}
    locations = scraper.process_api_response(empty_response)
    assert locations == []


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = SecondHarvestOfSiliconValleyCaScraper()
    assert scraper1.scraper_id == "second_harvest_of_silicon_valley_ca"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = SecondHarvestOfSiliconValleyCaScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = SecondHarvestOfSiliconValleyCaScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: SecondHarvestOfSiliconValleyCaScraper,
    mock_json_response: Dict[str, Any],
):
    """Test complete API scraping flow."""
    # Mock requests.get to return JSON
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = mock_json_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

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
        assert summary["total_jobs_created"] == 1
        assert summary["unique_locations"] == 1
        assert len(submitted_jobs) == 1

        # Verify job data
        job = submitted_jobs[0]
        assert job["name"] == "Sample Food Pantry"
        # Note: This scraper DOES extract coordinates from API
        assert job["latitude"] == 37.3541
        assert job["longitude"] == -121.9552
        assert "source" not in job  # source not included in job data
