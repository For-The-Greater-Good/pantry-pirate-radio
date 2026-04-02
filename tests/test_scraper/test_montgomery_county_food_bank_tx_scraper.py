"""Tests for Montgomery County Food Bank scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.montgomery_county_food_bank_tx_scraper import (
    MontgomeryCountyFoodBankTxScraper,
)


MOCK_HOMEPAGE = """
<html>
<body>
<nav>
<a href="/find-food/">Find Food</a>
<a href="/about/">About</a>
</nav>
<main>
<h1>Montgomery County Food Bank</h1>
</main>
</body>
</html>
"""

MOCK_FOOD_PAGE = """
<html>
<body>
<main>
<div class="card location-card">
<h3>Conroe Community Pantry</h3>
<p>1000 W Davis St, Conroe, TX 77301</p>
<p>(936) 539-1234</p>
<p>Monday and Wednesday 9:00 AM - 1:00 PM</p>
</div>
<div class="card location-card">
<h3>Willis Food Bank</h3>
<p>200 N Bell St, Willis, TX 77378</p>
<p>(936) 890-5678</p>
<p>Tuesday and Thursday 10:00 AM - 2:00 PM</p>
</div>
<div class="card location-card">
<h3>Magnolia Helping Hands</h3>
<p>1550 FM 1488, Magnolia, TX 77354</p>
<p>(281) 356-9012</p>
<p>Friday 9:00 AM - 12:00 PM</p>
</div>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    assert scraper.scraper_id == "montgomery_county_food_bank_tx"
    assert "mcfoodbank.org" in scraper.base_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = MontgomeryCountyFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_find_food_page_urls():
    """Test finding food page URLs from homepage."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    urls = scraper._find_food_page_urls(MOCK_HOMEPAGE)
    assert len(urls) >= 1
    assert any("find-food" in url for url in urls)


@pytest.mark.asyncio
async def test_parse_locations():
    """Test parsing locations from HTML content."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    assert len(locations) >= 2
    names = [loc["name"] for loc in locations]
    assert any("Conroe" in n or "Willis" in n or "Magnolia" in n for n in names)


@pytest.mark.asyncio
async def test_parse_locations_extracts_phone():
    """Test that phone numbers are extracted."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("936" in p or "281" in p for p in phones)


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty HTML gracefully."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_with_browser_fallback():
    """Test scraper uses browser fallback and parses results."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(url, client=None, headers=None, timeout=30):
        if "find-food" in url:
            return MOCK_FOOD_PAGE
        return MOCK_HOMEPAGE

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper.fetch_with_browser_fallback",
        side_effect=mock_fetch,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 2
    assert len(submitted) >= 2
    assert submitted[0]["source"] == "montgomery_county_food_bank_tx"
    assert submitted[0]["food_bank"] == "Montgomery County Food Bank"


@pytest.mark.asyncio
async def test_scrape_handles_none_response():
    """Test scraper handles None from browser fallback gracefully."""
    scraper = MontgomeryCountyFoodBankTxScraper()

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper.fetch_with_browser_fallback",
        return_value=None,
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = MontgomeryCountyFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(url, client=None, headers=None, timeout=30):
        if "find-food" in url:
            return MOCK_FOOD_PAGE
        return MOCK_HOMEPAGE

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper.fetch_with_browser_fallback",
        side_effect=mock_fetch,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "montgomery_county_food_bank_tx"
    assert summary["food_bank"] == "Montgomery County Food Bank"

    if submitted:
        assert submitted[0]["source"] == "montgomery_county_food_bank_tx"
        assert submitted[0]["food_bank"] == "Montgomery County Food Bank"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = MontgomeryCountyFoodBankTxScraper(test_mode=True)

    async def mock_fetch(url, client=None, headers=None, timeout=30):
        return MOCK_FOOD_PAGE

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper.fetch_with_browser_fallback",
        side_effect=mock_fetch,
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "total_jobs_created" in summary
