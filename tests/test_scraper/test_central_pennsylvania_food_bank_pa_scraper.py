"""Tests for Central Pennsylvania Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.central_pennsylvania_food_bank_pa_scraper import CentralPennsylvaniaFoodBankPAScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    # TODO: Add actual HTML sample from the food bank website
    return """
    <html>
    <body>
        <div class="location">
            <h3>Sample Food Pantry</h3>
            <p class="address">123 Main St, City, PA 12345</p>
            <p class="phone">(555) 123-4567</p>
            <p class="hours">Mon-Fri 9am-5pm</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_json_response() -> Dict[str, Any]:
    """Sample JSON response for testing Store Locator Plus API."""
    return {
        "response": [
            {
                "id": "123",
                "name": "OASIS COMMUNITY PARTNERSHIP",
                "address": "206 Oakleigh Avenue",
                "city": "Harrisburg",
                "state": "PA",
                "zip": "17111",
                "phone": "(717)564-5003",
                "lat": "40.285841",
                "lng": "-76.831462",
                "categories": "Pantry",
                "hours": "Mon-Fri 9am-5pm"
            },
            {
                "id": "124",
                "name": "THE SALVATION ARMY FAMILY SERVICES",
                "address": "506 S. 29Th St.",
                "city": "Harrisburg",
                "state": "PA",
                "zip": "17104",
                "phone": "(717)233-6755",
                "lat": "40.252631",
                "lng": "-76.896523",
                "categories": "Multi-Service Program"
            }
        ]
    }


@pytest.fixture
def scraper() -> CentralPennsylvaniaFoodBankPAScraper:
    """Create scraper instance for testing."""
    return CentralPennsylvaniaFoodBankPAScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(scraper: CentralPennsylvaniaFoodBankPAScraper, mock_html_response: str):
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
async def test_download_html_failure(scraper: CentralPennsylvaniaFoodBankPAScraper):
    """Test handling of download failures."""
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")
        
        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(scraper: CentralPennsylvaniaFoodBankPAScraper, mock_json_response: Dict[str, Any]):
    """Test successful API data fetch."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        # Return JSON as text for JSONP handling
        mock_response.text = json.dumps(mock_json_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await scraper.fetch_api_data("locations-map/search", params={"lat": 40.0, "lng": -75.0})
        
        assert result == mock_json_response
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_api_data_failure(scraper: CentralPennsylvaniaFoodBankPAScraper):
    """Test handling of API fetch failures."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_parse_html(scraper: CentralPennsylvaniaFoodBankPAScraper, mock_html_response: str):
    """Test HTML parsing."""
    # TODO: Update this test based on actual HTML structure
    locations = scraper.parse_html(mock_html_response)
    
    assert len(locations) == 1
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St, City, PA 12345"
    assert locations[0]["phone"] == "(555) 123-4567"
    assert locations[0]["hours"] == "Mon-Fri 9am-5pm"


