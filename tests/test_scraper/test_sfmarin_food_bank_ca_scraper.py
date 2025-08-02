"""Tests for SF-Marin Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.sfmarin_food_bank_ca_scraper import SfmarinFoodBankCAScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <input name="_token" value="test-csrf-token-123" />
        <div class="container">
            <h1>Food Locator</h1>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_json_response() -> Dict[str, Any]:
    """Sample JSON response for testing."""
    return {
        "ngns": [
            {
                "id": 1,
                "link_id": "TEST001",
                "name": "Sample Food Pantry",
                "address": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "zip": "94102",
                "phone": "(555) 123-4567",
                "lat": "37.7749",
                "lng": "-122.4194",
                "distro_day": "Monday",
                "distro_start": "9:00 AM",
                "distro_end": "5:00 PM",
                "enroll_time": "8:30 AM",
                "status": "enroll",
                "available": 50,
                "service_zips": ["94102", "94103"],
                "languages": ["374"],
                "agency_info": None
            }
        ]
    }


@pytest.fixture
def scraper() -> SfmarinFoodBankCAScraper:
    """Create scraper instance for testing."""
    return SfmarinFoodBankCAScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(scraper: SfmarinFoodBankCAScraper, mock_html_response: str):
    """Test successful HTML download."""
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.text = mock_html_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = await scraper.download_html()
        
        assert result == mock_html_response
        mock_get.assert_called_once_with(
            scraper.base_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
            timeout=scraper.timeout
        )


@pytest.mark.asyncio
async def test_download_html_failure(scraper: SfmarinFoodBankCAScraper):
    """Test handling of download failures."""
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")
        
        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(scraper: SfmarinFoodBankCAScraper, mock_html_response: str, mock_json_response: Dict[str, Any]):
    """Test successful API data fetch."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        # Mock GET response for CSRF token
        mock_get_response = Mock()
        mock_get_response.text = mock_html_response
        mock_client.get.return_value = mock_get_response
        
        # Mock POST response for API call
        mock_post_response = Mock()
        mock_post_response.json.return_value = mock_json_response
        mock_post_response.raise_for_status = Mock()
        mock_client.post.return_value = mock_post_response
        
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await scraper.fetch_api_data("sf")
        
        assert result["sites"] == mock_json_response["ngns"]
        mock_client.get.assert_called_once()
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_api_data_failure(scraper: SfmarinFoodBankCAScraper):
    """Test handling of API fetch failures."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("sf")


def test_parse_html(scraper: SfmarinFoodBankCAScraper, mock_html_response: str):
    """Test HTML parsing."""
    # Note: This scraper uses API, not HTML parsing
    locations = scraper.parse_html(mock_html_response)
    
    # The parse_html method is not fully implemented for this scraper
    assert locations == []


def test_parse_html_empty(scraper: SfmarinFoodBankCAScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(scraper: SfmarinFoodBankCAScraper, mock_json_response: Dict[str, Any]):
    """Test API response processing."""
    # Need to wrap response in expected format
    data = {"sites": mock_json_response["ngns"]}
    locations = scraper.process_api_response(data)
    
    assert len(locations) == 1
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St"
    assert locations[0]["city"] == "San Francisco"
    assert locations[0]["state"] == "CA"
    assert locations[0]["zip"] == "94102"
    assert locations[0]["latitude"] == 37.7749
    assert locations[0]["longitude"] == -122.4194


def test_process_api_response_empty(scraper: SfmarinFoodBankCAScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_api_flow(scraper: SfmarinFoodBankCAScraper, mock_html_response: str, mock_json_response: Dict[str, Any]):
    """Test complete API scraping flow."""
    # Mock fetch_api_data
    async def mock_fetch(county: str):
        return {"sites": mock_json_response["ngns"]}
    
    scraper.fetch_api_data = AsyncMock(side_effect=mock_fetch)
    
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
    assert summary["scraper_id"] == "sfmarin_food_bank_ca"
    assert summary["food_bank"] == "SF-Marin Food Bank"
    assert summary["total_locations_found"] == 1
    assert summary["unique_locations"] == 1
    assert summary["total_jobs_created"] == 1
    assert summary["test_mode"] is True
    
    # Verify submitted jobs
    assert len(submitted_jobs) == 1
    job = submitted_jobs[0]
    assert job["name"] == "Sample Food Pantry"
    assert job["latitude"] == 37.7749
    assert job["longitude"] == -122.4194
    assert job["source"] == "sfmarin_food_bank_ca"
    assert job["food_bank"] == "SF-Marin Food Bank"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(scraper: SfmarinFoodBankCAScraper, mock_json_response: Dict[str, Any]):
    """Test scraping when geocoding fails."""
    # Create response without lat/lng to trigger geocoding
    no_coords_response = {
        "ngns": [{
            "id": 1,
            "link_id": "TEST001",
            "name": "Sample Food Pantry",
            "address": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94102",
            "phone": "(555) 123-4567",
            "lat": None,
            "lng": None,
            "distro_day": "Monday",
            "distro_start": "9:00 AM",
            "distro_end": "5:00 PM",
            "enroll_time": "8:30 AM",
            "status": "enroll",
            "available": 50,
            "service_zips": ["94102", "94103"],
            "languages": ["374"],
            "agency_info": None
        }]
    }
    
    # Mock fetch_api_data
    async def mock_fetch(county: str):
        return {"sites": no_coords_response["ngns"]}
    
    scraper.fetch_api_data = AsyncMock(side_effect=mock_fetch)
    
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
    assert len(submitted_jobs) == 1
    job = submitted_jobs[0]
    assert job["latitude"] == 39.0
    assert job["longitude"] == -76.0
    
    # Verify geocoding stats
    assert summary["geocoding_stats"]["failed"] == 1
    assert summary["geocoding_stats"]["success"] == 0


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = SfmarinFoodBankCAScraper()
    assert scraper1.scraper_id == "sfmarin_food_bank_ca"
    assert scraper1.test_mode is False
    
    # Test with custom ID
    scraper2 = SfmarinFoodBankCAScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"
    
    # Test with test mode
    scraper3 = SfmarinFoodBankCAScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


# Removed duplicate test (already have test_scrape_api_flow above)