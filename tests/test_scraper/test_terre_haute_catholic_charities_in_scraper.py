"""Tests for Terre Haute Catholic Charities Foodbank scraper."""

import json
from unittest.mock import patch, AsyncMock

import httpx
import pytest

from app.scraper.scrapers.terre_haute_catholic_charities_in_scraper import (
    TerreHauteCatholicCharitiesInScraper,
    FOOD_BANK_NAME,
    KNOWN_VENUES,
)


MOCK_EVENTS_API_RESPONSE = {
    "events": [
        {
            "title": "St. Joseph Food Distribution",
            "description": "<p>Monthly food distribution</p>",
            "start_date": "2026-03-15 09:00:00",
            "start_date_details": {
                "year": "2026",
                "month": "03",
                "day": "15",
            },
            "end_date_details": {},
            "all_day": False,
            "venue": {
                "venue": "St. Joseph University Parish",
                "address": "113 S 5th St",
                "city": "Terre Haute",
                "state": "IN",
                "zip": "47807",
                "phone": "812-232-7011",
            },
        },
        {
            "title": "Sacred Heart Food Pantry",
            "description": "<p>Weekly pantry hours</p>",
            "start_date": "2026-03-20 10:00:00",
            "start_date_details": {
                "year": "2026",
                "month": "03",
                "day": "20",
            },
            "end_date_details": {},
            "all_day": False,
            "venue": {
                "venue": "Sacred Heart Church",
                "address": "575 Poplar St",
                "city": "Terre Haute",
                "state": "IN",
                "zip": "47803",
                "phone": "",
            },
        },
        {
            "title": "Duplicate Event at St. Joseph",
            "description": "",
            "start_date": "2026-04-12 09:00:00",
            "start_date_details": {},
            "end_date_details": {},
            "all_day": False,
            "venue": {
                "venue": "St. Joseph University Parish",
                "address": "113 S 5th St",
                "city": "Terre Haute",
                "state": "IN",
                "zip": "47807",
                "phone": "812-232-7011",
            },
        },
    ],
    "total_pages": 1,
}


@pytest.fixture
def mock_events_response():
    """Mock WordPress Events Calendar API response."""
    return MOCK_EVENTS_API_RESPONSE


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = TerreHauteCatholicCharitiesInScraper()
    assert scraper.scraper_id == "terre_haute_catholic_charities_in"
    assert "ccthin.org" in scraper.base_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = TerreHauteCatholicCharitiesInScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_venue():
    """Test parsing venue from event data."""
    scraper = TerreHauteCatholicCharitiesInScraper()

    event = {
        "title": "Food Distribution",
        "description": "<p>Monthly event</p>",
        "start_date": "2026-03-15 09:00:00",
        "start_date_details": {"year": "2026"},
        "all_day": False,
        "venue": {
            "venue": "Test Church",
            "address": "123 Main St",
            "city": "Terre Haute",
            "state": "IN",
            "zip": "47807",
            "phone": "812-555-1234",
        },
    }
    loc = scraper._parse_venue(event)
    assert loc is not None
    assert loc["name"] == "Test Church"
    assert loc["address"] == "123 Main St"
    assert loc["city"] == "Terre Haute"
    assert loc["state"] == "IN"
    assert loc["phone"] == "812-555-1234"


@pytest.mark.asyncio
async def test_parse_venue_no_venue():
    """Test parsing event with no venue returns None."""
    scraper = TerreHauteCatholicCharitiesInScraper()
    event = {"title": "Event", "venue": {}}
    loc = scraper._parse_venue(event)
    assert loc is None


@pytest.mark.asyncio
async def test_parse_venue_empty_state_defaults():
    """Test parsing defaults empty state to IN."""
    scraper = TerreHauteCatholicCharitiesInScraper()
    event = {
        "title": "Event",
        "venue": {
            "venue": "Test",
            "address": "123 Main",
            "city": "Terre Haute",
            "state": "",
            "zip": "47807",
            "phone": "",
        },
    }
    loc = scraper._parse_venue(event)
    assert loc is not None
    assert loc["state"] == "IN"


@pytest.mark.asyncio
async def test_scrape_from_api(mock_events_response):
    """Test scrape via API deduplicates venues."""
    scraper = TerreHauteCatholicCharitiesInScraper(test_mode=True)

    async def mock_api(client):
        return mock_events_response["events"]

    async def mock_html(client):
        return []

    with patch.object(
        scraper,
        "_fetch_events_api",
        side_effect=mock_api,
    ):
        with patch.object(
            scraper,
            "_fetch_events_html",
            side_effect=mock_html,
        ):
            with patch.object(
                scraper,
                "submit_to_queue",
                return_value="job_123",
            ):
                result = await scraper.scrape()

    summary = json.loads(result)
    # 3 events but only 2 unique venues
    assert summary["total_events"] == 3
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2


@pytest.mark.asyncio
async def test_scrape_metadata(mock_events_response):
    """Test that scraped locations include correct metadata."""
    scraper = TerreHauteCatholicCharitiesInScraper(test_mode=True)

    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_api(client):
        return mock_events_response["events"]

    async def mock_html(client):
        return []

    with patch.object(
        scraper, "_fetch_events_api", side_effect=mock_api
    ):
        with patch.object(
            scraper, "_fetch_events_html", side_effect=mock_html
        ):
            with patch.object(
                scraper, "submit_to_queue", side_effect=capture
            ):
                await scraper.scrape()

    assert len(submitted) >= 1
    assert (
        submitted[0]["source"]
        == "terre_haute_catholic_charities_in"
    )
    assert submitted[0]["food_bank"] == FOOD_BANK_NAME


@pytest.mark.asyncio
async def test_scrape_fallback_to_known_venues():
    """Test fallback to known venues when API and HTML fail."""
    scraper = TerreHauteCatholicCharitiesInScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_api_empty(client):
        return []

    async def mock_html_empty(client):
        return []

    with patch.object(
        scraper,
        "_fetch_events_api",
        side_effect=mock_api_empty,
    ):
        with patch.object(
            scraper,
            "_fetch_events_html",
            side_effect=mock_html_empty,
        ):
            with patch.object(
                scraper, "submit_to_queue", side_effect=capture
            ):
                result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 5
    assert (
        submitted[0]["source"]
        == "terre_haute_catholic_charities_in"
    )
    assert submitted[0]["food_bank"] == FOOD_BANK_NAME


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API and HTML with fallback."""
    scraper = TerreHauteCatholicCharitiesInScraper(test_mode=True)

    async def mock_api_empty(client):
        return []

    async def mock_html_empty(client):
        return []

    with patch.object(
        scraper,
        "_fetch_events_api",
        side_effect=mock_api_empty,
    ):
        with patch.object(
            scraper,
            "_fetch_events_html",
            side_effect=mock_html_empty,
        ):
            with patch.object(
                scraper,
                "submit_to_queue",
                return_value="job_123",
            ):
                result = await scraper.scrape()

    summary = json.loads(result)
    # Falls back to known venues (test_mode limits to 5)
    expected = min(len(KNOWN_VENUES), 5)
    assert summary["unique_locations"] == expected
    assert summary["total_jobs_created"] == expected
