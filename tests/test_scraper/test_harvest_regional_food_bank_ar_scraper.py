"""Tests for Harvest Regional Food Bank scraper."""

import json
from unittest.mock import patch, AsyncMock

import httpx
import pytest

from app.scraper.scrapers.harvest_regional_food_bank_ar_scraper import (
    HarvestRegionalFoodBankArScraper,
    FOOD_BANK_NAME,
)


MOCK_HTML = """
<html><body>
<table>
<tr><th>Agency</th><th>Address</th><th>City</th><th>Phone</th><th>Hours</th></tr>
<tr><td>Texarkana Food Pantry</td><td>100 Main St</td><td>Texarkana</td><td>870-555-1234</td><td>Mon-Fri 9am-3pm</td></tr>
<tr><td>Hope Community Kitchen</td><td>200 Elm St</td><td>Hope</td><td>870-555-5678</td><td>Tue 10am-1pm</td></tr>
<tr><td>Nashville Food Bank</td><td>300 Oak Ave</td><td>Nashville</td><td></td><td>Wed 9am-12pm</td></tr>
</table>
</body></html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = HarvestRegionalFoodBankArScraper()
    assert scraper.scraper_id == "harvest_regional_food_bank_ar"
    assert "harvestregionalfoodbank.org" in scraper.base_url


@pytest.mark.asyncio
async def test_parse_locations_from_table():
    """Test parsing agency locations from HTML table."""
    scraper = HarvestRegionalFoodBankArScraper()
    locations = scraper._parse_locations(MOCK_HTML)
    assert len(locations) == 3
    assert locations[0]["name"] == "Texarkana Food Pantry"
    assert locations[0]["address"] == "100 Main St"
    assert locations[0]["city"] == "Texarkana"
    assert locations[0]["phone"] == "870-555-1234"
    assert locations[0]["state"] == "AR"


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing returns empty list for empty HTML."""
    scraper = HarvestRegionalFoodBankArScraper()
    locations = scraper._parse_locations(
        "<html><body></body></html>"
    )
    assert locations == []


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test scraped locations include correct metadata."""
    scraper = HarvestRegionalFoodBankArScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    async def mock_fetch(client, url):
        return MOCK_HTML

    with patch.object(
        scraper, "_fetch_page", side_effect=mock_fetch
    ):
        with patch.object(
            scraper, "submit_to_queue", side_effect=capture
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "harvest_regional_food_bank_ar"
    assert len(submitted) == 3
    assert submitted[0]["source"] == "harvest_regional_food_bank_ar"
    assert submitted[0]["food_bank"] == FOOD_BANK_NAME


@pytest.mark.asyncio
async def test_scrape_with_browser_fallback():
    """Test scrape uses browser fallback and parses locations."""
    scraper = HarvestRegionalFoodBankArScraper(test_mode=True)
    submitted = []

    def capture(data):
        submitted.append(json.loads(data))
        return "j"

    with patch(
        "app.scraper.scrapers.harvest_regional_food_bank_ar_scraper.fetch_with_browser_fallback",
        new_callable=AsyncMock,
        return_value=MOCK_HTML,
    ):
        with patch.object(
            scraper, "submit_to_queue", side_effect=capture
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 3
    assert submitted[0]["source"] == "harvest_regional_food_bank_ar"
    assert submitted[0]["food_bank"] == FOOD_BANK_NAME


@pytest.mark.asyncio
async def test_scrape_empty_when_all_fail():
    """Test scrape returns zero jobs when browser fallback fails."""
    scraper = HarvestRegionalFoodBankArScraper(test_mode=True)

    async def mock_fetch_none(client, url):
        return None

    with patch.object(
        scraper, "_fetch_page", side_effect=mock_fetch_none
    ):
        with patch.object(
            scraper, "submit_to_queue", return_value="j"
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0


@pytest.mark.asyncio
async def test_scrape_deduplication():
    """Test duplicate locations are deduplicated by name."""
    scraper = HarvestRegionalFoodBankArScraper(test_mode=True)

    dupe_html = """
    <html><body><table>
    <tr><th>Agency</th><th>Address</th></tr>
    <tr><td>Same Pantry</td><td>100 Main St</td></tr>
    <tr><td>Same Pantry</td><td>100 Main St</td></tr>
    </table></body></html>
    """

    async def mock_fetch(client, url):
        return dupe_html

    with patch.object(
        scraper, "_fetch_page", side_effect=mock_fetch
    ):
        with patch.object(
            scraper, "submit_to_queue", return_value="j"
        ):
            result = await scraper.scrape()

    assert json.loads(result)["unique_locations"] == 1
