"""Tests for The Food Basket, Inc. scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.the_food_basket_inc_hi_scraper import TheFoodBasketIncHiScraper


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
def scraper() -> TheFoodBasketIncHiScraper:
    """Create scraper instance for testing."""
    return TheFoodBasketIncHiScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: TheFoodBasketIncHiScraper, mock_html_response: str
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
async def test_download_html_failure(scraper: TheFoodBasketIncHiScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: TheFoodBasketIncHiScraper, mock_json_response: Dict[str, Any]
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
async def test_fetch_api_data_failure(scraper: TheFoodBasketIncHiScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: TheFoodBasketIncHiScraper, mock_html_response: str):
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


def test_parse_html_empty(scraper: TheFoodBasketIncHiScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: TheFoodBasketIncHiScraper, mock_json_response: Dict[str, Any]
):
    """Test API response processing."""
    # This scraper uses HTML parsing, not API processing
    # Return empty list as the method is not implemented
    locations = scraper.process_api_response(mock_json_response)
    assert locations == []


def test_process_api_response_empty(scraper: TheFoodBasketIncHiScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: TheFoodBasketIncHiScraper, mock_html_response: str
):
    """Test complete HTML scraping flow."""
    # Mock download_html
    scraper.download_html = AsyncMock(return_value=mock_html_response)

    # Mock geocoder
    scraper.geocoder.geocode_address = Mock(return_value=(40.0, -75.0))

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
    assert summary["food_bank"] == "The Food Basket, Inc."
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 2
    job = submitted_jobs[0]
    assert job["name"] == "Sample Food Pantry"
    assert job["latitude"] == 40.0
    assert job["longitude"] == -75.0
    assert job["source"] == "the_food_basket_inc_hi"
    assert job["food_bank"] == "The Food Basket, Inc."


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: TheFoodBasketIncHiScraper, mock_html_response: str
):
    """Test scraping when geocoding fails."""
    # Mock download_html
    scraper.download_html = AsyncMock(return_value=mock_html_response)

    # Mock geocoder to fail
    scraper.geocoder.geocode_address = Mock(side_effect=ValueError("Geocoding failed"))
    scraper.geocoder.get_default_coordinates = Mock(return_value=(39.0, -76.0))

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
    assert len(submitted_jobs) == 2
    job = submitted_jobs[0]
    assert job["latitude"] == 39.0
    assert job["longitude"] == -76.0

    # Verify geocoding stats
    assert summary["geocoding_stats"]["failed"] == 2
    assert summary["geocoding_stats"]["success"] == 0


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = TheFoodBasketIncHiScraper()
    assert scraper1.scraper_id == "the_food_basket_inc_hi"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = TheFoodBasketIncHiScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = TheFoodBasketIncHiScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: TheFoodBasketIncHiScraper, mock_html_response: str
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
    assert summary["total_jobs_created"] == 0
    assert len(submitted_jobs) == 0
