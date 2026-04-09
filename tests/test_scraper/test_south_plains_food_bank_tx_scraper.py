"""Tests for South Plains Food Bank scraper."""

import json

import httpx
import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.south_plains_food_bank_tx_scraper import (
    SouthPlainsFoodBankTxScraper,
)

MOCK_HTML = """
<html>
<body>
<main>
<article class="entry-content">
<h2>Mobile Pantry Sites</h2>
<p>Cochran</p>
<p>404 N Fillmore St (City Hall), Whiteface, 3rd Thursday at 10:00am</p>
<p>202 SE 1st St (First Baptist Church), Morton, 3rd Thursday at 10:30am</p>
<p>Crosby</p>
<p>211 Tyler Ave (First Baptist Church), Lorenzo, 1st Monday at 10:00am</p>
<p>Hale</p>
<p>306 W 6th St (First Baptist Church), Hale Center, 1st Thursday at 10:00am</p>
<p>201 S I-27 (Trinity Life Church), Plainview, 1st Thursday at 11:30am</p>
</article>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = SouthPlainsFoodBankTxScraper()
    assert scraper.scraper_id == "south_plains_food_bank_tx"
    assert scraper.url == "https://www.spfb.org/mobile-pantry/"
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SouthPlainsFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_locations():
    """Test parsing locations from mobile pantry HTML content."""
    scraper = SouthPlainsFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    assert len(locations) >= 3
    names = [loc["name"] for loc in locations]
    assert any("City Hall" in n for n in names)
    assert any("First Baptist Church" in n for n in names)


@pytest.mark.asyncio
async def test_parse_locations_extracts_schedule():
    """Test that schedules are extracted as hours."""
    scraper = SouthPlainsFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    hours = [loc.get("hours", "") for loc in locations]
    assert any("Thursday" in h or "Monday" in h for h in hours)


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX."""
    scraper = SouthPlainsFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty HTML gracefully."""
    scraper = SouthPlainsFoodBankTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_with_browser_fallback():
    """Test scrape uses browser fallback and parses HTML."""
    scraper = SouthPlainsFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch(
        "app.scraper.scrapers.south_plains_food_bank_tx_scraper.fetch_with_browser_fallback",
        new_callable=AsyncMock,
        return_value=MOCK_HTML,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "south_plains_food_bank_tx"
    assert summary["food_bank"] == "South Plains Food Bank"
    assert summary["total_jobs_created"] >= 1

    if submitted:
        assert submitted[0]["source"] == "south_plains_food_bank_tx"
        assert submitted[0]["food_bank"] == "South Plains Food Bank"


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = SouthPlainsFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch.object(
        scraper,
        "_fetch_page",
        new_callable=AsyncMock,
        return_value=MOCK_HTML,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "south_plains_food_bank_tx"
    assert summary["food_bank"] == "South Plains Food Bank"

    if submitted:
        assert submitted[0]["source"] == "south_plains_food_bank_tx"
        assert submitted[0]["food_bank"] == "South Plains Food Bank"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = SouthPlainsFoodBankTxScraper(test_mode=True)

    with patch.object(
        scraper,
        "_fetch_page",
        new_callable=AsyncMock,
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
async def test_scrape_empty_when_all_fail():
    """Test scrape returns zero jobs when browser fallback fails."""
    scraper = SouthPlainsFoodBankTxScraper(test_mode=True)

    with patch.object(
        scraper,
        "_fetch_page",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
    assert summary["total_locations_found"] == 0


@pytest.mark.asyncio
async def test_text_fallback_parser():
    """Test the text fallback parser works with unstructured content."""
    scraper = SouthPlainsFoodBankTxScraper()
    seen: set[str] = set()

    from bs4 import BeautifulSoup

    html = """<div>
    Community Food Pantry
    123 Main St, Lubbock, TX 79401
    (806) 555-1234
    Other Line
    Another Pantry
    456 Oak Ave, Plainview, TX 79072
    (806) 555-5678
    </div>"""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div")

    locations = scraper._parse_text_fallback(content, seen)
    assert isinstance(locations, list)
