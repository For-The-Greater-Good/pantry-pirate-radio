"""Tests for Capital Area Food Bank scraper."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests

from app.scraper.capital_area_food_bank_dc_scraper import CapitalAreaFoodBankDcScraper


@pytest.fixture
def mock_arcgis_response() -> Dict[str, Any]:
    """Sample ArcGIS Feature Service response for testing."""
    return {
        "features": [
            {
                "attributes": {
                    "OBJECTID": 1,
                    "name": "Sample Food Pantry",
                    "address1": "123 Main St",
                    "address2": "Suite 100",
                    "city": "Washington",
                    "state": "DC",
                    "zip": "20001",
                    "county_name": "District of Columbia",
                    "phone": "(202) 555-1234",
                    "email": "contact@pantry.org",
                    "website": "https://pantry.org",
                    "tefap": "TEFAP Available",
                    "notes": "Call ahead for hours",
                    "start1_Monday": "9:00 AM",
                    "end1_Monday": "5:00 PM",
                    "start1_Wednesday": "9:00 AM",
                    "end1_Wednesday": "5:00 PM",
                    "start1_Friday": "9:00 AM",
                    "end1_Friday": "3:00 PM",
                },
                "geometry": {"x": -77.0369, "y": 38.9072},
            },
            {
                "attributes": {
                    "OBJECTID": 2,
                    "name": "Community Kitchen",
                    "address1": "456 Oak Ave",
                    "city": "Arlington",
                    "state": "VA",
                    "zip": "22201",
                    "county_name": "Arlington County",
                    "phone": "(703) 555-5678",
                    "tefap": "TEFAP Only",
                    "start1_Tuesday": "10:00 AM",
                    "end1_Tuesday": "2:00 PM",
                    "start1_Thursday": "10:00 AM",
                    "end1_Thursday": "2:00 PM",
                },
                "geometry": {"x": -77.1068, "y": 38.8799},
            },
        ]
    }


@pytest.fixture
def scraper() -> CapitalAreaFoodBankDcScraper:
    """Create scraper instance for testing."""
    return CapitalAreaFoodBankDcScraper(test_mode=True)


@pytest.mark.asyncio
async def test_query_arcgis_features_success(
    scraper: CapitalAreaFoodBankDcScraper, mock_arcgis_response: Dict[str, Any]
):
    """Test successful ArcGIS Feature Service query."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = mock_arcgis_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await scraper.query_arcgis_features(offset=0, limit=100)

        assert result == mock_arcgis_response
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0].endswith("/query")
        assert call_args[1]["params"]["where"] == "1=1"
        assert call_args[1]["params"]["f"] == "json"


@pytest.mark.asyncio
async def test_query_arcgis_features_failure(scraper: CapitalAreaFoodBankDcScraper):
    """Test handling of ArcGIS query failures."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("API error")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await scraper.query_arcgis_features()


def test_process_arcgis_features(
    scraper: CapitalAreaFoodBankDcScraper, mock_arcgis_response: Dict[str, Any]
):
    """Test processing ArcGIS features."""
    locations = scraper.process_arcgis_features(mock_arcgis_response["features"])

    assert len(locations) == 2

    # Check first location
    loc1 = locations[0]
    assert loc1["name"] == "Sample Food Pantry"
    assert loc1["address"] == "123 Main St"
    assert loc1["address2"] == "Suite 100"
    assert loc1["city"] == "Washington"
    assert loc1["state"] == "DC"
    assert loc1["zip"] == "20001"
    assert loc1["phone"] == "(202) 555-1234"
    assert loc1["latitude"] == 38.9072
    assert loc1["longitude"] == -77.0369
    assert "TEFAP Available" in loc1["services"]
    assert "Monday: 9:00 AM-5:00 PM" in loc1["hours"]
    assert "Wednesday: 9:00 AM-5:00 PM" in loc1["hours"]
    assert "Friday: 9:00 AM-3:00 PM" in loc1["hours"]

    # Check second location
    loc2 = locations[1]
    assert loc2["name"] == "Community Kitchen"
    assert loc2["city"] == "Arlington"
    assert loc2["state"] == "VA"
    assert "TEFAP Only" in loc2["services"]
    assert "Tuesday: 10:00 AM-2:00 PM" in loc2["hours"]
    assert "Thursday: 10:00 AM-2:00 PM" in loc2["hours"]


def test_process_arcgis_features_empty(scraper: CapitalAreaFoodBankDcScraper):
    """Test processing empty ArcGIS response."""
    locations = scraper.process_arcgis_features([])
    assert locations == []


def test_process_arcgis_features_no_hours(scraper: CapitalAreaFoodBankDcScraper):
    """Test processing location with no hours."""
    features = [
        {
            "attributes": {
                "OBJECTID": 3,
                "name": "No Hours Pantry",
                "address1": "789 Pine St",
                "city": "Bethesda",
                "state": "MD",
                "zip": "20814",
                "county_name": "Montgomery County",
            },
            "geometry": {"x": -77.0947, "y": 39.0142},
        }
    ]

    locations = scraper.process_arcgis_features(features)
    assert len(locations) == 1
    assert locations[0]["hours"] == "Call for hours"


@pytest.mark.asyncio
async def test_scrape_arcgis_flow(
    scraper: CapitalAreaFoodBankDcScraper, mock_arcgis_response: Dict[str, Any]
):
    """Test complete ArcGIS scraping flow."""
    # Mock ArcGIS query
    scraper.query_arcgis_features = AsyncMock(return_value=mock_arcgis_response)

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
    assert summary["scraper_id"] == "capital_area_food_bank_dc"
    assert summary["food_bank"] == "Capital Area Food Bank"
    assert summary["total_locations_found"] == 2
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["test_mode"] is True

    # Verify submitted jobs
    assert len(submitted_jobs) == 2

    # Check first job
    job1 = submitted_jobs[0]
    assert job1["name"] == "Sample Food Pantry"
    assert job1["latitude"] == 38.9072
    assert job1["longitude"] == -77.0369
    assert job1["source"] == "capital_area_food_bank_dc"
    assert job1["food_bank"] == "Capital Area Food Bank"
    assert "TEFAP Available" in job1["services"]

    # Check second job
    job2 = submitted_jobs[1]
    assert job2["name"] == "Community Kitchen"
    assert job2["latitude"] == 38.8799
    assert job2["longitude"] == -77.1068
    assert "TEFAP Only" in job2["services"]


@pytest.mark.asyncio
async def test_scrape_with_missing_coordinates(scraper: CapitalAreaFoodBankDcScraper):
    """Test scraping when ArcGIS doesn't provide coordinates."""
    # Mock ArcGIS response without coordinates
    no_coords_response = {
        "features": [
            {
                "attributes": {
                    "OBJECTID": 4,
                    "name": "No Coords Pantry",
                    "address1": "999 Lost St",
                    "city": "Somewhere",
                    "state": "DC",
                    "county_name": "District of Columbia",
                },
                "geometry": {},  # No coordinates
            }
        ]
    }

    scraper.query_arcgis_features = AsyncMock(return_value=no_coords_response)

    # Mock geocoder to fail
    scraper.geocoder.geocode_address = Mock(side_effect=ValueError("Geocoding failed"))
    scraper.geocoder.get_default_coordinates = Mock(return_value=(38.9, -77.0))

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
    assert job["latitude"] == 38.9
    assert job["longitude"] == -77.0

    # Verify geocoding stats
    assert summary["geocoding_stats"]["arcgis"] == 0
    assert summary["geocoding_stats"]["default"] == 1


