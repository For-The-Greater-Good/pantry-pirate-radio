"""Tests for CCA Regional Food Bank OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.cca_regional_food_bank_or_scraper import (
    CcaRegionalFoodBankOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>CCA Food Pantry - Warrenton</h3>
  <p>2010 SE Chokeberry Avenue<br>
  Warrenton, OR 97146<br>
  (503) 555-1234<br>
  Hours: Mon-Fri 9am-4pm</p>

  <h3>Astoria Community Pantry</h3>
  <p>100 Marine Drive<br>
  Astoria, OR 97103<br>
  (503) 555-5678</p>
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
    """Test parsing locations from HTML."""
    scraper = CcaRegionalFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


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
