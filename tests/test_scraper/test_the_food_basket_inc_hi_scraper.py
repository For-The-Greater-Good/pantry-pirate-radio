"""Tests for The Food Basket, Inc. scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.the_food_basket_inc_hi_scraper import The_Food_Basket_Inc_HiScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <div class="sqs-block-content">
            <h2>Monday</h2>
            <ul>
                <li>Food Pantry</li>
                <li>Sample Food Pantry</li>
                <li><a href="https://tinyurl.com/test">123 Main St, Hilo, HI 96720</a></li>
                <li>Days/Hours: • 3rd Monday of the Month, 10am (except holidays)</li>
                <li>(808) 123-4567</li>
            </ul>
        </div>
        <div class="sqs-block-content">
            <h2>Tuesday</h2>
            <ul>
                <li>Soup Kitchen</li>
                <li>Another Pantry</li>
                <li><a href="https://tinyurl.com/test2">456 Oak Ave, Kona, Hawaii 96740</a></li>
                <li>Days/Hours: • Tuesday Lunch, 12pm (except holidays)</li>
            </ul>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_json_response() -> Dict[str, Any]:
    """Sample JSON response for testing."""
    # TODO: Add actual JSON sample if the food bank uses an API
    return {
        "locations": [
            {
                "name": "Sample Food Pantry",
                "address": "123 Main St, City, HI 12345",
                "phone": "(555) 123-4567",
                "hours": "Mon-Fri 9am-5pm",
            }
        ]
    }


@pytest.fixture
def scraper() -> The_Food_Basket_Inc_HiScraper:
    """Create scraper instance for testing."""
    return The_Food_Basket_Inc_HiScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: The_Food_Basket_Inc_HiScraper, mock_html_response: str
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
async def test_download_html_failure(scraper: The_Food_Basket_Inc_HiScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: The_Food_Basket_Inc_HiScraper, mock_json_response: Dict[str, Any]
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
async def test_fetch_api_data_failure(scraper: The_Food_Basket_Inc_HiScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: The_Food_Basket_Inc_HiScraper, mock_html_response: str):
    """Test HTML parsing."""
    locations = scraper.parse_html(mock_html_response)

    assert len(locations) == 2

    # First location
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St, Hilo, HI 96720"
    assert locations[0]["city"] == "Hilo"
    assert locations[0]["zip"] == "96720"
    assert locations[0]["services"] == ["Food Pantry"]
    assert locations[0]["phone"] == "(808) 123-4567"
    assert "3rd Monday" in locations[0]["hours"]

    # Second location
    assert locations[1]["name"] == "Another Pantry"
    assert locations[1]["address"] == "456 Oak Ave, Kona, Hawaii 96740"
    assert locations[1]["city"] == "Kona"
    assert locations[1]["zip"] == "96740"
    assert locations[1]["services"] == ["Soup Kitchen"]
    assert "Tuesday Lunch" in locations[1]["hours"]


def test_parse_html_empty(scraper: The_Food_Basket_Inc_HiScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: The_Food_Basket_Inc_HiScraper, mock_json_response: Dict[str, Any]
):
    """Test API response processing."""
    # This scraper uses HTML parsing, not API processing
    # Return empty list as the method is not implemented
    locations = scraper.process_api_response(mock_json_response)
    assert locations == []


def test_process_api_response_empty(scraper: The_Food_Basket_Inc_HiScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: The_Food_Basket_Inc_HiScraper, mock_html_response: str
):
    """Test complete HTML scraping flow."""
    # Mock download_html
    scraper.download_html = AsyncMock(return_value=mock_html_response)
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
    assert summary["scraper_id"] == "the_food_basket_inc_hi"
    assert summary["food_bank"] == "The Food Basket Inc HI"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["jobs_created"] == 2
    assert "geocoding_stats" not in summary
    # test_mode field was removed from summary in updated scrapers

    # Verify submitted jobs
    assert len(submitted_jobs) == 2
    job = submitted_jobs[0]
    assert job["name"] == "Sample Food Pantry"
    # Note: latitude/longitude removed - validator service handles geocoding
    assert "latitude" not in job or job["latitude"] is None
    assert "longitude" not in job or job["longitude"] is None
    assert "source" not in job  # source not included in job data
    assert "food_bank" not in job  # food_bank not included in job data


@pytest.mark.asyncio
async def test_scrape_without_geocoding(
    scraper: The_Food_Basket_Inc_HiScraper, mock_html_response: str
):
    """Test scraping without geocoding (validator handles it now)."""
    # Mock download_html
    scraper.download_html = AsyncMock(return_value=mock_html_response)
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
    # Test with default ID
    scraper1 = The_Food_Basket_Inc_HiScraper()
    assert scraper1.scraper_id == "the_food_basket_inc_hi"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = The_Food_Basket_Inc_HiScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = The_Food_Basket_Inc_HiScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: The_Food_Basket_Inc_HiScraper, mock_html_response: str
):
    """Test scraping with empty results."""
    # Mock download_html to return empty page
    scraper.download_html = AsyncMock(return_value="<html><body></body></html>")

    # Track submitted jobs
    submitted_jobs = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"

    scraper.submit_to_queue = Mock(side_effect=mock_submit)

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify no jobs were created
    assert summary["jobs_created"] == 0
    assert "geocoding_stats" not in summary
    assert len(submitted_jobs) == 0
