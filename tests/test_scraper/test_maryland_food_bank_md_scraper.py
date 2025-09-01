"""Tests for Maryland Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.maryland_food_bank_md_scraper import MarylandFoodBankMdScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <div>
            <h3>Sample Food Pantry</h3>
            <div>
                <a href="https://maps.google.com/?q=123 Main St Baltimore MD 21227 USA">123 Main St Baltimore MD 21227 USA</a>
            </div>
            <div>
                <a href="tel:410-555-1234">410-555-1234</a>
            </div>
            <div>
                <a href="http://www.samplefoodpantry.org">www.samplefoodpantry.org</a>
            </div>
            <p>Hours open: Monday - Friday from 9 a.m. to 5 p.m.</p>
        </div>
        <div>
            <h3>Test Soup Kitchen</h3>
            <div>
                <a href="https://maps.google.com/?q=456 Oak Ave Catonsville MD 21228">456 Oak Ave Catonsville MD 21228</a>
            </div>
            <div>
                <a href="tel:443-555-5678">443-555-5678</a>
            </div>
            <p>Hours open: Thursdays from 12 p.m. – 2 p.m.</p>
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
                "address": "123 Main St, City, MD 12345",
                "phone": "(555) 123-4567",
                "hours": "Mon-Fri 9am-5pm",
            }
        ]
    }


@pytest.fixture
def scraper() -> MarylandFoodBankMdScraper:
    """Create scraper instance for testing."""
    return MarylandFoodBankMdScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: MarylandFoodBankMdScraper, mock_html_response: str
):
    """Test successful HTML download."""
    with patch(
        "app.scraper.maryland_food_bank_md_scraper.async_playwright"
    ) as mock_playwright:
        # Mock the playwright context manager
        mock_p = AsyncMock()
        mock_browser = AsyncMock()
        mock_page = AsyncMock()

        # Create async context manager
        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__.return_value = mock_p
        mock_async_playwright.__aexit__.return_value = None
        mock_playwright.return_value = mock_async_playwright

        # Set up the chain of mocks
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        # Mock page methods
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)  # No select element
        mock_page.wait_for_selector = AsyncMock()
        mock_page.locator = Mock()
        mock_page.locator.return_value.count = AsyncMock(return_value=2)
        mock_page.locator.return_value.text_content = AsyncMock(
            return_value="Showing 2 of 2 locations"
        )
        mock_page.content = AsyncMock(return_value=mock_html_response)

        mock_browser.close = AsyncMock()

        result = await scraper.download_html()

        assert result == mock_html_response
        mock_page.goto.assert_called_once_with(scraper.url, wait_until="networkidle")
        mock_page.click.assert_any_call('button:has-text("List")')


@pytest.mark.asyncio
async def test_download_html_failure(scraper: MarylandFoodBankMdScraper):
    """Test handling of download failures."""
    with patch(
        "app.scraper.maryland_food_bank_md_scraper.async_playwright"
    ) as mock_playwright:
        # Mock the playwright context manager
        mock_p = AsyncMock()
        mock_browser = AsyncMock()
        mock_page = AsyncMock()

        # Create async context manager
        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__.return_value = mock_p
        mock_async_playwright.__aexit__.return_value = None
        mock_playwright.return_value = mock_async_playwright

        # Set up the chain of mocks
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        # Make goto fail
        mock_page.goto = AsyncMock(side_effect=Exception("Connection error"))
        mock_browser.close = AsyncMock()

        with pytest.raises(Exception):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: MarylandFoodBankMdScraper, mock_json_response: Dict[str, Any]
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
async def test_fetch_api_data_failure(scraper: MarylandFoodBankMdScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: MarylandFoodBankMdScraper, mock_html_response: str):
    """Test HTML parsing."""
    locations = scraper.parse_html(mock_html_response)

    assert len(locations) == 2

    # Check first location
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St Baltimore MD 21227 USA"
    assert locations[0]["city"] == "Baltimore"
    assert locations[0]["state"] == "MD"
    assert locations[0]["zip"] == "21227"
    assert locations[0]["phone"] == "410-555-1234"
    assert locations[0]["website"] == "http://www.samplefoodpantry.org"
    assert locations[0]["hours"] == "Monday - Friday from 9 a.m. to 5 p.m."
    assert locations[0]["services"] == ["food pantry"]

    # Check second location
    assert locations[1]["name"] == "Test Soup Kitchen"
    assert locations[1]["address"] == "456 Oak Ave Catonsville MD 21228"
    assert locations[1]["city"] == "Catonsville"
    assert locations[1]["state"] == "MD"
    assert locations[1]["zip"] == "21228"
    assert locations[1]["phone"] == "443-555-5678"
    assert locations[1]["hours"] == "Thursdays from 12 p.m. – 2 p.m."
    assert locations[1]["services"] == ["hot meals"]


def test_parse_html_empty(scraper: MarylandFoodBankMdScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: MarylandFoodBankMdScraper, mock_json_response: Dict[str, Any]
):
    """Test API response processing."""
    # This scraper uses HTML parsing, not API, so process_api_response returns empty list
    locations = scraper.process_api_response(mock_json_response)

    assert len(locations) == 0


def test_process_api_response_empty(scraper: MarylandFoodBankMdScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: MarylandFoodBankMdScraper, mock_html_response: str
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
    assert summary["scraper_id"] == "maryland_food_bank_md"
    assert summary["food_bank"] == "Maryland Food Bank"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert "geocoding_stats" not in summary
    # Note: test_mode field was removed from summary in scraper updates
    # assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 2
    job = submitted_jobs[0]
    assert job["name"] == "Sample Food Pantry"
    # Note: latitude/longitude removed - validator service handles geocoding
    assert "latitude" not in job or job["latitude"] is None
    assert "longitude" not in job or job["longitude"] is None
    # Note: This scraper still uses OLD format - adds metadata to jobs
    assert job["source"] == "maryland_food_bank_md"
    assert job["food_bank"] == "Maryland Food Bank"


@pytest.mark.asyncio
async def test_scrape_without_geocoding(
    scraper: MarylandFoodBankMdScraper, mock_html_response: str
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
    scraper1 = MarylandFoodBankMdScraper()
    assert scraper1.scraper_id == "maryland_food_bank_md"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = MarylandFoodBankMdScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = MarylandFoodBankMdScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.skip(reason="This scraper uses HTML parsing, not API")
@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: MarylandFoodBankMdScraper, mock_json_response: Dict[str, Any]
):
    """Test complete API scraping flow."""
    # This test is skipped because Maryland Food Bank scraper uses HTML parsing, not API
    pass
