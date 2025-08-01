"""Tests for Second Harvest Food Bank of Northwest North Carolina scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.second_harvest_food_bank_of_northwest_north_carolina_nc_scraper import SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    # Main page with iframe
    return """
    <html>
    <body>
        <iframe class="wuksD5" src="https://example.com/iframe.html"></iframe>
    </body>
    </html>
    """


@pytest.fixture
def mock_iframe_response() -> str:
    """Sample iframe HTML response for testing."""
    return """
    <html>
    <body>
        <div>
            <div>
                <p><a href="#">Sample Food Pantry</a></p>
                <p>Mon-Fri 9am-5pm</p>
                <p>123 Main St, City, 12345</p>
                <p><a href="tel:5551234567">(555) 123-4567</a></p>
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
                "address": "123 Main St, City, NC 12345",
                "phone": "(555) 123-4567",
                "hours": "Mon-Fri 9am-5pm"
            }
        ]
    }


@pytest.fixture
def scraper() -> SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper:
    """Create scraper instance for testing."""
    return SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper, mock_html_response: str):
    """Test successful HTML download."""
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.text = mock_html_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = await scraper.download_html()
        
        assert result == mock_html_response
        mock_get.assert_called_once_with(
            scraper.url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
            timeout=scraper.timeout
        )


@pytest.mark.asyncio
async def test_download_html_failure(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper):
    """Test handling of download failures."""
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")
        
        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper, mock_json_response: Dict[str, Any]):
    """Test successful API data fetch."""
    with patch('httpx.AsyncClient') as mock_client_class:
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
async def test_fetch_api_data_failure(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper):
    """Test handling of API fetch failures."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper, mock_html_response: str, mock_iframe_response: str):
    """Test HTML parsing."""
    # Mock the iframe content fetch
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.text = mock_iframe_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        locations = scraper.parse_html(mock_html_response)
        
        assert len(locations) == 1
        location = locations[0]
        
        # Check all expected fields exist
        assert "name" in location
        assert "address" in location
        assert "city" in location
        assert "zip" in location
        assert "phone" in location
        assert "hours" in location
        assert "services" in location
        
        # Check values
        assert location["name"] == "Sample Food Pantry"
        assert location["address"] == "123 Main St"
        assert location["city"] == "City"
        assert location["zip"] == "12345"
        assert location["phone"] == "(555) 123-4567"
        assert location["hours"] == "Mon-Fri 9am-5pm"
        assert isinstance(location["services"], list)
        assert "Food Pantry" in location["services"]


def test_parse_html_empty(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper, mock_json_response: Dict[str, Any]):
    """Test Excel file download (placeholder)."""
    # Scraper uses HTML parsing, not API, so this test is adapted
    locations = scraper.download_excel_file("https://example.com/file.xls")
    assert locations == []  # Currently returns empty list


def test_process_api_response_empty(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper):
    """Test empty Excel file download."""
    locations = scraper.download_excel_file("")
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper, mock_html_response: str, mock_iframe_response: str):
    """Test complete HTML scraping flow."""
    # Mock download_html
    scraper.download_html = AsyncMock(return_value=mock_html_response)
    
    # Mock iframe content fetch
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.text = mock_iframe_response
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
        assert summary["scraper_id"] == "second_harvest_food_bank_of_northwest_north_carolina_nc"
        assert summary["food_bank"] == "Second Harvest Food Bank of Northwest North Carolina"
        assert summary["total_locations_found"] == 1
        assert summary["unique_locations"] == 1
        assert summary["total_jobs_created"] == 1
        assert summary["test_mode"] is True
        
        # Verify submitted jobs
        assert len(submitted_jobs) == 1
        job = submitted_jobs[0]
        assert job["name"] == "Sample Food Pantry"
        assert job["latitude"] == 40.0
        assert job["longitude"] == -75.0
        assert job["source"] == "second_harvest_food_bank_of_northwest_north_carolina_nc"
        assert job["food_bank"] == "Second Harvest Food Bank of Northwest North Carolina"
        assert "services" in job
        assert isinstance(job["services"], list)


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper, mock_html_response: str, mock_iframe_response: str):
    """Test scraping when geocoding fails."""
    # Mock download_html
    scraper.download_html = AsyncMock(return_value=mock_html_response)
    
    # Mock iframe content fetch
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.text = mock_iframe_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
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
    scraper1 = SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper()
    assert scraper1.scraper_id == "second_harvest_food_bank_of_northwest_north_carolina_nc"
    assert scraper1.test_mode is False
    
    # Test with custom ID
    scraper2 = SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"
    
    # Test with test mode
    scraper3 = SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.skip(reason="This scraper uses HTML parsing with iframe, not API")
@pytest.mark.asyncio
async def test_scrape_api_flow(scraper: SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper, mock_json_response: Dict[str, Any]):
    """Test complete API scraping flow."""
    # This test is skipped because the scraper uses HTML parsing, not API
    pass