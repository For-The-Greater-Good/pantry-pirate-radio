"""Tests for Southeast Texas Food Bank scraper."""

import json

import httpx
import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.southeast_texas_food_bank_tx_scraper import (
    SoutheastTexasFoodBankTxScraper,
    KNOWN_AGENCIES,
)


MOCK_WP_RESPONSE = [
    {
        "id": "201",
        "store": "Beaumont Food Pantry",
        "address": "3845 MLK Pkwy",
        "address2": "",
        "city": "Beaumont",
        "state": "TX",
        "zip": "77705",
        "phone": "409-839-1234",
        "lat": "30.0802",
        "lng": "-94.1266",
        "hours": "<p>Monday-Friday 8am-5pm</p>",
        "description": "<p>Drive-through pantry</p>",
    },
    {
        "id": "202",
        "store": "Port Arthur Community Kitchen",
        "address": "500 7th St",
        "address2": "",
        "city": "Port Arthur",
        "state": "TX",
        "zip": "77640",
        "phone": "409-982-5678",
        "lat": "29.8985",
        "lng": "-93.9399",
        "hours": "",
        "description": "<p>Hot meals served daily</p>",
    },
    {
        "id": "203",
        "store": "Orange Community Outreach",
        "address": "200 Border St",
        "address2": "Suite A",
        "city": "Orange",
        "state": "TX",
        "zip": "77630",
        "phone": "409-883-9012",
        "lat": "30.0930",
        "lng": "-93.7366",
        "hours": "",
        "description": "",
    },
]

MOCK_HTML = """
<html>
<body>
<main>
<h2>Get Help</h2>
<p><strong>Beaumont Food Pantry</strong></p>
<p>3845 MLK Pkwy, Beaumont, TX 77705</p>
<p>(409) 839-1234</p>
<p>Monday - Friday 8:00 AM - 5:00 PM</p>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SoutheastTexasFoodBankTxScraper()
    assert scraper.scraper_id == "southeast_texas_food_bank_tx"
    assert "setxfoodbank.org" in scraper.url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SoutheastTexasFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_parse_wp_location():
    """Test parsing WordPress locator response items."""
    scraper = SoutheastTexasFoodBankTxScraper()
    loc = scraper._parse_wp_location(MOCK_WP_RESPONSE[0])

    assert loc["name"] == "Beaumont Food Pantry"
    assert loc["city"] == "Beaumont"
    assert loc["state"] == "TX"
    assert loc["zip"] == "77705"
    assert loc["latitude"] == 30.0802
    assert loc["longitude"] == -94.1266
    assert "Monday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_wp_location_empty_state():
    """Test WP parsing defaults state to TX."""
    scraper = SoutheastTexasFoodBankTxScraper()
    item = {**MOCK_WP_RESPONSE[0], "state": ""}
    loc = scraper._parse_wp_location(item)
    assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_wp_location_with_address2():
    """Test WP parsing includes address2."""
    scraper = SoutheastTexasFoodBankTxScraper()
    loc = scraper._parse_wp_location(MOCK_WP_RESPONSE[2])
    assert loc["address2"] == "Suite A"


@pytest.mark.asyncio
async def test_parse_wp_location_coords_none():
    """Test WP parsing handles missing coordinates."""
    scraper = SoutheastTexasFoodBankTxScraper()
    item = {**MOCK_WP_RESPONSE[0], "lat": None, "lng": None}
    loc = scraper._parse_wp_location(item)
    assert loc["latitude"] is None
    assert loc["longitude"] is None


@pytest.mark.asyncio
async def test_parse_html_locations():
    """Test fallback HTML parsing."""
    scraper = SoutheastTexasFoodBankTxScraper()
    locations = scraper._parse_html_locations(MOCK_HTML)
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_parse_html_empty():
    """Test HTML parsing handles empty content."""
    scraper = SoutheastTexasFoodBankTxScraper()
    locations = scraper._parse_html_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_with_wpsl():
    """Test scrape workflow when WPSL is detected."""
    scraper = SoutheastTexasFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch.object(
        scraper, "_try_wpsl", new_callable=AsyncMock, return_value=MOCK_WP_RESPONSE
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "southeast_texas_food_bank_tx"
    assert summary["food_bank"] == "Southeast Texas Food Bank"
    assert summary["total_jobs_created"] == 3

    assert submitted[0]["source"] == "southeast_texas_food_bank_tx"
    assert submitted[0]["food_bank"] == "Southeast Texas Food Bank"


@pytest.mark.asyncio
async def test_scrape_falls_back_to_html():
    """Test scrape falls back to HTML when no WP plugin found."""
    scraper = SoutheastTexasFoodBankTxScraper(test_mode=True)

    with patch.object(
        scraper,
        "_try_wpsl",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch.object(
            scraper,
            "_try_slp",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch.object(
                scraper,
                "_try_asl",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch.object(
                    scraper,
                    "_fetch_html_with_retry",
                    new_callable=AsyncMock,
                    return_value=MOCK_HTML,
                ):
                    with patch.object(
                        scraper,
                        "submit_to_queue",
                        return_value="job_123",
                    ):
                        result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "southeast_texas_food_bank_tx"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = SoutheastTexasFoodBankTxScraper(test_mode=True)

    with patch.object(
        scraper, "_try_wpsl", new_callable=AsyncMock, return_value=MOCK_WP_RESPONSE
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
    scraper = SoutheastTexasFoodBankTxScraper(test_mode=True)

    duplicated = MOCK_WP_RESPONSE + MOCK_WP_RESPONSE

    with patch.object(
        scraper,
        "_try_wpsl",
        new_callable=AsyncMock,
        return_value=duplicated,
    ):
        with patch.object(
            scraper, "submit_to_queue", return_value="job_123"
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_locations_found"] == 3


@pytest.mark.asyncio
async def test_scrape_fallback_to_known_agencies():
    """Test fallback to known agencies when all methods fail."""
    scraper = SoutheastTexasFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch.object(
        scraper,
        "_try_wpsl",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch.object(
            scraper,
            "_try_slp",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch.object(
                scraper,
                "_try_asl",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch.object(
                    scraper,
                    "_fetch_html_with_retry",
                    new_callable=AsyncMock,
                    side_effect=httpx.HTTPStatusError(
                        "403 Forbidden",
                        request=httpx.Request(
                            "GET", scraper.url
                        ),
                        response=httpx.Response(403),
                    ),
                ):
                    with patch.object(
                        scraper,
                        "submit_to_queue",
                        side_effect=capture,
                    ):
                        result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == len(KNOWN_AGENCIES)
    assert (
        submitted[0]["source"]
        == "southeast_texas_food_bank_tx"
    )
    assert (
        submitted[0]["food_bank"]
        == "Southeast Texas Food Bank"
    )
