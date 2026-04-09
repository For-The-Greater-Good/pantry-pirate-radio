"""Tests for Columbia Pacific Food Bank OR scraper."""

import json
from typing import Any

import pytest
from unittest.mock import patch, AsyncMock

from app.scraper.scrapers.columbia_pacific_food_bank_or_scraper import (
    ColumbiaPacificFoodBankOrScraper,
)

# Main listing page with links to subpages
LISTING_HTML = """
<html><body><main>
<h1>Food Pantries</h1>
<p>Find Your Local Food Pantry</p>
<a href="https://cpfoodbank.org/food-pantries/clatskanie-area-food-pantry/">Clatskanie Food Pantry</a>
<a href="https://cpfoodbank.org/food-pantries/rainier-area-food-pantry/">Rainier Food Pantry</a>
<a href="https://cpfoodbank.org/food-pantries/st-helens-area-food-pantry/">St. Helens Food Pantry</a>
<a href="https://cpfoodbank.org/food-pantries/vernonia-area-food-pantry/">Vernonia Food Pantry</a>
<a href="https://cpfoodbank.org/food-pantries/scappoose-area-food-pantry/">Scappoose Food Pantry</a>
<a href="https://cpfoodbank.org/food-pantries/mist-birkenfeld-area-food-pantry/">Mist-Birkenfeld Food Pantry</a>
</main></body></html>
"""

# Individual pantry subpage
CLATSKANIE_HTML = """
<html><body><main>
<h1>Clatskanie Area Food Pantry</h1>
<p>Map data 2020 Google</p>
<p>Turning Point Community Service Center</p>
<p>503-728-3126</p>
<p>Monday, Tuesday, Thursday - 10:00 am - 2:30 pm</p>
<p>220 E Columbia River Hwy</p>
<p>Clatskanie, OR 97016</p>
</main>
<footer>Columbia Pacific Food Bank</footer>
</body></html>
"""

RAINIER_HTML = """
<html><body><main>
<h1>Rainier Area Food Pantry</h1>
<p>HOPE of Rainier</p>
<p>503-556-0701</p>
<p>Monday and Wednesday - 10:00 AM - 4:00 PM</p>
<p>Last Saturday of each month - 10:00AM - 12:00PM</p>
<p>404 East A Street</p>
<p>Rainier, OR 97048</p>
</main>
<footer>Columbia Pacific Food Bank</footer>
</body></html>
"""

ST_HELENS_HTML = """
<html><body><main>
<h1>St. Helens Area Food Pantry</h1>
<p>Barbara Bullis Memorial HELP Food Pantry</p>
<p>503-397-9708</p>
<p>Monday thru Thursday - 9:00 am - 1:00 pm</p>
<p>Wednesday Evening - 5:00 pm - 7:00 pm</p>
<p>Friday - CLOSED</p>
<p>1421 Columbia Blvd.</p>
<p>St.Helens, OR 97051</p>
</main>
<footer>Columbia Pacific Food Bank</footer>
</body></html>
"""

# Combined sample for _parse_locations fallback
SAMPLE_HTML = """
<html><body><main>
  <h3>St. Helens Food Pantry</h3>
  <p>Barbara Bullis Memorial HELP Food Pantry</p>
  <p>503-397-9708</p>
  <p>Monday thru Thursday - 9:00 am - 1:00 pm</p>
  <p>1421 Columbia Blvd.</p>
  <p>St.Helens, OR 97051</p>

  <h3>Rainier Area Food Pantry</h3>
  <p>HOPE of Rainier</p>
  <p>503-556-0701</p>
  <p>Monday and Wednesday - 10:00 AM - 4:00 PM</p>
  <p>404 East A Street</p>
  <p>Rainier, OR 97048</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = ColumbiaPacificFoodBankOrScraper()
    assert scraper.scraper_id == "columbia_pacific_food_bank_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = ColumbiaPacificFoodBankOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_discover_pantry_urls():
    """Test discovering pantry subpage URLs from listing page."""
    scraper = ColumbiaPacificFoodBankOrScraper()
    urls = scraper._discover_pantry_urls(LISTING_HTML)
    assert len(urls) >= 5
    assert any("clatskanie" in u for u in urls)
    assert any("rainier" in u for u in urls)
    assert any("st-helens" in u for u in urls)


def test_parse_pantry_page_clatskanie():
    """Test parsing an individual pantry page."""
    scraper = ColumbiaPacificFoodBankOrScraper()
    locations = scraper._parse_pantry_page(CLATSKANIE_HTML)
    assert len(locations) >= 1
    loc = locations[0]
    assert "Turning Point" in loc["name"]
    assert "503" in loc.get("phone", "")
    assert loc["state"] == "OR"


def test_parse_pantry_page_rainier():
    """Test parsing Rainier pantry page."""
    scraper = ColumbiaPacificFoodBankOrScraper()
    locations = scraper._parse_pantry_page(RAINIER_HTML)
    assert len(locations) >= 1
    loc = locations[0]
    assert "HOPE" in loc["name"]


def test_parse_locations():
    """Test _parse_locations falls back correctly."""
    scraper = ColumbiaPacificFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_scrape_with_subpages():
    """Test scraper fetches listing page and individual subpages."""
    scraper = ColumbiaPacificFoodBankOrScraper()

    submitted: list[dict[str, Any]] = []

    def mock_submit(content: str) -> str:
        submitted.append(json.loads(content))
        return "job-1"

    # Mock fetch_with_browser_fallback to return different HTML
    # based on the URL being fetched
    async def mock_fetch(url, client, headers=None):
        if "clatskanie" in url:
            return CLATSKANIE_HTML
        elif "rainier" in url:
            return RAINIER_HTML
        elif "st-helens" in url:
            return ST_HELENS_HTML
        elif url.rstrip("/").endswith("food-pantries"):
            return LISTING_HTML
        return None

    with patch(
        "app.scraper.scrapers.columbia_pacific_food_bank_or_scraper.fetch_with_browser_fallback",
        side_effect=mock_fetch,
    ):
        with patch.object(scraper, "submit_to_queue", side_effect=mock_submit):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "columbia_pacific_food_bank_or"
    assert summary["food_bank"] == "Columbia Pacific Food Bank"
    assert summary["total_jobs_created"] >= 2
    assert len(submitted) >= 2
    assert submitted[0]["source"] == "columbia_pacific_food_bank_or"


@pytest.mark.asyncio
async def test_scrape_handles_none_response():
    """Test scraper handles None from browser fallback gracefully."""
    scraper = ColumbiaPacificFoodBankOrScraper()

    with patch(
        "app.scraper.scrapers.columbia_pacific_food_bank_or_scraper.fetch_with_browser_fallback",
        return_value=None,
    ):
        with patch.object(scraper, "submit_to_queue", return_value="job-1"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    """Test complete scrape workflow with HTML."""
    scraper = ColumbiaPacificFoodBankOrScraper()

    submitted: list[dict[str, Any]] = []

    def mock_submit(content: str) -> str:
        submitted.append(json.loads(content))
        return "job-1"

    # Return listing page with no subpage links to test
    # the fallback to parsing main page directly
    async def mock_fetch(url, client, headers=None):
        return SAMPLE_HTML

    with patch(
        "app.scraper.scrapers.columbia_pacific_food_bank_or_scraper.fetch_with_browser_fallback",
        side_effect=mock_fetch,
    ):
        monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)
        result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "columbia_pacific_food_bank_or"
    assert summary["food_bank"] == "Columbia Pacific Food Bank"
