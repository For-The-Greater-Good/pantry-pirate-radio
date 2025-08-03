"""Tests for Food Bank of Contra Costa and Solano scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.food_bank_of_contra_costa_and_solano_ca_scraper import (
    FoodBankOfContraCostaAndSolanoCAScraper,
)


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <div class="et_pb_accordion">
            <h3>Contra Costa County</h3>
            <ul>
                <li><a href="/map-city/antioch/">Antioch</a></li>
                <li><a href="/map-city/concord/">Concord</a></li>
                <li><a href="/map-city/richmond/">Richmond</a></li>
            </ul>
            <h3>Solano County</h3>
            <ul>
                <li><a href="/map-city/fairfield/">Fairfield</a></li>
                <li><a href="/map-city/vallejo/">Vallejo</a></li>
            </ul>
        </div>
        <a href="/en-US/?mpfy_print_locations=37866%2C37723%2C42415%2C42414">Print results</a>
    </body>
    </html>
    """


@pytest.fixture
def mock_csv_response() -> str:
    """Sample CSV response from export endpoint."""
    return """Name,Address,City,State,Zip,Phone,Hours,Services,Notes,Latitude,Longitude
"Sample Food Pantry","123 Main St","Antioch","CA","94509","(555) 123-4567","Mon-Fri 9am-5pm","Food Distribution","Call for details","38.0050","-121.8058"
"Community Center","456 Oak Ave","Concord","CA","94520","(555) 987-6543","Tue-Thu 10am-2pm","Food Pantry","No appointment needed","37.9780","-122.0311"
"""


@pytest.fixture
def mock_city_html() -> str:
    """Sample city page HTML."""
    return """
    <html>
    <body>
        <table>
            <tr>
                <th>Name</th>
                <th>Address</th>
                <th>Phone</th>
                <th>Hours</th>
            </tr>
            <tr>
                <td>City Food Bank</td>
                <td>789 Pine St 94509</td>
                <td>(555) 555-5555</td>
                <td>Wed 2pm-4pm</td>
            </tr>
        </table>
    </body>
    </html>
    """


