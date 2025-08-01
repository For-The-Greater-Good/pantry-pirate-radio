"""Tests for Feeding the Gulf Coast scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.scraper.feeding_the_gulf_coast_al_scraper import FeedingTheGulfCoastALScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <div class="pantry-result">
            <article class="pantry-location">
                <div class="pantry-address">
                    <p class="epsilon">Sample Food Pantry</p>
                    <p class="street">123 Main St<br>Mobile, AL 36601</p>
                    <p class="phone-number bold">(251) 123-4567</p>
                </div>
                <div class="pantry-direction">
                    <p class="mileage">5.2 miles<br>
                    Mon-Fri 9am-5pm</p>
                </div>
            </article>
        </div>
        <div class="pantry-result">
            <article class="pantry-location">
                <div class="pantry-address">
                    <p class="epsilon">Community Kitchen</p>
                    <p class="street">456 Oak Ave<br>Daphne, AL 36526</p>
                    <p class="phone-number bold">(251) 987-6543</p>
                </div>
                <div class="pantry-direction">
                    <p class="mileage">10.5 miles<br>
                    Daily 11am-2pm</p>
                </div>
            </article>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_empty_html() -> str:
    """Empty HTML response for testing."""
    return "<html><body><p>No results found</p></body></html>"


@pytest.fixture
def scraper() -> FeedingTheGulfCoastALScraper:
    """Create scraper instance for testing."""
    return FeedingTheGulfCoastALScraper(test_mode=True)


@pytest.mark.asyncio
async def test_fetch_results_html_success(scraper: FeedingTheGulfCoastALScraper, mock_html_response: str):
    """Test successful HTML fetch from results page."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.text = mock_html_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await scraper.fetch_results_html()
        
        assert result == mock_html_response
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == scraper.results_url
        assert call_args[1]['params'] == {'address': '', 'near': '100'}


@pytest.mark.asyncio
async def test_fetch_results_html_failure(scraper: FeedingTheGulfCoastALScraper):
    """Test handling of fetch failures."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection error")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_results_html()


def test_parse_location_element(scraper: FeedingTheGulfCoastALScraper):
    """Test parsing a location element."""
    from bs4 import BeautifulSoup
    
    html = '''
    <div class="pantry-result">
        <article class="pantry-location">
            <div class="pantry-address">
                <p class="epsilon">Test Pantry</p>
                <p class="street">123 Main St<br>Mobile, AL 36601</p>
                <p class="phone-number bold">(251) 123-4567</p>
            </div>
            <div class="pantry-direction">
                <p class="mileage">5.2 miles<br>Mon-Fri 9am-5pm</p>
            </div>
        </article>
    </div>
    '''
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.find('div', class_='pantry-result')
    
    locations = scraper.parse_results_html(html)
    
    assert len(locations) == 1
    location = locations[0]
    assert location['name'] == 'Test Pantry'
    assert location['address'] == '123 Main St'
    assert location['city'] == 'Mobile'
    assert location['state'] == 'AL'
    assert location['zip'] == '36601'
    assert location['phone'] == '(251) 123-4567'
    assert location['distance'] == '5.2 miles'
    assert location.get('notes') == 'Mon-Fri 9am-5pm'


def test_parse_results_html(scraper: FeedingTheGulfCoastALScraper, mock_html_response: str):
    """Test HTML parsing from results page."""
    locations = scraper.parse_results_html(mock_html_response)
    
    assert len(locations) == 2
    
    # Check first location
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St"
    assert locations[0]["city"] == "Mobile"
    assert locations[0]["state"] == "AL"
    assert locations[0]["zip"] == "36601"
    assert locations[0]["phone"] == "(251) 123-4567"
    assert locations[0]["distance"] == "5.2 miles"
    
    # Check second location
    assert locations[1]["name"] == "Community Kitchen"
    assert locations[1]["city"] == "Daphne"


def test_parse_results_html_empty(scraper: FeedingTheGulfCoastALScraper, mock_empty_html: str):
    """Test parsing empty HTML."""
    locations = scraper.parse_results_html(mock_empty_html)
    assert locations == []


def test_parse_address_text(scraper: FeedingTheGulfCoastALScraper):
    """Test address parsing."""
    location = {}
    
    # Test full address
    scraper.parse_address_text("123 Main St, Mobile, AL 36601", location)
    assert location['address'] == '123 Main St'
    assert location['city'] == 'Mobile'
    assert location['state'] == 'AL'
    assert location['zip'] == '36601'
    
    # Test address with different state
    location2 = {}
    scraper.parse_address_text("456 Beach Blvd, Pensacola, FL 32501", location2)
    assert location2['state'] == 'FL'
    assert location2['city'] == 'Pensacola'


@pytest.mark.asyncio
async def test_scrape_html_flow(scraper: FeedingTheGulfCoastALScraper, mock_html_response: str):
    """Test complete HTML scraping flow."""
    # Mock fetch_results_html
    scraper.fetch_results_html = AsyncMock(return_value=mock_html_response)
    
    # Mock geocoder for default coordinates
    scraper.geocoder.get_default_coordinates = Mock(return_value=(30.696, -88.043))
    
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
    assert summary["scraper_id"] == "feeding_the_gulf_coast_al"
    assert summary["food_bank"] == "Feeding the Gulf Coast"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["test_mode"] is True
    assert "note" in summary
    
    # Verify submitted jobs
    assert len(submitted_jobs) == 2
    job = submitted_jobs[0]
    assert job["name"] == "Sample Food Pantry"
    assert "latitude" in job
    assert "longitude" in job
    assert job["source"] == "feeding_the_gulf_coast_al"
    assert job["food_bank"] == "Feeding the Gulf Coast"




def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = FeedingTheGulfCoastALScraper()
    assert scraper1.scraper_id == "feeding_the_gulf_coast_al"
    assert scraper1.test_mode is False
    
    # Test with custom ID
    scraper2 = FeedingTheGulfCoastALScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"
    
    # Test with test mode
    scraper3 = FeedingTheGulfCoastALScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_error_handling(scraper: FeedingTheGulfCoastALScraper):
    """Test error handling during scrape."""
    # Mock fetch to raise error
    scraper.fetch_results_html = AsyncMock(side_effect=httpx.HTTPError("Server error"))
    
    # Should raise the error
    with pytest.raises(httpx.HTTPError):
        await scraper.scrape()