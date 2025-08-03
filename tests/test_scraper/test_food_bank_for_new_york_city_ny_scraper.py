"""Tests for Food Bank For New York City scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.food_bank_for_new_york_city_ny_scraper import (
    FoodBankForNewYorkCityNyScraper,
)


@pytest.fixture
def mock_kml_response() -> str:
    """Sample KML response for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Sample Food Pantry</name>
      <description><![CDATA[
        123 Main St, Brooklyn, NY 11201<br>
        Phone: (555) 123-4567<br>
        Hours: Monday-Friday 9am-5pm
      ]]></description>
      <Point>
        <coordinates>-73.9442,40.6782,0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Another Food Bank</name>
      <description><![CDATA[
        456 Second Ave, Manhattan, NY 10003<br>
        (212) 555-7890<br>
        Open: Tuesday-Saturday 10am-6pm
      ]]></description>
      <Point>
        <coordinates>-73.9857,40.7295,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""


@pytest.fixture
def scraper() -> FoodBankForNewYorkCityNyScraper:
    """Create scraper instance for testing."""
    return FoodBankForNewYorkCityNyScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_kml_success(
    scraper: FoodBankForNewYorkCityNyScraper, mock_kml_response: str
):
    """Test successful KML download."""
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.text = mock_kml_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = await scraper.download_kml()

        assert result == mock_kml_response
        mock_get.assert_called_once_with(
            scraper.kml_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=scraper.timeout,
        )


@pytest.mark.asyncio
async def test_download_kml_failure(scraper: FoodBankForNewYorkCityNyScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_kml()


def test_parse_kml(scraper: FoodBankForNewYorkCityNyScraper, mock_kml_response: str):
    """Test KML parsing."""
    locations = scraper.parse_kml(mock_kml_response)

    assert len(locations) == 2

    # Check first location
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St"
    assert locations[0]["city"] == "Brooklyn"
    assert locations[0]["zip"] == "11201"
    assert locations[0]["phone"] == "(555) 123-4567"
    assert "Monday-Friday 9am-5pm" in locations[0]["hours"]
    assert locations[0]["latitude"] == 40.6782
    assert locations[0]["longitude"] == -73.9442

    # Check second location
    assert locations[1]["name"] == "Another Food Bank"
    assert locations[1]["address"] == "456 Second Ave"
    assert locations[1]["city"] == "Manhattan"
    assert locations[1]["zip"] == "10003"
    assert locations[1]["phone"] == "(212) 555-7890"
    assert "Tuesday-Saturday 10am-6pm" in locations[1]["hours"]
    assert locations[1]["latitude"] == 40.7295
    assert locations[1]["longitude"] == -73.9857


def test_parse_kml_empty(scraper: FoodBankForNewYorkCityNyScraper):
    """Test parsing empty KML."""
    empty_kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
  </Document>
</kml>"""
    locations = scraper.parse_kml(empty_kml)
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_kml_flow(
    scraper: FoodBankForNewYorkCityNyScraper, mock_kml_response: str
):
    """Test complete KML scraping flow."""
    # Mock download_kml
    scraper.download_kml = AsyncMock(return_value=mock_kml_response)

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
    assert summary["scraper_id"] == "food_bank_for_new_york_city_ny"
    assert summary["food_bank"] == "Food Bank For New York City"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 2

    # Check first job
    job1 = submitted_jobs[0]
    assert job1["name"] == "Sample Food Pantry"
    assert job1["latitude"] == 40.6782
    assert job1["longitude"] == -73.9442
    assert job1["source"] == "food_bank_for_new_york_city_ny"
    assert job1["food_bank"] == "Food Bank For New York City"

    # Check second job
    job2 = submitted_jobs[1]
    assert job2["name"] == "Another Food Bank"
    assert job2["latitude"] == 40.7295
    assert job2["longitude"] == -73.9857


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(scraper: FoodBankForNewYorkCityNyScraper):
    """Test scraping when geocoding fails."""
    # Create KML without coordinates
    kml_no_coords = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>No Coords Pantry</name>
      <description><![CDATA[
        789 Third St, Queens, NY 11375
      ]]></description>
    </Placemark>
  </Document>
</kml>"""

    # Mock download_kml
    scraper.download_kml = AsyncMock(return_value=kml_no_coords)

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
    assert job["name"] == "No Coords Pantry"
    assert job["latitude"] == 39.0
    assert job["longitude"] == -76.0

    # Verify geocoding stats
    assert summary["geocoding_stats"]["failed"] == 1
    assert summary["geocoding_stats"]["success"] == 0


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = FoodBankForNewYorkCityNyScraper()
    assert scraper1.scraper_id == "food_bank_for_new_york_city_ny"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = FoodBankForNewYorkCityNyScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = FoodBankForNewYorkCityNyScraper(test_mode=True)
    assert scraper3.test_mode is True
