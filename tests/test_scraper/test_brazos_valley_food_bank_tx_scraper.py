"""Tests for Brazos Valley Food Bank scraper."""

import json

import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.brazos_valley_food_bank_tx_scraper import (
    BrazosValleyFoodBankTxScraper,
)


MOCK_HOMEPAGE = """
<html>
<body>
<nav>
<a href="/programs/">Programs</a>
<a href="/find-food/">Find Food</a>
<a href="/donate/">Donate</a>
</nav>
<main>
<h1>Brazos Valley Food Bank</h1>
<p>Serving the Brazos Valley community.</p>
</main>
</body>
</html>
"""

MOCK_FOOD_PAGE = """
<html>
<body>
<main>
<h2>Partner Agencies</h2>
<p>
Bryan/College Station Pantry
</p>
<p>2001 E 29th St, Bryan, TX 77802</p>
<p>(979) 779-1234</p>
<p>Monday through Friday 8:00 AM - 5:00 PM</p>

<p>
Navasota Community Center
</p>
<p>600 N La Salle St, Navasota, TX 77868</p>
<p>(936) 825-5678</p>
<p>Wednesday 10:00 AM - 1:00 PM</p>

<p>
Brenham Food Pantry
</p>
<p>100 E Main St, Brenham, TX 77833</p>
<p>(979) 836-9012</p>
<p>Thursday 9:00 AM - 12:00 PM</p>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = BrazosValleyFoodBankTxScraper()
    assert scraper.scraper_id == "brazos_valley_food_bank_tx"
    assert "bvfb.org" in scraper.base_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = BrazosValleyFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_find_food_page_urls():
    """Test finding food page URLs from homepage."""
    scraper = BrazosValleyFoodBankTxScraper()
    urls = scraper._find_food_page_urls(MOCK_HOMEPAGE)
    assert len(urls) >= 1
    assert any("find-food" in url or "programs" in url for url in urls)


@pytest.mark.asyncio
async def test_parse_locations():
    """Test parsing locations from HTML content."""
    scraper = BrazosValleyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    assert len(locations) >= 2
    names = [loc["name"] for loc in locations]
    assert any("Bryan" in n or "Navasota" in n or "Brenham" in n for n in names)


@pytest.mark.asyncio
async def test_parse_locations_extracts_phone():
    """Test that phone numbers are extracted."""
    scraper = BrazosValleyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("979" in p or "936" in p for p in phones)


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX."""
    scraper = BrazosValleyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FOOD_PAGE)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty HTML gracefully."""
    scraper = BrazosValleyFoodBankTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = BrazosValleyFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client, url):
        if "find-food" in url or "programs" in url:
            return MOCK_FOOD_PAGE
        return MOCK_HOMEPAGE

    with patch.object(scraper, "_fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "brazos_valley_food_bank_tx"
    assert summary["food_bank"] == "Brazos Valley Food Bank"

    if submitted:
        assert submitted[0]["source"] == "brazos_valley_food_bank_tx"
        assert submitted[0]["food_bank"] == "Brazos Valley Food Bank"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = BrazosValleyFoodBankTxScraper(test_mode=True)

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
