"""Tests for Food Bank of North Alabama scraper."""

import json

import httpx
import pytest
from unittest.mock import patch

from app.scraper.scrapers.food_bank_of_north_alabama_al_scraper import (
    FoodBankOfNorthAlabamaAlScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP (Store Locator Plus) API response for North Alabama."""
    return [
        {
            "id": "201",
            "name": "Huntsville Community Pantry",
            "address": "1000 Meridian St N",
            "address2": "",
            "city": "Huntsville",
            "state": "AL",
            "zip": "35801",
            "phone": "256-555-1234",
            "lat": "34.7304",
            "lng": "-86.5861",
            "hours": "<p>Monday-Friday 9:00 AM - 4:00 PM</p>",
            "url": "https://huntsvillepantry.org",
            "email": "info@huntsvillepantry.org",
            "description": "<p>Serving Madison County families</p>",
            "tags": "pantry, food distribution",
            "distance": "0.1",
        },
        {
            "id": "202",
            "name": "Decatur Food Assistance Center",
            "address": "500 Bank St NE",
            "address2": "Building C",
            "city": "Decatur",
            "state": "",
            "zip": "35601",
            "phone": "",
            "lat": "34.6059",
            "lng": "-86.9833",
            "hours": '<table class="slp-hours"><tr><td>Tuesday</td><td>10am-2pm</td></tr><tr><td>Thursday</td><td>10am-2pm</td></tr></table>',
            "url": "",
            "email": "",
            "description": "<p>Bring photo ID and proof of address</p>",
            "tags": "<a>food pantry</a>, <a>Se habla espanol</a>",
            "distance": "15.3",
        },
        {
            "id": "203",
            "name": "Athens Area Food Bank",
            "address": "200 W Washington St",
            "address2": "",
            "city": "Athens",
            "state": "AL",
            "zip": "35611",
            "phone": "256-555-9876",
            "lat": "34.8023",
            "lng": "-86.9717",
            "hours": "",
            "url": "",
            "email": "",
            "description": "<p>1st and 3rd Saturday<br/>8:00 AM - 11:00 AM</p>",
            "tags": "",
            "distance": "25.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfNorthAlabamaAlScraper()
    assert scraper.scraper_id == "food_bank_of_north_alabama_al"
    assert "foodbanknorthal.org" in scraper.ajax_url
    assert scraper.test_mode is False
    assert scraper.center_lat == 34.7304
    assert scraper.center_lng == -86.5861
    assert scraper.search_radius == 200


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Huntsville Community Pantry"
    assert loc["city"] == "Huntsville"
    assert loc["state"] == "AL"
    assert loc["zip"] == "35801"
    assert loc["latitude"] == 34.7304
    assert loc["longitude"] == -86.5861
    assert loc["phone"] == "256-555-1234"
    assert "Monday-Friday" in loc["hours"]
    assert "9:00 AM - 4:00 PM" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state field with AL default."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "AL"  # Defaults to AL


@pytest.mark.asyncio
async def test_parse_location_with_address2(mock_slp_response):
    """Test parsing includes address2 in full_address."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert "Building C" in loc["full_address"]
    assert "500 Bank St NE" in loc["full_address"]


@pytest.mark.asyncio
async def test_parse_location_hours_table(mock_slp_response):
    """Test parsing extracts text from HTML hours table."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert "Tuesday" in loc["hours"]
    assert "10am-2pm" in loc["hours"]
    assert "Thursday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_hours_fallback_to_description(mock_slp_response):
    """Test that hours falls back to description when hours field is empty."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[2])
    # hours field is empty, so it falls back to description
    assert "Saturday" in loc["hours"]
    assert "8:00 AM" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_email(mock_slp_response):
    """Test parsing extracts email field."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["email"] == "info@huntsvillepantry.org"


@pytest.mark.asyncio
async def test_parse_location_url(mock_slp_response):
    """Test parsing extracts URL field."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["url"] == "https://huntsvillepantry.org"


@pytest.mark.asyncio
async def test_parse_location_tags(mock_slp_response):
    """Test parsing extracts and cleans tags including HTML tags."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert "food pantry" in loc["tags"]
    assert "Se habla espanol" in loc["tags"]
    # HTML anchor tags should be stripped
    assert "<a>" not in loc["tags"]


@pytest.mark.asyncio
async def test_parse_location_description_html_stripped(mock_slp_response):
    """Test parsing strips HTML from description."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["description"] == "Serving Madison County families"
    assert "<p>" not in loc["description"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None (validator handles geocoding)."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    item = {
        "id": "999",
        "name": "No Coords Pantry",
        "address": "123 Main St",
        "address2": "",
        "city": "Huntsville",
        "state": "AL",
        "zip": "35801",
        "phone": "",
        "lat": None,
        "lng": None,
        "hours": "",
        "url": "",
        "email": "",
        "description": "",
        "tags": "",
    }
    loc = scraper._parse_location(item)
    assert loc["latitude"] is None
    assert loc["longitude"] is None


@pytest.mark.asyncio
async def test_parse_location_uses_store_field_fallback():
    """Test parsing falls back to 'store' field if 'name' is empty."""
    scraper = FoodBankOfNorthAlabamaAlScraper()

    item = {
        "id": "888",
        "name": "",
        "store": "Fallback Name Pantry",
        "address": "456 Oak Ave",
        "address2": "",
        "city": "Huntsville",
        "state": "AL",
        "zip": "35801",
        "phone": "",
        "lat": "34.7304",
        "lng": "-86.5861",
        "hours": "",
        "url": "",
        "email": "",
        "description": "",
        "tags": "",
    }
    loc = scraper._parse_location(item)
    assert loc["name"] == "Fallback Name Pantry"


@pytest.mark.asyncio
async def test_scrape_deduplication(mock_slp_response):
    """Test that duplicate locations are removed by ID."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)

    # Return duplicates to verify dedup
    duplicated = mock_slp_response + mock_slp_response

    async def mock_fetch(client):
        return duplicated

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    # 6 raw items but only 3 unique IDs
    assert summary["total_locations_found"] == 6
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test that scraped locations include correct metadata."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)

    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert len(submitted) == 1
    assert submitted[0]["source"] == "food_bank_of_north_alabama_al"
    assert submitted[0]["food_bank"] == "Food Bank of North Alabama"


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_slp_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)

    async def mock_fetch(client):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "food_bank_of_north_alabama_al"
    assert summary["food_bank"] == "Food Bank of North Alabama"
    assert summary["source"] == "https://foodbanknorthal.org/find-food/"
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3


@pytest.mark.asyncio
async def test_fetch_locations_handles_dict_response():
    """Test fetch handles SLP dict response with 'response' key."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)

    mock_response = httpx.Response(
        200,
        json={"response": [{"id": "1", "name": "Test"}]},
        request=httpx.Request("POST", scraper.ajax_url),
    )

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations(client)
            assert len(result) == 1
            assert result[0]["id"] == "1"


@pytest.mark.asyncio
async def test_fetch_locations_handles_list_response():
    """Test fetch handles SLP list response (direct array)."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)

    mock_response = httpx.Response(
        200,
        json=[{"id": "1", "name": "Test"}],
        request=httpx.Request("POST", scraper.ajax_url),
    )

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations(client)
            assert len(result) == 1


@pytest.mark.asyncio
async def test_fetch_locations_handles_error():
    """Test fetch gracefully handles errors."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)

    with patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.ConnectError("Connection failed"),
    ):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations(client)
            assert result == []


@pytest.mark.asyncio
async def test_scrape_empty_response():
    """Test scrape handles empty API response gracefully."""
    scraper = FoodBankOfNorthAlabamaAlScraper(test_mode=True)

    async def mock_fetch(client):
        return []

    with patch.object(scraper, "fetch_locations", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
