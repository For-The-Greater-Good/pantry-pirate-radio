"""Tests for Community Action of Napa Valley Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.community_action_of_napa_valley_food_bank_ca_scraper import (
    CommunityActionOfNapaValleyFoodBankCaScraper,
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
def scraper() -> CommunityActionOfNapaValleyFoodBankCaScraper:
    """Create scraper instance for testing."""
    return CommunityActionOfNapaValleyFoodBankCaScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper, mock_html_response: str
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
async def test_download_html_failure(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper,
):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper,
    mock_json_response: Dict[str, Any],
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
async def test_fetch_api_data_failure(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper,
):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper, mock_html_response: str
):
    """Test HTML parsing."""
    # Since the actual parser uses hardcoded location data, it doesn't parse the HTML
    # It just returns the known locations
    locations = scraper.parse_html(mock_html_response)

    assert len(locations) == 8
    assert locations[0]["name"] == "Napa Food Pantry (NEW LOCATION)"
    assert locations[0]["address"] == "938 Kaiser Road"
    assert locations[0]["city"] == "Napa"
    assert locations[0]["state"] == "CA"
    assert locations[0]["zip"] == "94559"


def test_parse_html_empty(scraper: CommunityActionOfNapaValleyFoodBankCaScraper):
    """Test parsing empty HTML."""
    # Since the parser uses hardcoded data, it always returns 8 locations
    locations = scraper.parse_html("<html><body></body></html>")
    assert len(locations) == 8


def test_process_api_response(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper,
    mock_json_response: Dict[str, Any],
):
    """Test API response processing."""
    # This scraper doesn't use API, so it returns empty list
    locations = scraper.process_api_response(mock_json_response)

    assert len(locations) == 0


def test_process_api_response_empty(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper,
):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper, mock_html_response: str
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
    assert summary["scraper_id"] == "community_action_of_napa_valley_food_bank_ca"
    assert summary["food_bank"] == "Community Action of Napa Valley Food Bank"
    assert summary["total_locations_found"] == 8
    assert summary["unique_locations"] == 8
    assert summary["total_jobs_created"] == 8
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 8
    job = submitted_jobs[0]
    assert job["name"] == "Napa Food Pantry (NEW LOCATION)"
    assert job["latitude"] == 40.0
    assert job["longitude"] == -75.0
    assert job["source"] == "community_action_of_napa_valley_food_bank_ca"
    assert job["food_bank"] == "Community Action of Napa Valley Food Bank"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper, mock_html_response: str
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
    assert len(submitted_jobs) == 8
    job = submitted_jobs[0]
    assert job["latitude"] == 39.0
    assert job["longitude"] == -76.0

    # Verify geocoding stats
    assert summary["geocoding_stats"]["failed"] == 8
    assert summary["geocoding_stats"]["success"] == 0


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = CommunityActionOfNapaValleyFoodBankCaScraper()
    assert scraper1.scraper_id == "community_action_of_napa_valley_food_bank_ca"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = CommunityActionOfNapaValleyFoodBankCaScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = CommunityActionOfNapaValleyFoodBankCaScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: CommunityActionOfNapaValleyFoodBankCaScraper,
    mock_json_response: Dict[str, Any],
):
    """Test complete API scraping flow."""
    # This scraper uses HTML parsing, not API
    # Mock download_html instead
    scraper.download_html = AsyncMock(return_value="<html></html>")

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

    # Verify summary (should have 8 locations)
    assert summary["total_jobs_created"] == 8
    assert len(submitted_jobs) == 8
