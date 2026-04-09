"""Tests for South Texas Food Bank scraper."""

import json

import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.south_texas_food_bank_tx_scraper import (
    SouthTexasFoodBankTxScraper,
)


MOCK_HTML = """
<html>
<body>
<main>
<article class="entry-content">
<h2>Webb County</h2>
<table>
<tr><th>Agency</th><th>Address</th><th>Phone</th><th>Hours</th></tr>
<tr>
<td>Bethany House of Laredo</td>
<td>2610 Salinas Ave, Laredo, TX 78040</td>
<td>(956) 726-1234</td>
<td>Monday 9:00 AM - 12:00 PM</td>
</tr>
<tr>
<td>Sacred Heart Church</td>
<td>1801 San Francisco Ave, Laredo, TX 78040</td>
<td>(956) 722-5678</td>
<td>Wednesday and Friday 10:00 AM - 2:00 PM</td>
</tr>
</table>

<h2>Val Verde County</h2>
<table>
<tr><th>Agency</th><th>Address</th><th>Phone</th><th>Hours</th></tr>
<tr>
<td>Del Rio Community Pantry</td>
<td>300 E Garfield St, Del Rio, TX 78840</td>
<td>(830) 775-9012</td>
<td>Tuesday and Thursday 1:00 PM - 4:00 PM</td>
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
    scraper = SouthTexasFoodBankTxScraper()
    assert scraper.scraper_id == "south_texas_food_bank_tx"
    assert scraper.url == "https://www.southtexasfoodbank.org/agencies"
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SouthTexasFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_locations_from_tables():
    """Test parsing locations from HTML tables."""
    scraper = SouthTexasFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    assert len(locations) >= 3
    names = [loc["name"] for loc in locations]
    assert "Bethany House of Laredo" in names
    assert "Sacred Heart Church" in names
    assert "Del Rio Community Pantry" in names


@pytest.mark.asyncio
async def test_parse_locations_extracts_addresses():
    """Test that addresses are extracted from table cells."""
    scraper = SouthTexasFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    by_name = {loc["name"]: loc for loc in locations}
    bethany = by_name.get("Bethany House of Laredo", {})
    assert "Salinas" in bethany.get("address", "")


@pytest.mark.asyncio
async def test_parse_locations_extracts_phones():
    """Test that phone numbers are extracted from table cells."""
    scraper = SouthTexasFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("956" in p for p in phones)


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX."""
    scraper = SouthTexasFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_extracts_zip():
    """Test that zip codes are extracted from addresses."""
    scraper = SouthTexasFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    zips = [loc.get("zip", "") for loc in locations]
    assert "78040" in zips or any("78040" in z for z in zips)


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty HTML gracefully."""
    scraper = SouthTexasFoodBankTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = SouthTexasFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch.object(
        scraper, "_fetch_page", new_callable=AsyncMock, return_value=MOCK_HTML
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "south_texas_food_bank_tx"
    assert summary["food_bank"] == "South Texas Food Bank"

    assert len(submitted) >= 3
    assert submitted[0]["source"] == "south_texas_food_bank_tx"
    assert submitted[0]["food_bank"] == "South Texas Food Bank"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = SouthTexasFoodBankTxScraper(test_mode=True)

    with patch.object(
        scraper, "_fetch_page", new_callable=AsyncMock, return_value=MOCK_HTML
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "total_jobs_created" in summary
    assert "source" in summary