@pytest.fixture
def scraper() -> FoodBankOfContraCostaAndSolanoCAScraper:
    """Create scraper instance for testing."""
    return FoodBankOfContraCostaAndSolanoCAScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper, mock_html_response: str
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
async def test_download_html_failure(scraper: FoodBankOfContraCostaAndSolanoCAScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


@pytest.mark.asyncio
async def test_fetch_api_data_success(scraper: FoodBankOfContraCostaAndSolanoCAScraper):
    """Test successful API data fetch."""
    mock_json = {"test": "data"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await scraper.fetch_api_data("test/endpoint", params={"key": "value"})

        assert result == mock_json
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_api_data_failure(scraper: FoodBankOfContraCostaAndSolanoCAScraper):
    """Test handling of API fetch failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_api_data("test/endpoint")


def test_extract_city_links(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper, mock_html_response: str
):
    """Test extracting city links from main page."""
    city_links = scraper.extract_city_links(mock_html_response)

    assert len(city_links) == 5
    assert city_links[0] == ("Antioch", "https://www.foodbankccs.org/map-city/antioch/")
    assert city_links[1] == ("Concord", "https://www.foodbankccs.org/map-city/concord/")
    assert city_links[4] == ("Vallejo", "https://www.foodbankccs.org/map-city/vallejo/")


def test_extract_location_ids(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper, mock_html_response: str
):
    """Test extracting location IDs from main page."""
    location_ids = scraper.extract_location_ids(mock_html_response)

    assert len(location_ids) == 4
    assert "37866" in location_ids
    assert "37723" in location_ids
    assert "42415" in location_ids
    assert "42414" in location_ids


def test_parse_city_page(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper, mock_city_html: str
):
    """Test parsing city page."""
    locations = scraper.parse_city_page(mock_city_html, "Test City")

    assert len(locations) == 1
    assert locations[0]["name"] == "City Food Bank"
    assert locations[0]["address"] == "789 Pine St 94509"
    assert locations[0]["city"] == "Test City"
    assert locations[0]["zip"] == "94509"
    assert locations[0]["phone"] == "(555) 555-5555"
    assert locations[0]["hours"] == "Wed 2pm-4pm"


@pytest.mark.asyncio
async def test_fetch_locations_from_export(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper,
    mock_html_response: str,
    mock_csv_response: str,
):
    """Test fetching locations from export endpoint."""
    # Mock download_html to return main page
    scraper.download_html = AsyncMock(return_value=mock_html_response)

    # Mock export endpoint request
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.text = mock_csv_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        locations = await scraper.fetch_locations_from_export()

        assert len(locations) == 2
        assert locations[0]["name"] == "Sample Food Pantry"
        assert locations[0]["city"] == "Antioch"
        assert locations[0]["latitude"] == "38.0050"
        assert locations[0]["longitude"] == "-121.8058"
        assert locations[1]["name"] == "Community Center"


@pytest.mark.asyncio
async def test_scrape_export_flow(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper,
    mock_html_response: str,
    mock_csv_response: str,
):
    """Test complete export endpoint scraping flow."""
    # Mock fetch_locations_from_export to return parsed CSV data
    scraper.fetch_locations_from_export = AsyncMock(
        return_value=[
            {
                "name": "Sample Food Pantry",
                "address": "123 Main St",
                "city": "Antioch",
                "state": "CA",
                "zip": "94509",
                "phone": "(555) 123-4567",
                "hours": "Mon-Fri 9am-5pm",
                "services": "Food Distribution",
                "notes": "Call for details",
                "latitude": "38.0050",
                "longitude": "-121.8058",
            }
        ]
    )

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
    assert summary["scraper_id"] == "food_bank_of_contra_costa_and_solano_ca"
    assert summary["food_bank"] == "Food Bank of Contra Costa and Solano"
    assert summary["total_locations_found"] == 1
    assert summary["unique_locations"] == 1
    assert summary["total_jobs_created"] == 1
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 1
    job = submitted_jobs[0]
    assert job["name"] == "Sample Food Pantry"
    assert job["latitude"] == "38.0050"
    assert job["longitude"] == "-121.8058"
    assert job["source"] == "food_bank_of_contra_costa_and_solano_ca"
    assert job["food_bank"] == "Food Bank of Contra Costa and Solano"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper, mock_csv_response: str
):
    """Test scraping when geocoding fails."""
    # Mock fetch_locations_from_export to return location without coordinates
    scraper.fetch_locations_from_export = AsyncMock(
        return_value=[
            {
                "name": "Sample Food Pantry",
                "address": "123 Main St",
                "city": "Antioch",
                "state": "CA",
                "zip": "94509",
            }
        ]
    )

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
    scraper1 = FoodBankOfContraCostaAndSolanoCAScraper()
    assert scraper1.scraper_id == "food_bank_of_contra_costa_and_solano_ca"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = FoodBankOfContraCostaAndSolanoCAScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = FoodBankOfContraCostaAndSolanoCAScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_fallback_flow(
    scraper: FoodBankOfContraCostaAndSolanoCAScraper,
    mock_html_response: str,
    mock_city_html: str,
):
    """Test fallback to city page scraping when export fails."""
    # Mock export to fail
    scraper.fetch_locations_from_export = AsyncMock(return_value=[])

    # Mock download_html to return main page first, then city page
    scraper.download_html = AsyncMock(return_value=mock_html_response)

    # Mock city page requests
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.text = mock_city_html
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock geocoder
        scraper.geocoder.geocode_address = Mock(return_value=(38.0, -121.8))

        # Track submitted jobs
        submitted_jobs = []

        def mock_submit(content: str) -> str:
            submitted_jobs.append(json.loads(content))
            return f"job-{len(submitted_jobs)}"

        scraper.submit_to_queue = Mock(side_effect=mock_submit)

        # Run scraper (test mode limits to 3 cities)
        summary_json = await scraper.scrape()
        summary = json.loads(summary_json)

        # Verify we processed city pages
        assert mock_get.call_count == 3  # Limited by test mode
        # Each city page has 1 location, but they're all the same name so deduplication reduces to 1
        assert summary["total_jobs_created"] == 1
        assert len(submitted_jobs) == 1