def test_parse_html_empty(scraper: CentralPennsylvaniaFoodBankPAScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


def test_process_api_response(scraper: CentralPennsylvaniaFoodBankPAScraper, mock_json_response: Dict[str, Any]):
    """Test API response processing."""
    locations = scraper.process_api_response(mock_json_response)
    
    assert len(locations) == 2
    assert locations[0]["name"] == "OASIS COMMUNITY PARTNERSHIP"
    assert locations[0]["address"] == "206 Oakleigh Avenue"
    assert locations[0]["city"] == "Harrisburg"
    assert locations[0]["state"] == "PA"
    assert locations[0]["zip"] == "17111"
    assert locations[0]["phone"] == "(717)564-5003"
    assert locations[0]["latitude"] == 40.285841
    assert locations[0]["longitude"] == -76.831462
    assert locations[0]["services"] == ["Pantry"]
    
    assert locations[1]["name"] == "THE SALVATION ARMY FAMILY SERVICES"
    assert locations[1]["services"] == ["Multi-Service Program"]


def test_process_api_response_empty(scraper: CentralPennsylvaniaFoodBankPAScraper):
    """Test processing empty API response."""
    locations = scraper.process_api_response({})
    assert locations == []


def test_process_api_response_service_types(scraper: CentralPennsylvaniaFoodBankPAScraper):
    """Test correct parsing of different service types from categories."""
    response = {
        "response": [
            {"id": "1", "name": "Test 1", "categories": "Fresh Express", "lat": "40.0", "lng": "-75.0", "city": "Test", "state": "PA"},
            {"id": "2", "name": "Test 2", "categories": "Soup Kitchen", "lat": "40.0", "lng": "-75.0", "city": "Test", "state": "PA"},
            {"id": "3", "name": "Test 3", "categories": "Pantry/Soup Kitchen", "lat": "40.0", "lng": "-75.0", "city": "Test", "state": "PA"},
            {"id": "4", "name": "Test 4", "categories": "", "lat": "40.0", "lng": "-75.0", "city": "Test", "state": "PA"},
        ]
    }
    
    locations = scraper.process_api_response(response)
    
    assert len(locations) == 4
    assert locations[0]["services"] == ["Fresh Express"]
    assert locations[1]["services"] == ["Soup Kitchen"]
    assert locations[2]["services"] == ["Pantry/Soup Kitchen"]
    assert locations[3]["services"] == ["Pantry"]  # Default


@pytest.mark.asyncio
async def test_scrape_with_jsonp_response(scraper: CentralPennsylvaniaFoodBankPAScraper, mock_json_response: Dict[str, Any]):
    """Test handling of JSONP wrapped responses."""
    # Mock grid points 
    from app.models.geographic import GridPoint
    mock_grid_points = [
        GridPoint(lat=40.27, lng=-76.88),
    ]
    scraper.utils.get_state_grid_points = Mock(return_value=mock_grid_points)
    
    # Mock API fetch with JSONP wrapper
    jsonp_response = f"initMySLP({json.dumps(mock_json_response)});"
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.text = jsonp_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Track submitted jobs
        submitted_jobs = []
        
        def mock_submit(content: str) -> str:
            submitted_jobs.append(json.loads(content))
            return f"job-{len(submitted_jobs)}"
        
        scraper.submit_to_queue = Mock(side_effect=mock_submit)
        
        # Run scraper
        summary_json = await scraper.scrape()
        summary = json.loads(summary_json)
        
        # Verify we handled JSONP correctly
        assert summary["total_jobs_created"] == 2
        assert len(submitted_jobs) == 2


@pytest.mark.asyncio
async def test_scrape_with_api_error_handling(scraper: CentralPennsylvaniaFoodBankPAScraper):
    """Test graceful handling of API errors during grid search."""
    # Mock grid points 
    from app.models.geographic import GridPoint
    mock_grid_points = [
        GridPoint(lat=40.27, lng=-76.88),
        GridPoint(lat=41.0, lng=-77.0),  # This one will fail
    ]
    scraper.utils.get_state_grid_points = Mock(return_value=mock_grid_points)
    
    # Mock API to succeed on first call, fail on second
    successful_response = {"response": [{"id": "1", "name": "Test Location", "lat": "40.0", "lng": "-75.0", "city": "Test", "state": "PA"}]}
    scraper.fetch_api_data = AsyncMock(side_effect=[successful_response, Exception("API Error")])
    
    # Track submitted jobs
    submitted_jobs = []
    
    def mock_submit(content: str) -> str:
        submitted_jobs.append(json.loads(content))
        return f"job-{len(submitted_jobs)}"
    
    scraper.submit_to_queue = Mock(side_effect=mock_submit)
    
    # Run scraper - should continue despite one grid point failing
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)
    
    # Should have processed the successful grid point
    assert summary["total_jobs_created"] == 1
    assert len(submitted_jobs) == 1
    assert submitted_jobs[0]["name"] == "Test Location"


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = CentralPennsylvaniaFoodBankPAScraper()
    assert scraper1.scraper_id == "central_pennsylvania_food_bank_pa"
    assert scraper1.test_mode is False
    
    # Test with custom ID
    scraper2 = CentralPennsylvaniaFoodBankPAScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"
    
    # Test with test mode
    scraper3 = CentralPennsylvaniaFoodBankPAScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_api_flow(scraper: CentralPennsylvaniaFoodBankPAScraper, mock_json_response: Dict[str, Any]):
    """Test complete API scraping flow with Store Locator Plus."""
    # Mock grid points 
    from app.models.geographic import GridPoint
    mock_grid_points = [
        GridPoint(lat=40.27, lng=-76.88),  # Harrisburg area
    ]
    scraper.utils.get_state_grid_points = Mock(return_value=mock_grid_points)
    
    # Mock API fetch
    scraper.fetch_api_data = AsyncMock(return_value=mock_json_response)
    
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
    assert summary["total_jobs_created"] == 2
    assert summary["unique_locations"] == 2
    assert len(submitted_jobs) == 2
    
    # Verify submitted jobs have correct data
    job1 = submitted_jobs[0]
    assert job1["name"] == "OASIS COMMUNITY PARTNERSHIP"
    assert job1["latitude"] == 40.285841
    assert job1["longitude"] == -76.831462
    assert job1["services"] == ["Pantry"]
    
    job2 = submitted_jobs[1]
    assert job2["name"] == "THE SALVATION ARMY FAMILY SERVICES"
    assert job2["services"] == ["Multi-Service Program"]