def test_scraper_initialization():
    """Test scraper initialization."""
    # Test with default ID
    scraper1 = CapitalAreaFoodBankDcScraper()
    assert scraper1.scraper_id == "capital_area_food_bank_dc"
    assert scraper1.test_mode is False

    # Test with custom ID
    scraper2 = CapitalAreaFoodBankDcScraper(scraper_id="custom_id")
    assert scraper2.scraper_id == "custom_id"

    # Test with test mode
    scraper3 = CapitalAreaFoodBankDcScraper(test_mode=True)
    assert scraper3.test_mode is True
    assert scraper3.batch_size == 3  # Reduced in test mode
    assert scraper3.request_delay == 0.05  # Reduced in test mode


@pytest.mark.asyncio
async def test_scrape_with_pagination(scraper: CapitalAreaFoodBankDcScraper):
    """Test scraping with pagination."""
    # Create a page with exactly 1000 results to trigger pagination
    page1_features = []
    for i in range(1000):
        page1_features.append(
            {
                "attributes": {
                    "OBJECTID": i + 1,
                    "name": f"Pantry {i+1}",
                    "address1": f"{i+1} Main St",
                    "city": "DC",
                    "state": "DC",
                },
                "geometry": {"x": -77.0 + i * 0.001, "y": 38.9 - i * 0.001},
            }
        )

    page1 = {"features": page1_features}

    # Second page with 3 more results
    page2 = {
        "features": [
            {
                "attributes": {
                    "OBJECTID": 1001,
                    "name": "Pantry 1001",
                    "address1": "1001 Main St",
                    "city": "DC",
                    "state": "DC",
                },
                "geometry": {"x": -77.0, "y": 38.9},
            },
            {
                "attributes": {
                    "OBJECTID": 1002,
                    "name": "Pantry 1002",
                    "address1": "1002 Main St",
                    "city": "DC",
                    "state": "DC",
                },
                "geometry": {"x": -77.1, "y": 38.8},
            },
            {
                "attributes": {
                    "OBJECTID": 1003,
                    "name": "Pantry 1003",
                    "address1": "1003 Main St",
                    "city": "DC",
                    "state": "DC",
                },
                "geometry": {"x": -77.2, "y": 38.7},
            },
        ]
    }

    # Set up mock to return different pages
    scraper.query_arcgis_features = AsyncMock(side_effect=[page1, page2])
    scraper.test_mode = False  # Allow pagination
    scraper.submit_to_queue = Mock(return_value="job-id")

    # Run scraper
    summary_json = await scraper.scrape()
    summary = json.loads(summary_json)

    # Verify all locations were processed
    assert summary["total_locations_found"] == 1003
    assert summary["unique_locations"] == 1003
    assert summary["total_jobs_created"] == 1003

    # Verify query was called 2 times with different offsets
    assert scraper.query_arcgis_features.call_count == 2
    calls = scraper.query_arcgis_features.call_args_list
    assert calls[0][1]["offset"] == 0
    assert calls[1][1]["offset"] == 1000
