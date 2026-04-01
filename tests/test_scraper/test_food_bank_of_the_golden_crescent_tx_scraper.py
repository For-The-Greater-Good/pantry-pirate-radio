"""Tests for Food Bank of the Golden Crescent scraper."""

import json

import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.food_bank_of_the_golden_crescent_tx_scraper import (
    KNOWN_LOCATIONS,
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


def test_known_locations_populated():
    """Test that KNOWN_LOCATIONS fallback has entries."""
    assert len(KNOWN_LOCATIONS) >= 12
    for loc in KNOWN_LOCATIONS:
        assert loc["state"] == "TX"
        assert loc["name"]
        assert loc["city"]


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
async def test_scrape_uses_fallback_on_empty_parse():
    """Test scraper uses known locations when Wix returns no data."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    # Wix HTML with no parseable content (typical response)
    wix_html = "<html><body><div>Loading...</div></body></html>"

    with patch.object(
        scraper, "_fetch_page", new_callable=AsyncMock, return_value=wix_html
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 12
    assert len(submitted) >= 12
    assert submitted[0]["source"] == "food_bank_of_the_golden_crescent_tx"


@pytest.mark.asyncio
async def test_scrape_uses_fallback_on_error():
    """Test scraper uses known locations when fetch fails."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper()
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch.object(
        scraper,
        "_fetch_page",
        new_callable=AsyncMock,
        side_effect=Exception("Network error"),
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 12


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper(test_mode=True)
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
    assert summary["scraper_id"] == "food_bank_of_the_golden_crescent_tx"
    assert summary["food_bank"] == "Food Bank of the Golden Crescent"

    if submitted:
        assert submitted[0]["source"] == "food_bank_of_the_golden_crescent_tx"
        assert submitted[0]["food_bank"] == "Food Bank of the Golden Crescent"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper(test_mode=True)

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


@pytest.mark.asyncio
async def test_scrape_test_mode_limits_results():
    """Test that test mode limits the number of locations submitted."""
    scraper = FoodBankOfTheGoldenCrescentTxScraper(test_mode=True)

    # Use empty HTML so it falls back to 12 known locations
    with patch.object(
        scraper,
        "_fetch_page",
        new_callable=AsyncMock,
        return_value="<html><body></body></html>",
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] <= 5
