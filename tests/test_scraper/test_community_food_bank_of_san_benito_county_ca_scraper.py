"""Tests for Community Food Bank of San Benito County scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.community_food_bank_of_san_benito_county_ca_scraper import (
    CommunityFoodBankOfSanBenitoCountyCaScraper,
)


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <main>
            <article>
                <div>
                    <div>
                        <h3>Pick-Up in San Benito County</h3>
                        <p><strong>Mobile Pantry in Hollister</strong></p>
                        <p>Monday:</p>
                        <ul>
                            <li>Central & Willow – 12:30 p.m. – 1:30 p.m.</li>
                            <li>San Juan Rd & Rajkovich – 2:00 p.m. – 3 p.m.</li>
                        </ul>
                        <hr>
                        <p>Pre-packed grocery bags are available each week at designated pick up locations in San Benito County for people in need of food.</p>
                        <p><strong>Aromas</strong><br>
                        Location: Marshalls Grocery Market, 300 Carpenteria Road<br>
                        Time: Thursdays, 10:00 a.m. – 10:30 a.m.</p>
                    </div>
                </div>
            </article>
        </main>
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
def scraper() -> CommunityFoodBankOfSanBenitoCountyCaScraper:
    """Create scraper instance for testing."""
    return CommunityFoodBankOfSanBenitoCountyCaScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper, mock_html_response: str
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
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper,
):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper,
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
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper,
):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper, mock_html_response: str
):
    """Test HTML parsing."""
    locations = scraper.parse_html(mock_html_response)

    # Should find locations based on mock HTML
    assert len(locations) >= 2  # At least mobile pantry and static location

    # Check first mobile pantry location if present
    mobile_pantries = [loc for loc in locations if "Mobile Pantry" in loc["name"]]
    if mobile_pantries:
        mobile_pantry = mobile_pantries[0]
        assert mobile_pantry["city"] == "Hollister"
        assert mobile_pantry["state"] == "CA"
        assert mobile_pantry["phone"] == "(831) 637-0340"
        assert "mobile pantry" in mobile_pantry["services"]

    # Check static location if present
    static_locations = [loc for loc in locations if "Aromas" in loc["name"]]
    if static_locations:
        static_location = static_locations[0]
        assert static_location["city"] == "Aromas"
        assert "food pantry" in static_location["services"]


def test_parse_html_empty(scraper: CommunityFoodBankOfSanBenitoCountyCaScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper,
    mock_json_response: Dict[str, Any],
):
    """Test API response processing."""
    # This scraper uses HTML parsing, not API, so this should return empty
    locations = scraper.process_api_response(mock_json_response)
    assert len(locations) == 0


def test_process_api_response_empty(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper,
):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper, mock_html_response: str
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
    assert summary["scraper_id"] == "community_food_bank_of_san_benito_county_ca"
    assert summary["food_bank"] == "Community Food Bank of San Benito County"
    assert summary["total_locations_found"] >= 2
    assert summary["unique_locations"] >= 2
    assert summary["total_jobs_created"] >= 2
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) >= 2

    # Check first job has required fields
    job = submitted_jobs[0]
    assert "name" in job
    assert job["latitude"] == 40.0
    assert job["longitude"] == -75.0
    assert job["source"] == "community_food_bank_of_san_benito_county_ca"
    assert job["food_bank"] == "Community Food Bank of San Benito County"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper, mock_html_response: str
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
    assert len(submitted_jobs) >= 2

    # At least one job should have used fallback coordinates
    fallback_used = any(
        job["latitude"] == 39.0 and job["longitude"] == -76.0 for job in submitted_jobs
    )
    assert fallback_used

    # Verify geocoding stats
    assert summary["geocoding_stats"]["failed"] >= 1


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = CommunityFoodBankOfSanBenitoCountyCaScraper()
    assert scraper1.scraper_id == "community_food_bank_of_san_benito_county_ca"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = CommunityFoodBankOfSanBenitoCountyCaScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = CommunityFoodBankOfSanBenitoCountyCaScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_api_flow(
    scraper: CommunityFoodBankOfSanBenitoCountyCaScraper, mock_html_response: str
):
    """Test API flow (though this scraper uses HTML)."""
    # This scraper uses HTML parsing, not API
    # Mock download_html instead
    scraper.download_html = AsyncMock(return_value=mock_html_response)

    # Mock geocoder
    scraper.geocoder.geocode_address = Mock(return_value=(40.0, -75.0))
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
    assert summary["total_jobs_created"] >= 2
    assert len(submitted_jobs) >= 2
