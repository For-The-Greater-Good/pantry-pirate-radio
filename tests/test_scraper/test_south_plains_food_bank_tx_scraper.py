"""Tests for South Plains Food Bank scraper."""

import json

import httpx
import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.south_plains_food_bank_tx_scraper import (
    SouthPlainsFoodBankTxScraper,
    KNOWN_AGENCIES,
)


MOCK_HTML = """
<html>
<body>
<main>
<article class="entry-content">
<h2>Lubbock County</h2>
<h3>South Plains Community Action</h3>
<p>1611 Broadway, Lubbock, TX 79401</p>
<p>(806) 894-2207</p>
<p>Monday - Friday 8:00 AM - 5:00 PM</p>

<h3>Salvation Army Lubbock</h3>
<p>1500 Crickets Ave, Lubbock, TX 79401</p>
<p>(806) 765-9434</p>
<p>Tuesday and Thursday 9:00 AM - 12:00 PM</p>

<h2>Hale County</h2>
<h3>Plainview Community Pantry</h3>
<p>200 N Broadway, Plainview, TX 79072</p>
<p>(806) 296-1234</p>
<p>Wednesday 10:00 AM - 2:00 PM</p>
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
    assert scraper.url == "https://www.spfb.org/get_help"
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = SouthPlainsFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_locations():
    """Test parsing locations from HTML content."""
    scraper = SouthPlainsFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    assert len(locations) >= 2
    names = [loc["name"] for loc in locations]
    assert any(
        "Salvation" in n or "Community" in n or "Plainview" in n
        for n in names
    )


@pytest.mark.asyncio
async def test_parse_locations_extracts_phone():
    """Test that phone numbers are extracted."""
    scraper = SouthPlainsFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_HTML)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("806" in p for p in phones)


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
    locations = scraper._parse_locations(
        "<html><body></body></html>"
    )
    assert isinstance(locations, list)


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
        with patch.object(
            scraper, "submit_to_queue", side_effect=capture
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "south_plains_food_bank_tx"
    assert summary["food_bank"] == "South Plains Food Bank"

    if submitted:
        assert submitted[0]["source"] == "south_plains_food_bank_tx"
        assert submitted[0]["food_bank"] == "South Plains Food Bank"


@pytest.mark.asyncio
async def test_scrape_fallback_to_known_agencies():
    """Test fallback to known agencies when site returns 403."""
    scraper = SouthPlainsFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch_fail(client):
        raise httpx.HTTPStatusError(
            "403 Forbidden",
            request=httpx.Request("GET", scraper.url),
            response=httpx.Response(403),
        )

    with patch.object(
        scraper,
        "_fetch_page",
        new_callable=AsyncMock,
        side_effect=mock_fetch_fail,
    ):
        with patch.object(
            scraper, "submit_to_queue", side_effect=capture
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] >= 5
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
        with patch.object(
            scraper, "submit_to_queue", return_value="job_123"
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "total_jobs_created" in summary
    assert "source" in summary


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
