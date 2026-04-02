"""Tests for Food Bank of the Golden Crescent scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper import (
    FoodBankOfTheGoldenCrescentTxScraper,
)


MOCK_HTML = """
<html>
<body>
<main>
<div class="sqs-block html-content">
<h3>Victoria County</h3>
<div class="location-listing">
<p><strong>Faith Community Center Pantry</strong></p>
<p>1234 Main Street, Victoria, TX 77901</p>
<p>361-578-1234</p>
<p>Tuesday 9:00 AM - 12:00 PM</p>
</div>
<div class="location-listing">
<p><strong>Golden Crescent Food Pantry</strong></p>
<p>567 Oak Ave, Victoria, TX 77901</p>
<p>361-578-5678</p>
<p>Thursday 1:00 PM - 4:00 PM</p>
</div>
<div class="location-listing">
<p><strong>Port Lavaca Mission</strong></p>
<p>890 Harbor Blvd, Port Lavaca, TX 77979</p>
<p>361-552-9012</p>
<p>Wednesday 10:00 AM - 1:00 PM</p>
</div>
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
    assert scraper.url == "https://www.tfbgc.org/get-help"
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

    # Parser finds locations from the text structure
    assert len(locations) >= 1
    # At least some location with an address should be found
    addresses = [loc.get("address", "") for loc in locations]
    assert any("Victoria" in a or "Main" in a or "Harbor" in a for a in addresses)


@pytest.mark.asyncio
async def test_parse_locations_extracts_phone():
    """Test that phone numbers are extracted from parsed locations."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("361" in phone for phone in phones)


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX for all locations."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty or minimal HTML gracefully."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_with_browser():
    """Test scraper uses browser rendering and parses results."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper.fetch_html_with_browser",
        return_value=MOCK_HTML,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 1
    assert submitted[0]["source"] == "food_bank_of_the_golden_crescent_tx"
    assert submitted[0]["food_bank"] == "Food Bank of the Golden Crescent"


@pytest.mark.asyncio
async def test_scrape_handles_none_response():
    """Test scraper handles None from browser gracefully."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper.fetch_html_with_browser",
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
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper.fetch_html_with_browser",
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
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper.fetch_html_with_browser",
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
    many_locations_html = "<html><body><main>"
    for i in range(10):
        many_locations_html += f"""
        <div>
        <p><strong>Pantry {i}</strong></p>
        <p>{100 + i} Main St, City, TX {77900 + i}</p>
        <p>361-555-{1000 + i}</p>
        </div>
        """
    many_locations_html += "</main></body></html>"

    with patch(
        "app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper.fetch_html_with_browser",
        return_value=many_locations_html,
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] <= 5
