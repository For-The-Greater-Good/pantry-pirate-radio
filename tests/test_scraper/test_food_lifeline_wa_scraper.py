"""Tests for Food Lifeline scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests

from app.scraper.food_lifeline_wa_scraper import FoodLifelineWAScraper


@pytest.fixture
def mock_html_response() -> str:
    """Sample HTML response for testing."""
    return """
    <html>
    <body>
        <div class="location-popup" data-location="loc-001">
            <h2 class="heading">Sample Food Pantry</h2>
            <div class="address">123 Main St, Seattle, WA 98101</div>
            <div class="type">Food Pantry</div>
            <div class="type">Emergency Food</div>
            <a href="mailto:contact@pantry.org">contact@pantry.org</a>
            <a href="https://pantry.org" target="_blank">Visit Site</a>
            <a href="tel:+12065551234">(206) 555-1234</a>
        </div>
        <div class="location-popup" data-location="loc-002">
            <h2 class="heading">Community Food Bank</h2>
            <div class="address">456 Oak Ave, Tacoma, WA 98402</div>
            <div class="type">Food Bank</div>
            <a href="tel:+12535555678">(253) 555-5678</a>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def scraper() -> FoodLifelineWAScraper:
    """Create scraper instance for testing."""
    return FoodLifelineWAScraper(test_mode=True)


@pytest.mark.asyncio
async def test_download_html_success(
    scraper: FoodLifelineWAScraper, mock_html_response: str
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
async def test_download_html_failure(scraper: FoodLifelineWAScraper):
    """Test handling of download failures."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            await scraper.download_html()


def test_parse_html(scraper: FoodLifelineWAScraper, mock_html_response: str):
    """Test HTML parsing."""
    locations = scraper.parse_html(mock_html_response)

    assert len(locations) == 2

    # Test first location
    assert locations[0]["id"] == "loc-001"
    assert locations[0]["name"] == "Sample Food Pantry"
    assert locations[0]["address"] == "123 Main St"
    assert locations[0]["city"] == "Seattle"
    assert locations[0]["state"] == "WA"
    assert locations[0]["zip"] == "98101"
    assert locations[0]["phone"] == "(206) 555-1234"
    assert locations[0]["email"] == "contact@pantry.org"
    assert locations[0]["website"] == "https://pantry.org"
    assert locations[0]["services"] == ["Food Pantry", "Emergency Food"]
    assert locations[0]["full_address"] == "123 Main St, Seattle, WA 98101"

    # Test second location
    assert locations[1]["id"] == "loc-002"
    assert locations[1]["name"] == "Community Food Bank"
    assert locations[1]["address"] == "456 Oak Ave"
    assert locations[1]["city"] == "Tacoma"
    assert locations[1]["state"] == "WA"
    assert locations[1]["zip"] == "98402"
    assert locations[1]["phone"] == "(253) 555-5678"
    assert locations[1]["services"] == ["Food Bank"]


def test_parse_html_empty(scraper: FoodLifelineWAScraper):
    """Test parsing empty HTML."""
    locations = scraper.parse_html("<html><body></body></html>")
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_html_flow(
    scraper: FoodLifelineWAScraper, mock_html_response: str
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
    assert summary["scraper_id"] == "food_lifeline_wa"
    assert summary["food_bank"] == "Food Lifeline"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 2

    # Check first job
    job1 = submitted_jobs[0]
    assert job1["name"] == "Sample Food Pantry"
    assert job1["latitude"] == 40.0
    assert job1["longitude"] == -75.0
    assert job1["source"] == "food_lifeline_wa"
    assert job1["food_bank"] == "Food Lifeline"
    assert job1["email"] == "contact@pantry.org"
    assert job1["website"] == "https://pantry.org"
    assert job1["services"] == ["Food Pantry", "Emergency Food"]

    # Check second job
    job2 = submitted_jobs[1]
    assert job2["name"] == "Community Food Bank"
    assert job2["source"] == "food_lifeline_wa"
    assert job2["food_bank"] == "Food Lifeline"


@pytest.mark.asyncio
async def test_scrape_with_geocoding_failure(
    scraper: FoodLifelineWAScraper, mock_html_response: str
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

    # Both jobs should use fallback coordinates
    for job in submitted_jobs:
        assert job["latitude"] == 39.0
        assert job["longitude"] == -76.0

    # Verify geocoding stats
    assert summary["geocoding_stats"]["failed"] == 2
    assert summary["geocoding_stats"]["success"] == 0


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = FoodLifelineWAScraper()
    assert scraper1.scraper_id == "food_lifeline_wa"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = FoodLifelineWAScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = FoodLifelineWAScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode
