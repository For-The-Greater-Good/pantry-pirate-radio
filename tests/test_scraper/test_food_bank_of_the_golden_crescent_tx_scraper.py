"""Tests for Food Bank of the Golden Crescent scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper import (
    FoodBankOfTheGoldenCrescentTxScraper,
)

# Mock HTML matching the real Wix-rendered food-assistance page structure.
# The real page lists agencies grouped under county headers with the
# pattern: COUNTY HEADER -> Agency Name -> Address (TX) -> Phone -> Hours.
MOCK_HTML = """
<html>
<body>
<main>
<div>
<p>CALHOUN COUNTY</p>
<p>Bayside Community Church Food Pantry</p>
<p>25080 Hwy 172, Olivia, TX</p>
<p>Hours: 2nd Thursday of each month, 4:00-6:00pm</p>

<p>Calhoun County Community Ministries</p>
<p>331 Alcoa Drive, Port Lavaca, TX</p>
<p>361-552-1722</p>
<p>Hours: Monday-Friday, 9:00am-12:00pm</p>

<p>VICTORIA COUNTY</p>
<p>Christ's Kitchen Soup Kitchen</p>
<p>611 E. Warren, Victoria, TX</p>
<p>361-578-4233</p>
<p>Hours: Monday-Friday, 10:30am-1:00pm</p>

<p>City Harvest Food Pantry</p>
<p>2802 Lone Tree Road, Victoria, TX</p>
<p>361-576-9966</p>
<p>Hours: 1st Tuesday of each month 1:00-3:00pm</p>

<p>Dorothy's Hope Kitchen &amp; Pantry</p>
<p>12657 State Hwy 185, Bloomington, TX 77951</p>
<p>Pantry: Monday, Wednesday, Friday 2:00 - 4:00pm</p>
</div>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    assert scraper.scraper_id == "food_bank_of_the_golden_crescent_tx"
    assert scraper.url == "https://www.tfbgc.org/food-assistance"
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_locations():
    """Test parsing locations from HTML content."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    assert len(locations) >= 4
    names = [loc["name"] for loc in locations]
    assert "Bayside Community Church Food Pantry" in names
    assert "Calhoun County Community Ministries" in names
    assert "Christ's Kitchen Soup Kitchen" in names
    assert "City Harvest Food Pantry" in names


@pytest.mark.asyncio
async def test_parse_locations_extracts_phone():
    """Test that phone numbers are extracted from parsed locations."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("361" in phone for phone in phones)


@pytest.mark.asyncio
async def test_parse_locations_extracts_hours():
    """Test that hours are extracted from parsed locations."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    hours_list = [loc.get("hours", "") for loc in locations]
    assert any("Monday" in h for h in hours_list)


@pytest.mark.asyncio
async def test_parse_locations_extracts_county():
    """Test that county is captured for each location."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    counties = [loc.get("county", "") for loc in locations]
    assert "CALHOUN" in counties
    assert "VICTORIA" in counties


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX for all locations."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_extracts_zip():
    """Test that zip codes are extracted when present."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    # Dorothy's Hope has zip 77951
    zips = [loc.get("zip", "") for loc in locations]
    assert "77951" in zips


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty or minimal HTML gracefully."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)
    assert len(locations) == 0


@pytest.mark.asyncio
async def test_parse_locations_deduplicates():
    """Test that duplicate locations are deduplicated."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    dup_html = """
    <html><body><main>
    <p>VICTORIA COUNTY</p>
    <p>Test Pantry</p>
    <p>100 Main St, Victoria, TX</p>
    <p>Test Pantry</p>
    <p>100 Main St, Victoria, TX</p>
    </main></body></html>
    """
    locations = scraper._parse_locations(dup_html)
    assert len(locations) == 1


@pytest.mark.asyncio
async def test_scrape_with_browser():
    """Test scraper uses browser rendering and parses results."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper"
        ".fetch_html_with_browser",
        return_value=MOCK_HTML,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 4
    assert submitted[0]["source"] == "food_bank_of_the_golden_crescent_tx"
    assert submitted[0]["food_bank"] == "Food Bank of the Golden Crescent"


@pytest.mark.asyncio
async def test_scrape_handles_none_response():
    """Test scraper handles None from browser gracefully."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper"
        ".fetch_html_with_browser",
        return_value=None,
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper"
        ".fetch_html_with_browser",
        return_value=MOCK_HTML,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "food_bank_of_the_golden_crescent_tx"
    assert summary["food_bank"] == "Food Bank of the Golden Crescent"

    if submitted:
        assert submitted[0]["source"] == "food_bank_of_the_golden_crescent_tx"
        assert submitted[0]["food_bank"] == "Food Bank of the Golden Crescent"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper(test_mode=True)

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper"
        ".fetch_html_with_browser",
        return_value=MOCK_HTML,
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
async def test_scrape_test_mode_limits_results():
    """Test that test mode limits the number of locations submitted."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper(test_mode=True)

    # Create HTML with many locations to trigger limit
    many_html = "<html><body><main>\n<p>VICTORIA COUNTY</p>\n"
    for i in range(10):
        many_html += f"""
        <p>Pantry {i}</p>
        <p>{100 + i} Main St, City, TX {77900 + i}</p>
        <p>361-555-{1000 + i}</p>
        <p>Hours: Tuesday 9:00am-12:00pm</p>
        """
    many_html += "</main></body></html>"

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper"
        ".fetch_html_with_browser",
        return_value=many_html,
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] <= 5
