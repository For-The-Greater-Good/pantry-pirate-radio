"""Tests for Tarrant Area Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.tarrant_area_food_bank_tx_scraper import TarrantAreaFoodBankTXScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    # Sample Store Locator Plus results HTML
    return """
    <html>
    <body>
        <div class="results_wrapper">
            <div class="results_entry location_0">
                <span class="location_name">First Missionary Baptist Church</span>
                <div class="slp_result_address">
                    PO Box 15342<br/>
                    Fort Worth, TX 76119
                </div>
                <span class="slp_result_phone">817-487-7020</span>
                <div class="slp_result_description">Every 3rd Saturday of the month</div>
            </div>
            <div class="results_entry location_1">
                <span class="location_name">Broadway Baptist Church</span>
                <div class="slp_result_address">
                    305 W Broadway<br/>
                    Fort Worth, TX 76104
                </div>
                <span class="slp_result_phone">817-336-5761</span>
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
                "address": "123 Main St, City, TX 12345",
                "phone": "(555) 123-4567",
                "hours": "Mon-Fri 9am-5pm",
            }
        ]
    }


@pytest.fixture
def scraper() -> TarrantAreaFoodBankTXScraper:
    """Create scraper instance for testing."""
    return TarrantAreaFoodBankTXScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: TarrantAreaFoodBankTXScraper, mock_html_response: str
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
async def test_download_html_failure(scraper: TarrantAreaFoodBankTXScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: TarrantAreaFoodBankTXScraper, mock_json_response: Dict[str, Any]
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
async def test_fetch_api_data_failure(scraper: TarrantAreaFoodBankTXScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: TarrantAreaFoodBankTXScraper, mock_html_response: str):
    """Test HTML parsing."""
    locations = scraper.parse_html(mock_html_response)

    assert len(locations) == 2

    # First location
    assert locations[0]["name"] == "First Missionary Baptist Church"
    assert locations[0]["address"] == "PO Box 15342 Fort Worth, TX 76119"
    assert locations[0]["phone"] == "817-487-7020"
    assert locations[0]["hours"] == "Every 3rd Saturday of the month"

    # Second location
    assert locations[1]["name"] == "Broadway Baptist Church"
    assert locations[1]["address"] == "305 W Broadway Fort Worth, TX 76104"
    assert locations[1]["phone"] == "817-336-5761"


def test_parse_html_empty(scraper: TarrantAreaFoodBankTXScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: TarrantAreaFoodBankTXScraper, mock_json_response: Dict[str, Any]
):
    """Test API response processing."""
    # The Tarrant scraper doesn't use API, so process_api_response returns empty list
    locations = scraper.process_api_response(mock_json_response)

    assert len(locations) == 0  # Not implemented for this scraper


def test_process_api_response_empty(scraper: TarrantAreaFoodBankTXScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: TarrantAreaFoodBankTXScraper, mock_html_response: str
):
    """Test complete HTML scraping flow."""
    # Mock requests.get to return our test HTML
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.text = mock_html_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

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
        assert summary["scraper_id"] == "tarrant_area_food_bank_tx"
        assert summary["food_bank"] == "Tarrant Area Food Bank"
        assert summary["total_locations"] == 2
        assert summary["total_jobs_created"] == 2
        assert summary["test_mode"] is True

        # Verify submitted jobs
        assert len(submitted_jobs) == 2
        job = submitted_jobs[0]
        assert job["name"] == "First Missionary Baptist Church"
        assert job["latitude"] == 40.0
        assert job["longitude"] == -75.0
        assert job["source"] == "tarrant_area_food_bank_tx"
        assert job["food_bank"] == "Tarrant Area Food Bank"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: TarrantAreaFoodBankTXScraper, mock_html_response: str
):
    """Test scraping when geocoding fails."""
    # Mock requests.get to return our test HTML
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.text = mock_html_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock geocoder to fail
        scraper.geocoder.geocode_address = Mock(
            side_effect=ValueError("Geocoding failed")
        )
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
    scraper1 = TarrantAreaFoodBankTXScraper()
    assert scraper1.scraper_id == "tarrant_area_food_bank_tx"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = TarrantAreaFoodBankTXScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = TarrantAreaFoodBankTXScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_with_zip_search(
    scraper: TarrantAreaFoodBankTXScraper, mock_html_response: str
):
    """Test scraping with ZIP code search."""
    # Mock requests.get to return our HTML response
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.text = mock_html_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock geocoder
        scraper.geocoder.geocode_address = Mock(return_value=(32.7357, -97.1081))

        # Track submitted jobs
        submitted_jobs = []

        def mock_submit(content: str) -> str:
            submitted_jobs.append(json.loads(content))
            return f"job-{len(submitted_jobs)}"

        scraper.submit_to_queue = Mock(side_effect=mock_submit)

        # Run scraper
        summary_json = await scraper.scrape()
        summary = json.loads(summary_json)

        # Should have searched 3 ZIP codes in test mode
        assert summary["search_zips_used"] == 3
        assert summary["total_jobs_created"] == 2  # 2 unique locations
        assert len(submitted_jobs) == 2
