"""Tests for FIND Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.find_food_bank_ca_scraper import FindFoodBankCaScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <div class="facetwp-location">
            <div class="facetwp-location-title">Southwest Church</div>
            <div class="facetwp-location-details">
                <p><strong>Hours of Operation:</strong> Emergency Bags Available Monday through Friday from 9:00 am – 5:00 pm</p>
                <p><strong>Location:</strong> 44-175 Washington St. Indian Wells, CA 92210</p>
                <p><strong>Contact:</strong> <a href="tel:7602002000">(760) 200-2000</a></p>
            </div>
        </div>
        <div class="facetwp-location">
            <div class="facetwp-location-title">FIND Mobile Market - Rancho Las Flores Park</div>
            <div class="facetwp-location-details">
                <p><strong>Hours of Operation:</strong> 4th Friday of the month from 8:00am – 9:00am</p>
                <p><strong>Location:</strong> 48400 Van Buren St. Coachella, CA 92236</p>
                <p><strong>Contact:</strong> FIND Food Bank at <a href="tel:7607753663">(760) 775-3663</a></p>
                <p>See Mobile Market Calendar Each Month for Updates</p>
            </div>
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
                "address": "123 Main St, City, CA 12345",
                "phone": "(555) 123-4567",
                "hours": "Mon-Fri 9am-5pm",
            }
        ]
    }


@pytest.fixture
def scraper() -> FindFoodBankCaScraper:
    """Create scraper instance for testing."""
    return FindFoodBankCaScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: FindFoodBankCaScraper, mock_html_response: str
):
    """Test successful HTML download with Playwright."""
    # Mock the entire playwright async context manager chain
    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_playwright = AsyncMock()

    # Setup the mock chain
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    # Mock page methods
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(
        side_effect=[True, {"debug": True, "pager": {}}, None]
    )  # FWP checks
    mock_page.wait_for_selector = AsyncMock(
        side_effect=Exception("Timeout")
    )  # Simulates no facetwp divs
    mock_page.locator = AsyncMock()
    mock_page.content = AsyncMock(return_value=mock_html_response)

    with patch(
        "app.scraper.find_food_bank_ca_scraper.async_playwright"
    ) as mock_async_playwright:
        mock_async_playwright.return_value.__aenter__.return_value = mock_playwright

        result = await scraper.download_html()

        assert mock_html_response in result  # Page might add wrapper HTML
        mock_page.goto.assert_called_once_with(scraper.url, wait_until="networkidle")


@pytest.mark.asyncio
async def test_download_html_failure(scraper: FindFoodBankCaScraper):
    """Test handling of download failures with Playwright."""
    # Mock playwright to raise an exception
    mock_playwright = AsyncMock()
    mock_playwright.chromium.launch.side_effect = Exception("Browser launch failed")

    with patch(
        "app.scraper.find_food_bank_ca_scraper.async_playwright"
    ) as mock_async_playwright:
        mock_async_playwright.return_value.__aenter__.return_value = mock_playwright

        with pytest.raises(Exception, match="Browser launch failed"):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: FindFoodBankCaScraper, mock_json_response: Dict[str, Any]
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
async def test_fetch_api_data_failure(scraper: FindFoodBankCaScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: FindFoodBankCaScraper, mock_html_response: str):
    """Test HTML parsing."""
    locations = scraper.parse_html(mock_html_response)

    assert len(locations) == 2

    # Test first location
    assert locations[0]["name"] == "Southwest Church"
    assert locations[0]["address"] == "44-175 Washington St. Indian Wells, CA 92210"
    assert locations[0]["city"] == "Indian Wells"
    assert locations[0]["zip"] == "92210"
    assert locations[0]["phone"] == "(760) 200-2000"
    assert (
        locations[0]["hours"]
        == "Emergency Bags Available Monday through Friday from 9:00 am – 5:00 pm"
    )

    # Test second location
    assert locations[1]["name"] == "FIND Mobile Market - Rancho Las Flores Park"
    assert locations[1]["address"] == "48400 Van Buren St. Coachella, CA 92236"
    assert locations[1]["city"] == "Coachella"
    assert locations[1]["zip"] == "92236"
    assert locations[1]["phone"] == "(760) 775-3663"
    assert locations[1]["hours"] == "4th Friday of the month from 8:00am – 9:00am"


def test_parse_html_empty(scraper: FindFoodBankCaScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: FindFoodBankCaScraper, mock_json_response: Dict[str, Any]
):
    """Test API response processing."""
    # This scraper uses HTML parsing, not API, so process_api_response returns empty
    locations = scraper.process_api_response(mock_json_response)

    assert len(locations) == 0


def test_process_api_response_empty(scraper: FindFoodBankCaScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: FindFoodBankCaScraper, mock_html_response: str
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
    assert summary["scraper_id"] == "find_food_bank_ca"
    assert summary["food_bank"] == "FIND Food Bank"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 2
    job = submitted_jobs[0]
    assert job["name"] == "Southwest Church"
    assert job["latitude"] == 40.0
    assert job["longitude"] == -75.0
    assert job["source"] == "find_food_bank_ca"
    assert job["food_bank"] == "FIND Food Bank"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: FindFoodBankCaScraper, mock_html_response: str
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
    scraper1 = FindFoodBankCaScraper()
    assert scraper1.scraper_id == "find_food_bank_ca"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = FindFoodBankCaScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = FindFoodBankCaScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode
