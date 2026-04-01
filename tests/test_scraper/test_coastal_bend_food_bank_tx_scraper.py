"""Tests for Coastal Bend Food Bank scraper."""

import json

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import httpx

from app.scraper.scrapers.coastal_bend_food_bank_tx_scraper import (
    CoastalBendFoodBankTxScraper,
)


MOCK_WPSL_RESPONSE = [
    {
        "id": "101",
        "store": "Corpus Christi Food Pantry",
        "address": "1234 Leopard St",
        "address2": "",
        "city": "Corpus Christi",
        "state": "TX",
        "zip": "78401",
        "phone": "361-887-1234",
        "lat": "27.8006",
        "lng": "-97.3964",
        "hours": "<p>Monday-Friday 9am-4pm</p>",
        "description": "<p>Walk-in welcome</p>",
    },
    {
        "id": "102",
        "store": "Kingsville Community Center",
        "address": "500 E King Ave",
        "address2": "",
        "city": "Kingsville",
        "state": "TX",
        "zip": "78363",
        "phone": "361-592-5678",
        "lat": "27.5159",
        "lng": "-97.8561",
        "hours": "",
        "description": "<p>Tuesday and Thursday</p>",
    },
    {
        "id": "103",
        "store": "Alice Food Bank",
        "address": "300 N Texas Blvd",
        "address2": "",
        "city": "Alice",
        "state": "TX",
        "zip": "78332",
        "phone": "361-664-9012",
        "lat": "27.7522",
        "lng": "-98.0697",
        "hours": "",
        "description": "",
    },
]

MOCK_HTML = """
<html>
<body>
<main>
<h2>Partner Agencies</h2>
<p><strong>Corpus Christi Mission</strong></p>
<p>1234 Leopard St, Corpus Christi, TX 78401</p>
<p>361-887-1234</p>
<p>Monday through Friday 9:00 AM - 4:00 PM</p>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = CoastalBendFoodBankTxScraper()
    assert scraper.scraper_id == "coastal_bend_food_bank_tx"
    assert "coastalbendfoodbank.org" in scraper.url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = CoastalBendFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_parse_wpsl_location():
    """Test parsing WPSL API response items."""
    scraper = CoastalBendFoodBankTxScraper()
    loc = scraper._parse_wpsl_location(MOCK_WPSL_RESPONSE[0])

    assert loc["name"] == "Corpus Christi Food Pantry"
    assert loc["city"] == "Corpus Christi"
    assert loc["state"] == "TX"
    assert loc["zip"] == "78401"
    assert loc["latitude"] == 27.8006
    assert loc["longitude"] == -97.3964
    assert "Monday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_wpsl_location_empty_state_defaults():
    """Test WPSL parsing defaults state to TX."""
    scraper = CoastalBendFoodBankTxScraper()
    item = {**MOCK_WPSL_RESPONSE[0], "state": ""}
    loc = scraper._parse_wpsl_location(item)
    assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_slp_location():
    """Test parsing SLP API response items."""
    scraper = CoastalBendFoodBankTxScraper()
    item = {
        "id": "1",
        "name": "Test Pantry",
        "address": "123 Main St",
        "city": "Corpus Christi",
        "state": "TX",
        "zip": "78401",
        "phone": "361-555-0000",
        "lat": "27.8",
        "lng": "-97.4",
        "hours": "",
        "description": "",
    }
    loc = scraper._parse_slp_location(item)
    assert loc["name"] == "Test Pantry"
    assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_asl_location():
    """Test parsing ASL API response items."""
    scraper = CoastalBendFoodBankTxScraper()
    item = {
        "title": "ASL Pantry",
        "street": "456 Oak St",
        "city": "Alice",
        "state": "TX",
        "postal_code": "78332",
        "phone": "361-555-1111",
        "lat": "27.75",
        "lng": "-98.07",
        "description": "Food pantry",
        "description_2": "Mon-Fri 9am-5pm",
    }
    loc = scraper._parse_asl_location(item)
    assert loc["name"] == "ASL Pantry"
    assert loc["hours"] == "Mon-Fri 9am-5pm"


@pytest.mark.asyncio
async def test_parse_html_locations():
    """Test fallback HTML parsing."""
    scraper = CoastalBendFoodBankTxScraper()
    locations = scraper._parse_html_locations(MOCK_HTML)
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_parse_html_empty():
    """Test HTML parsing handles empty content."""
    scraper = CoastalBendFoodBankTxScraper()
    locations = scraper._parse_html_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_with_wpsl():
    """Test scrape workflow when WPSL plugin is detected."""
    scraper = CoastalBendFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch.object(
        scraper, "_try_wpsl", new_callable=AsyncMock, return_value=MOCK_WPSL_RESPONSE
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "coastal_bend_food_bank_tx"
    assert summary["food_bank"] == "Coastal Bend Food Bank"
    assert summary["total_jobs_created"] == 3

    assert len(submitted) == 3
    assert submitted[0]["source"] == "coastal_bend_food_bank_tx"
    assert submitted[0]["food_bank"] == "Coastal Bend Food Bank"


@pytest.mark.asyncio
async def test_scrape_falls_back_to_html():
    """Test scrape falls back to HTML when no WP plugin found."""
    scraper = CoastalBendFoodBankTxScraper(test_mode=True)

    with patch.object(scraper, "_try_wpsl", new_callable=AsyncMock, return_value=None):
        with patch.object(
            scraper, "_try_slp", new_callable=AsyncMock, return_value=None
        ):
            with patch.object(
                scraper, "_try_asl", new_callable=AsyncMock, return_value=None
            ):
                with patch.object(
                    scraper,
                    "_fetch_html",
                    new_callable=AsyncMock,
                    return_value=MOCK_HTML,
                ):
                    with patch.object(
                        scraper, "submit_to_queue", return_value="job_123"
                    ):
                        result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "coastal_bend_food_bank_tx"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = CoastalBendFoodBankTxScraper(test_mode=True)

    with patch.object(
        scraper, "_try_wpsl", new_callable=AsyncMock, return_value=MOCK_WPSL_RESPONSE
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "total_jobs_created" in summary
    assert "source" in summary


@pytest.mark.asyncio
async def test_deduplication():
    """Test that duplicate locations are deduplicated."""
    scraper = CoastalBendFoodBankTxScraper(test_mode=True)

    duplicated = MOCK_WPSL_RESPONSE + MOCK_WPSL_RESPONSE  # Double the data

    with patch.object(
        scraper, "_try_wpsl", new_callable=AsyncMock, return_value=duplicated
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    # Should deduplicate to 3 unique locations
    assert summary["total_locations_found"] == 3
