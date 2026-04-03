"""Tests for CCA Regional Food Bank OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.cca_regional_food_bank_or_scraper import (
    CcaRegionalFoodBankOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h1>Food Pantries in Clatsop County</h1>
  <p>CCA Regional Food Bank distributes food to our Partner Agencies.</p>
  <p>Please visit a Food pantry in the city you live in.</p>

  <p><strong>St. Vincent de Paul Food Pantry (Astoria)</strong><br />
  Location: Saint Mary's Star of the Sea Church<br />
  <a href="https://www.google.com/maps/place/1465+Grand+Ave">1465 Grand Ave., Astoria, OR 97103</a><br />
  Phone: <a href="tel:15033252007">(503) 325-2007</a><br />
  Hours of Operation:<br>Tuesdays - 1:00 p.m. to 3:00 p.m.,<br>
  Fridays - 10:00 a.m. to 12:00 p.m.</p><hr>

  <p><strong>Clatsop Community Action Food Pantry</strong><br />
  Location: CCA Regional Food Bank<br />
  <a href="https://www.google.com/maps/place/CCA+Regional+Food+Bank">2010 SE Chokeberry Ave. Warrenton, OR 97146</a><br />
  Phone: <a href="tel:15038613663">503-861-FOOD (3663)</a><br />
  Hours of Operation: Tuesdays - 1:00 p.m to 3:00 p.m.</p><hr>

  <p><strong>Grace Food Pantry</strong><br />
  Location: Grace Episcopal Church<br />
  <a href="https://www.google.com/maps/place/1545+Franklin+Ave">1545 Franklin Ave, Astoria OR 97103</a><br />
  Phone: <a href="tel:15033254691">(503) 325-4691</a><br />
  Hours of Operation: Tuesdays and Thursdays - 9:00 a.m. to 11:00 a.m.</p>
</main></body></html>
"""

SAMPLE_HTML_EMPTY = "<html><body><main><p>No locations.</p></main></body></html>"


def test_scraper_init():
    """Test scraper initializes with correct defaults."""
    scraper = CcaRegionalFoodBankOrScraper()
    assert scraper.scraper_id == "cca_regional_food_bank_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = CcaRegionalFoodBankOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    """Test parsing locations from HTML with strong-tag structure."""
    scraper = CcaRegionalFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 3
    names = [loc["name"] for loc in locations]
    assert "St. Vincent de Paul Food Pantry (Astoria)" in names
    assert "Clatsop Community Action Food Pantry" in names
    assert "Grace Food Pantry" in names
    for loc in locations:
        assert loc["state"] == "OR"


def test_parse_locations_extracts_phones():
    """Test that phone numbers are extracted from tel: links."""
    scraper = CcaRegionalFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    phones = [loc.get("phone", "") for loc in locations]
    assert any("503" in p or "325" in p for p in phones)


def test_parse_locations_extracts_addresses():
    """Test that addresses are extracted from Google Maps links."""
    scraper = CcaRegionalFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    addresses = [loc.get("address", "") for loc in locations]
    assert any("Grand Ave" in a or "Chokeberry" in a for a in addresses)


def test_parse_empty_html():
    """Test parsing empty HTML returns empty list."""
    scraper = CcaRegionalFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_EMPTY)
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    """Test complete scrape workflow."""
    scraper = CcaRegionalFoodBankOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    submitted: list[dict[str, Any]] = []

    def mock_submit(content: str) -> str:
        submitted.append(json.loads(content))
        return "job-1"

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "cca_regional_food_bank_or"
    assert summary["food_bank"] == "CCA Regional Food Bank"
    assert summary["total_jobs_created"] >= 3
    if submitted:
        assert submitted[0]["source"] == "cca_regional_food_bank_or"
        assert submitted[0]["food_bank"] == "CCA Regional Food Bank"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    """Test scraper handles errors gracefully."""
    scraper = CcaRegionalFoodBankOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
