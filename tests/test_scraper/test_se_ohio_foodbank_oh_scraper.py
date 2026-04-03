"""Tests for SE Ohio Foodbank OH scraper."""

import json
from typing import Any

import pytest
from unittest.mock import patch

from app.scraper.scrapers.se_ohio_foodbank_oh_scraper import (
    SE_OHIO_ZIPS,
    SeOhioFoodbankOhScraper,
)


@pytest.fixture
def mock_agency_response():
    """Mock FreshTrak API agency response for SE Ohio."""
    return [
        {
            "id": 501,
            "name": "Athens County Food Pantry",
            "address": "1005 CIC Drive",
            "city": "Athens",
            "state": "OH",
            "zip": "45701",
            "phone": "740-555-1234",
            "latitude": "39.3292",
            "longitude": "-82.1013",
            "nickname": "ACFP",
        },
        {
            "id": 502,
            "name": "Hocking County Food Center",
            "address": "100 E Main St",
            "city": "Logan",
            "state": "OH",
            "zip": "43138",
            "phone": "",
            "latitude": "39.5401",
            "longitude": "-82.4071",
            "nickname": "",
        },
        {
            "id": 503,
            "name": "Marietta Community Pantry",
            "address": "200 Front St",
            "city": "Marietta",
            "state": "OH",
            "zip": "45750",
            "phone": "740-555-9876",
            "latitude": "39.4145",
            "longitude": "-81.4549",
            "nickname": "MCP",
        },
    ]


def test_scraper_init():
    """Test scraper initializes with correct defaults."""
    scraper = SeOhioFoodbankOhScraper()
    assert scraper.scraper_id == "se_ohio_foodbank_oh"
    assert "freshtrak.com" in scraper.base_url
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    """Test scraper initializes with test_mode enabled."""
    scraper = SeOhioFoodbankOhScraper(test_mode=True)
    assert scraper.test_mode is True


def test_zip_codes_cover_se_ohio():
    """Test that ZIP codes cover the 9-county SE Ohio area."""
    assert len(SE_OHIO_ZIPS) >= 15
    # Should have Athens, Hocking, Washington county zips
    assert "45701" in SE_OHIO_ZIPS  # Athens
    assert "43138" in SE_OHIO_ZIPS  # Logan (Hocking)
    assert "45750" in SE_OHIO_ZIPS  # Marietta (Washington)


def test_parse_agency_valid(mock_agency_response):
    """Test parsing a valid agency record."""
    scraper = SeOhioFoodbankOhScraper()
    result = scraper._parse_agency(mock_agency_response[0])

    assert result is not None
    assert result["name"] == "Athens County Food Pantry"
    assert result["city"] == "Athens"
    assert result["state"] == "OH"
    assert result["zip"] == "45701"
    assert result["latitude"] == 39.3292
    assert result["longitude"] == -82.1013


def test_parse_agency_empty_phone(mock_agency_response):
    """Test parsing handles empty phone gracefully."""
    scraper = SeOhioFoodbankOhScraper()
    result = scraper._parse_agency(mock_agency_response[1])

    assert result is not None
    assert result["phone"] == ""


def test_parse_agency_no_name():
    """Test parsing rejects records with no name."""
    scraper = SeOhioFoodbankOhScraper()
    result = scraper._parse_agency({"name": "", "address": "123 Main"})
    assert result is None


def test_parse_agency_invalid_coordinates():
    """Test parsing handles invalid coordinates."""
    scraper = SeOhioFoodbankOhScraper()
    result = scraper._parse_agency(
        {
            "id": 999,
            "name": "Bad Coords Pantry",
            "address": "123 Main",
            "city": "Athens",
            "state": "OH",
            "zip": "45701",
            "phone": "",
            "latitude": "invalid",
            "longitude": "bad",
            "nickname": "",
        }
    )
    assert result is not None
    assert result["latitude"] is None
    assert result["longitude"] is None


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_agency_response):
    """Test that duplicate agencies are removed."""
    scraper = SeOhioFoodbankOhScraper(test_mode=True)

    # Return same agencies for multiple zips
    async def mock_fetch(client, zip_code):
        return mock_agency_response

    with patch.object(scraper, "fetch_agencies_by_zip", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    # 3 zips in test mode, each returning 3 agencies, but dedup by ID
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3


@pytest.mark.asyncio
async def test_scrape_metadata(mock_agency_response):
    """Test that scraped locations include correct metadata."""
    scraper = SeOhioFoodbankOhScraper(test_mode=True)

    submitted: list[str] = []

    def capture(data):
        submitted.append(data)
        return "job_123"

    async def mock_fetch(client, zip_code):
        return mock_agency_response[:1]

    with patch.object(scraper, "fetch_agencies_by_zip", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert len(submitted) >= 1
    loc = json.loads(submitted[0])
    assert loc["source"] == "se_ohio_foodbank_oh"
    assert loc["food_bank"] == "SE Ohio Foodbank"


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_agency_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = SeOhioFoodbankOhScraper(test_mode=True)

    async def mock_fetch(client, zip_code):
        return mock_agency_response

    with patch.object(scraper, "fetch_agencies_by_zip", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "se_ohio_foodbank_oh"
    assert summary["food_bank"] == "SE Ohio Foodbank"


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = SeOhioFoodbankOhScraper(test_mode=True)

    async def mock_fetch(client, zip_code):
        return []

    with patch.object(scraper, "fetch_agencies_by_zip", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
