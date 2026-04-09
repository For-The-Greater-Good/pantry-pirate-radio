"""Tests for Food Bank of West Central Texas scraper."""

import json

import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.food_bank_of_west_central_texas_tx_scraper import (
    FoodBankOfWestCentralTexasTxScraper,
)


MOCK_WP_RESPONSE = [
    {
        "id": "301",
        "store": "Abilene Food Pantry",
        "address": "5505 N First St",
        "city": "Abilene",
        "state": "TX",
        "zip": "79603",
        "phone": "325-695-1234",
        "lat": "32.4800",
        "lng": "-99.7400",
        "hours": "<p>Monday-Friday 9am-3pm</p>",
        "description": "<p>Food pantry</p>",
    },
    {
        "id": "302",
        "store": "Brownwood Mission",
        "address": "100 W Commerce St",
        "city": "Brownwood",
        "state": "TX",
        "zip": "76801",
        "phone": "325-646-5678",
        "lat": "31.7128",
        "lng": "-98.9912",
        "hours": "",
        "description": "<p>Wednesday 10am-2pm</p>",
    },
    {
        "id": "303",
        "store": "Coleman County Outreach",
        "address": "200 W Pecan St",
        "city": "Coleman",
        "state": "TX",
        "zip": "76834",
        "phone": "325-625-9012",
        "lat": "31.8274",
        "lng": "-99.4267",
        "hours": "",
        "description": "",
    },
]

MOCK_HTML_SCHEDULE = """
<html>
<body>
<main>
<article class="entry-content">
<h2>Food Pantries</h2>
<table>
<tr><th>Site</th><th>Address</th><th>Phone</th><th>Day/Time</th></tr>
<tr>
<td>Abilene Salvation Army</td>
<td>1726 Butternut St, Abilene, TX 79602</td>
<td>(325) 677-1408</td>
<td>Tuesday and Thursday 9:00 AM - 12:00 PM</td>
</tr>
<tr>
<td>Eastland County Pantry</td>
<td>201 W Main St, Eastland, TX 76448</td>
<td>(254) 629-1234</td>
<td>Wednesday 10:00 AM - 1:00 PM</td>
</tr>
</table>

<h2>Meal Sites</h2>
<table>
<tr><th>Site</th><th>Address</th><th>Phone</th><th>Day/Time</th></tr>
<tr>
<td>Love and Care Ministries</td>
<td>1150 E South 11th St, Abilene, TX 79602</td>
<td>(325) 672-1234</td>
<td>Monday - Saturday 11:30 AM - 12:30 PM</td>
</tr>
</table>
</article>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    assert scraper.scraper_id == "food_bank_of_west_central_texas_tx"
    assert "fbwct.org" in scraper.url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = FoodBankOfWestCentralTexasTxScraper(test_mode=True)
    assert scraper.test_mode is True
    assert scraper.request_delay == 0.05


@pytest.mark.asyncio
async def test_parse_wp_location():
    """Test parsing WordPress locator response items."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    loc = scraper._parse_wp_location(MOCK_WP_RESPONSE[0])

    assert loc["name"] == "Abilene Food Pantry"
    assert loc["city"] == "Abilene"
    assert loc["state"] == "TX"
    assert loc["zip"] == "79603"
    assert loc["latitude"] == 32.48
    assert loc["longitude"] == -99.74
    assert "Monday" in loc["hours"]


@pytest.mark.asyncio
async def test_parse_wp_location_empty_state():
    """Test WP parsing defaults state to TX."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    item = {**MOCK_WP_RESPONSE[0], "state": ""}
    loc = scraper._parse_wp_location(item)
    assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_html_locations_from_tables():
    """Test parsing locations from HTML schedule tables."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    locations = scraper._parse_html_locations(MOCK_HTML_SCHEDULE)

    assert len(locations) >= 3
    names = [loc["name"] for loc in locations]
    assert "Abilene Salvation Army" in names
    assert "Eastland County Pantry" in names
    assert "Love and Care Ministries" in names


@pytest.mark.asyncio
async def test_parse_html_extracts_phones():
    """Test that phone numbers are extracted from tables."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    locations = scraper._parse_html_locations(MOCK_HTML_SCHEDULE)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("325" in p for p in phones)


@pytest.mark.asyncio
async def test_parse_html_extracts_hours():
    """Test that hours are extracted from tables."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    locations = scraper._parse_html_locations(MOCK_HTML_SCHEDULE)

    by_name = {loc["name"]: loc for loc in locations}
    salvation = by_name.get("Abilene Salvation Army", {})
    assert "Tuesday" in salvation.get("hours", "")


@pytest.mark.asyncio
async def test_parse_html_sets_state():
    """Test that state defaults to TX."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    locations = scraper._parse_html_locations(MOCK_HTML_SCHEDULE)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_html_empty():
    """Test HTML parsing handles empty content."""
    scraper = FoodBankOfWestCentralTexasTxScraper()
    locations = scraper._parse_html_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_with_wpsl():
    """Test scrape workflow when WPSL plugin is detected."""
    scraper = FoodBankOfWestCentralTexasTxScraper(test_mode=True)
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
    assert summary["scraper_id"] == "food_bank_of_west_central_texas_tx"
    assert summary["food_bank"] == "Food Bank of West Central Texas"
    assert summary["total_jobs_created"] == 3

    assert submitted[0]["source"] == "food_bank_of_west_central_texas_tx"
    assert submitted[0]["food_bank"] == "Food Bank of West Central Texas"


@pytest.mark.asyncio
async def test_scrape_falls_back_to_html():
    """Test scrape falls back to HTML parsing."""
    scraper = FoodBankOfWestCentralTexasTxScraper(test_mode=True)

    mock_response = AsyncMock()
    mock_response.text = MOCK_HTML_SCHEDULE
    mock_response.raise_for_status = lambda: None

    with patch.object(scraper, "_try_wpsl", new_callable=AsyncMock, return_value=None):
        with patch.object(
            scraper, "_try_slp", new_callable=AsyncMock, return_value=None
        ):
            with patch("httpx.AsyncClient.get", return_value=mock_response):
                with patch.object(scraper, "submit_to_queue", return_value="job_123"):
                    result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "food_bank_of_west_central_texas_tx"
    assert summary["total_locations_found"] >= 3


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = FoodBankOfWestCentralTexasTxScraper(test_mode=True)

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
    scraper = FoodBankOfWestCentralTexasTxScraper(test_mode=True)

    duplicated = MOCK_WP_RESPONSE + MOCK_WP_RESPONSE

    with patch.object(
        scraper, "_try_wpsl", new_callable=AsyncMock, return_value=duplicated
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_locations_found"] == 3
