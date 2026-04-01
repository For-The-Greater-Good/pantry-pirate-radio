"""Tests for Galveston County Food Bank scraper."""

import json

import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.galveston_county_food_bank_tx_scraper import (
    GalvestonCountyFoodBankTxScraper,
)


MOCK_HOMEPAGE = """
<html>
<body>
<nav>
<a href="/find-food/">Find Food</a>
<a href="/about/">About</a>
<a href="/donate/">Donate</a>
</nav>
<main>
<h1>Galveston County Food Bank</h1>
<p>Serving Galveston County since 1985</p>
</main>
</body>
</html>
"""

MOCK_FOOD_PAGE = """
<html>
<body>
<main>
<h2>Partner Agencies</h2>
<table>
<tr><th>Agency</th><th>Address</th><th>Phone</th><th>Hours</th></tr>
<tr>
<td>Island Community Center</td>
<td>4700 Broadway, Galveston, TX 77551</td>
<td>(409) 762-1234</td>
<td>Monday and Wednesday 10:00 AM - 2:00 PM</td>
</tr>
<tr>
<td>Texas City Food Pantry</td>
<td>2005 9th Ave N, Texas City, TX 77590</td>
<td>(409) 945-5678</td>
<td>Tuesday and Thursday 9:00 AM - 12:00 PM</td>
</tr>
<tr>
<td>Dickinson Community Church</td>
<td>300 FM 517 Rd E, Dickinson, TX 77539</td>
<td>(281) 337-9012</td>
<td>Friday 1:00 PM - 3:00 PM</td>
</tr>
</table>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = GalvestonCountyFoodBankTxScraper()
    assert scraper.scraper_id == "galveston_county_food_bank_tx"
    assert "galvestoncountyfoodbank.org" in scraper.base_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = GalvestonCountyFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_find_agency_page_url():
    """Test finding the food/agency page URL from homepage."""
    scraper = GalvestonCountyFoodBankTxScraper()
    url = scraper._find_agency_page_url(MOCK_HOMEPAGE)
    assert url is not None
    assert "find-food" in url


@pytest.mark.asyncio
async def test_find_agency_page_url_returns_none():
    """Test returns None when no agency page link found."""
    scraper = GalvestonCountyFoodBankTxScraper()
    url = scraper._find_agency_page_url(
        "<html><body><a href='/about/'>About</a></body></html>"
    )
    assert url is None


@pytest.mark.asyncio
async def test_parse_locations_from_tables():
    """Test parsing locations from HTML tables."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    assert len(locations) >= 3
    names = [loc["name"] for loc in locations]
    assert "Island Community Center" in names
    assert "Texas City Food Pantry" in names


@pytest.mark.asyncio
async def test_parse_locations_extracts_phones():
    """Test that phone numbers are extracted."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("409" in p for p in phones)


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty HTML gracefully."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = GalvestonCountyFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client, url):
        if "find-food" in url:
            return MOCK_FOOD_PAGE
        return MOCK_HOMEPAGE

    with patch.object(scraper, "_fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "galveston_county_food_bank_tx"
    assert summary["food_bank"] == "Galveston County Food Bank"

    if submitted:
        assert submitted[0]["source"] == "galveston_county_food_bank_tx"
        assert submitted[0]["food_bank"] == "Galveston County Food Bank"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = GalvestonCountyFoodBankTxScraper(test_mode=True)

    async def mock_fetch(client, url):
        return MOCK_FOOD_PAGE

    with patch.object(scraper, "_fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "total_jobs_created" in summary
