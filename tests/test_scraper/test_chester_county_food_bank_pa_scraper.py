"""Tests for Chester County Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.chester_county_food_bank_pa_scraper import (
    ChesterCountyFoodBankPaScraper,
)


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <script>
        var map_data = {
            "locations": [
                {"lat":40.040690400000003,"lng":-75.490907699999994,"post_id":8192,"types":["food-providers"],"city":"Paoli"},
                {"lat":39.959174500000003,"lng":-75.928025300000002,"post_id":8223,"types":["food-providers"],"city":"Parkesburg"}
            ]
        };
        </script>
        <div class="tbody results-wrap">
            <div class="t-row">
                <div class="td">Paoli</div>
                <div class="td">Presbyterian Church — 225 S Valley Rd Paoli, PA</div>
                <div class="td">(610) 644-8250</div>
                <div class="td">First Wednesday of every month: 8:45 – 9:45 am</div>
            </div>
            <div class="t-row">
                <div class="td">Parkesburg</div>
                <div class="td">Octorara Area Food Cupboard — 714 Main St Parkesburg, PA</div>
                <div class="td">(610) 857-4000</div>
                <div class="td">Tuesdays & Wednesdays: 11:00am-1:00pm and 2:00-5:00pm</div>
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
                "address": "123 Main St, City, PA 12345",
                "phone": "(555) 123-4567",
                "hours": "Mon-Fri 9am-5pm",
            }
        ]
    }


@pytest.fixture
def scraper() -> ChesterCountyFoodBankPaScraper:
    """Create scraper instance for testing."""
    return ChesterCountyFoodBankPaScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: ChesterCountyFoodBankPaScraper, mock_html_response: str
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
async def test_download_html_failure(scraper: ChesterCountyFoodBankPaScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: ChesterCountyFoodBankPaScraper, mock_json_response: Dict[str, Any]
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
async def test_fetch_api_data_failure(scraper: ChesterCountyFoodBankPaScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: ChesterCountyFoodBankPaScraper, mock_html_response: str):
    """Test HTML parsing."""
    locations = scraper.parse_html(mock_html_response)

    assert len(locations) == 2

    # Check first location
    assert locations[0]["name"] == "Presbyterian Church"
    assert locations[0]["address"] == "225 S Valley Rd"
    assert locations[0]["city"] == "Paoli"
    assert locations[0]["phone"] == "(610) 644-8250"
    assert "First Wednesday" in locations[0]["hours"]
    assert locations[0]["latitude"] == 40.040690400000003
    assert locations[0]["longitude"] == -75.490907699999994

    # Check second location
    assert locations[1]["name"] == "Octorara Area Food Cupboard"
    assert locations[1]["address"] == "714 Main St"
    assert locations[1]["city"] == "Parkesburg"
    assert locations[1]["phone"] == "(610) 857-4000"
    assert "Tuesdays" in locations[1]["hours"]
    assert locations[1]["latitude"] == 39.959174500000003
    assert locations[1]["longitude"] == -75.928025300000002


def test_parse_html_empty(scraper: ChesterCountyFoodBankPaScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: ChesterCountyFoodBankPaScraper, mock_json_response: Dict[str, Any]
):
    """Test API response processing."""
    locations = scraper.process_api_response(mock_json_response)

    assert len(locations) == 1
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St, City, PA 12345"


def test_process_api_response_empty(scraper: ChesterCountyFoodBankPaScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: ChesterCountyFoodBankPaScraper, mock_html_response: str
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
    assert summary["scraper_id"] == "chester_county_food_bank_pa"
    assert summary["food_bank"] == "Chester County Food Bank"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 2
    job = submitted_jobs[0]
    assert job["name"] == "Presbyterian Church"
    assert job["latitude"] == 40.040690400000003
    assert job["longitude"] == -75.490907699999994
    assert job["source"] == "chester_county_food_bank_pa"
    assert job["food_bank"] == "Chester County Food Bank"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: ChesterCountyFoodBankPaScraper, mock_html_response: str
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
    # Note: coordinates come from map_data, not geocoding, so they should still be correct
    job = submitted_jobs[0]
    assert job["latitude"] == 40.040690400000003
    assert job["longitude"] == -75.490907699999994

    # Verify geocoding stats (no geocoding needed since coords in map_data)
    assert summary["geocoding_stats"]["failed"] == 0
    assert summary["geocoding_stats"]["success"] == 0


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = ChesterCountyFoodBankPaScraper()
    assert scraper1.scraper_id == "chester_county_food_bank_pa"
    assert scraper1.test_mode is False
    assert scraper1.url == "https://chestercountyfoodbank.org/find-help/food-finder/"

    # Test with custom ID
    scraper2 = ChesterCountyFoodBankPaScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = ChesterCountyFoodBankPaScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: ChesterCountyFoodBankPaScraper, mock_json_response: Dict[str, Any]
):
    """Test complete API scraping flow."""
    # Mock API fetch
    scraper.fetch_api_data = AsyncMock(return_value=mock_json_response)

    # Override parse_html to use process_api_response instead
    scraper.parse_html = Mock(
        side_effect=lambda x: scraper.process_api_response(mock_json_response)
    )

    # Mock geocoder (locations in API response don't have addresses)
    scraper.geocoder.get_default_coordinates = Mock(return_value=(40.0, -75.0))

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
    assert len(submitted_jobs) == 1
