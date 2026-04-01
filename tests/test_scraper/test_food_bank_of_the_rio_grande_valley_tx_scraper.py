"""Tests for Food Bank of the Rio Grande Valley scraper."""

import json
import pytest
from unittest.mock import patch

from app.scraper.scrapers.food_bank_of_the_rio_grande_valley_tx_scraper import (
    FoodBankOfTheRioGrandeValleyTxScraper,
)


@pytest.fixture
def mock_slp_response():
    """Mock SLP (Store Locator Plus) API response."""
    return [
        {
            "id": "101",
            "name": "Sacred Heart Church Pantry",
            "address": "300 S Texas Blvd",
            "address2": "",
            "city": "Weslaco",
            "state": "TX",
            "zip": "78596",
            "phone": "956-968-3434",
            "lat": "26.1592",
            "lng": "-97.9908",
            "hours": "",
            "url": "",
            "email": "",
            "description": "<p>2nd &amp; 4th Wednesday<br />9:00 AM - 11:00 AM</p>",
            "tags": "pantry",
            "distance": "0.5",
        },
        {
            "id": "102",
            "name": "Community Food Bank - McAllen",
            "address": "1800 S Main St",
            "address2": "Suite B",
            "city": "McAllen",
            "state": "",
            "zip": "78501",
            "phone": "",
            "lat": "26.1884",
            "lng": "-98.2300",
            "hours": '<table class="slp-hours"><tr><td>Monday</td><td>8am-12pm</td></tr></table>',
            "url": "https://mcallenfoodbank.org",
            "email": "info@mcallenfoodbank.org",
            "description": "<p>Walk-in welcome, bring ID</p>",
            "tags": "<a>food pantry</a>, <a>distribution</a>",
            "distance": "1.2",
        },
        {
            "id": "103",
            "name": "Brownsville Helping Hands",
            "address": "450 E Levee St",
            "address2": "",
            "city": "Brownsville",
            "state": "TX",
            "zip": "78520",
            "phone": "956-541-1234",
            "lat": "25.9017",
            "lng": "-97.4975",
            "hours": "",
            "url": "",
            "email": "",
            "description": "<p>Every Friday 10:00 AM - 2:00 PM</p>",
            "tags": "",
            "distance": "3.0",
        },
    ]


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()
    assert scraper.scraper_id == "food_bank_of_the_rio_grande_valley_tx"
    assert "foodbankrgv.com" in scraper.ajax_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_generate_grid_points():
    """Test grid generation covers Rio Grande Valley area."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()
    points = scraper._generate_grid_points()
    assert len(points) > 50
    # Verify points are in Rio Grande Valley area
    for lat, lng in points:
        assert 25.8 <= lat <= 26.8
        assert -98.5 <= lng <= -97.1


@pytest.mark.asyncio
async def test_parse_location(mock_slp_response):
    """Test parsing raw SLP response items."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    loc = scraper._parse_location(mock_slp_response[0])
    assert loc["name"] == "Sacred Heart Church Pantry"
    assert loc["city"] == "Weslaco"
    assert loc["state"] == "TX"
    assert loc["latitude"] == 26.1592
    assert loc["longitude"] == -97.9908
    assert "Wednesday" in loc["description"]


@pytest.mark.asyncio
async def test_parse_location_empty_state(mock_slp_response):
    """Test parsing handles empty state field."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["state"] == "TX"  # Defaults to TX


@pytest.mark.asyncio
async def test_parse_location_with_address2(mock_slp_response):
    """Test parsing includes address2 in full_address."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert "Suite B" in loc["full_address"]


@pytest.mark.asyncio
async def test_parse_location_hours_table(mock_slp_response):
    """Test parsing extracts text from HTML hours table."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert "Monday" in loc["hours"]
    assert "8am-12pm" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_location_email(mock_slp_response):
    """Test parsing extracts email field."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["email"] == "info@mcallenfoodbank.org"


@pytest.mark.asyncio
async def test_parse_location_url(mock_slp_response):
    """Test parsing extracts URL field."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert loc["url"] == "https://mcallenfoodbank.org"


@pytest.mark.asyncio
async def test_parse_location_tags(mock_slp_response):
    """Test parsing extracts and cleans tags."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    loc = scraper._parse_location(mock_slp_response[1])
    assert "food pantry" in loc["tags"]
    assert "distribution" in loc["tags"]


@pytest.mark.asyncio
async def test_parse_location_coordinates_can_be_none():
    """Test that coordinates can be None (validator handles geocoding)."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    item = {
        "id": "999",
        "name": "No Coords Pantry",
        "address": "123 Main St",
        "address2": "",
        "city": "McAllen",
        "state": "TX",
        "zip": "78501",
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
    scraper = FoodBankOfTheRioGrandeValleyTxScraper()

    item = {
        "id": "888",
        "name": "",
        "store": "Fallback Name Pantry",
        "address": "456 Oak Ave",
        "address2": "",
        "city": "Harlingen",
        "state": "TX",
        "zip": "78550",
        "phone": "",
        "lat": "26.1906",
        "lng": "-97.6961",
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
    """Test that duplicate locations from overlapping grid cells are removed."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    # Even though we query 3 grid points (test_mode), each returning 3 items,
    # dedup by ID means we only get 3 unique locations
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3


@pytest.mark.asyncio
async def test_scrape_metadata(mock_slp_response):
    """Test that scraped locations include correct metadata."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper(test_mode=True)

    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client, lat, lng):
        return mock_slp_response[:1]

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    assert len(submitted) >= 1
    assert submitted[0]["source"] == "food_bank_of_the_rio_grande_valley_tx"
    assert submitted[0]["food_bank"] == "Food Bank of the Rio Grande Valley"


@pytest.mark.asyncio
async def test_scrape_full_workflow(mock_slp_response):
    """Test complete scrape workflow returns valid summary."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper(test_mode=True)

    async def mock_fetch(client, lat, lng):
        return mock_slp_response

    with patch.object(scraper, "fetch_locations_for_point", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "food_bank_of_the_rio_grande_valley_tx"
    assert summary["food_bank"] == "Food Bank of the Rio Grande Valley"
    assert summary["source"] == "https://foodbankrgv.com/find-food/"


@pytest.mark.asyncio
async def test_fetch_locations_handles_dict_response():
    """Test fetch handles SLP dict response with 'response' key."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper(test_mode=True)

    import httpx

    mock_response = httpx.Response(
        200,
        json={"response": [{"id": "1", "name": "Test"}]},
        request=httpx.Request("POST", scraper.ajax_url),
    )

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations_for_point(client, 26.0, -98.0)
            assert len(result) == 1
            assert result[0]["id"] == "1"


@pytest.mark.asyncio
async def test_fetch_locations_handles_list_response():
    """Test fetch handles SLP list response (direct array)."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper(test_mode=True)

    import httpx

    mock_response = httpx.Response(
        200,
        json=[{"id": "1", "name": "Test"}],
        request=httpx.Request("POST", scraper.ajax_url),
    )

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations_for_point(client, 26.0, -98.0)
            assert len(result) == 1


@pytest.mark.asyncio
async def test_fetch_locations_handles_error():
    """Test fetch gracefully handles errors."""
    scraper = FoodBankOfTheRioGrandeValleyTxScraper(test_mode=True)

    import httpx

    with patch(
        "httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection failed")
    ):
        async with httpx.AsyncClient() as client:
            result = await scraper.fetch_locations_for_point(client, 26.0, -98.0)
            assert result == []
