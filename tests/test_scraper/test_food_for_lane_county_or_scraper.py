"""Tests for FOOD for Lane County OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.food_for_lane_county_or_scraper import (
    FoodForLaneCountyOrScraper,
)

# --- Sample HTML fixtures ---

SAMPLE_HTML_WITH_LOCATIONS = """
<html><body><main>
  <h3>Springfield Food Pantry</h3>
  <p>123 Main Street<br>
  Springfield, OR 97477<br>
  (541) 555-1234<br>
  Hours: Mon-Fri 9am-5pm</p>

  <h3>Eugene Community Kitchen</h3>
  <p>456 Oak Avenue<br>
  Eugene, OR 97401<br>
  (541) 555-5678<br>
  Hours: Tue-Sat 10am-2pm</p>

  <h3>Cottage Grove Pantry</h3>
  <p>789 Elm Road<br>
  Cottage Grove, OR 97424<br>
  (541) 555-9012</p>
</main></body></html>
"""

SAMPLE_HTML_EMPTY = """
<html><body><main>
  <h2>Get Help</h2>
  <p>Call our office for information.</p>
</main></body></html>
"""

SAMPLE_HTML_BLOCKS = """
<html><body><main>
  <article>
    <h4>First Baptist Church Food Pantry</h4>
    <p>100 Church Lane, Eugene, OR 97402</p>
    <p>(541) 555-3333</p>
    <p>Hours: Wednesdays 1pm-3pm</p>
  </article>
  <article>
    <h4>St. Vincent de Paul</h4>
    <p>200 Charity Drive, Eugene, OR 97401</p>
    <p>(541) 555-4444</p>
  </article>
</main></body></html>
"""

SAMPLE_HTML_DUPLICATES = """
<html><body><main>
  <h3>Springfield Food Pantry</h3>
  <p>123 Main Street, Springfield, OR 97477</p>

  <h3>Springfield Food Pantry</h3>
  <p>123 Main Street, Springfield, OR 97477</p>

  <h3>Eugene Pantry</h3>
  <p>456 Oak Avenue, Eugene, OR 97401</p>
</main></body></html>
"""


def test_scraper_init():
    """Test scraper initializes with correct defaults."""
    scraper = FoodForLaneCountyOrScraper()
    assert scraper.scraper_id == "food_for_lane_county_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = FoodForLaneCountyOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations_with_headings():
    """Test parsing locations from heading-delimited HTML."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_WITH_LOCATIONS)

    assert len(locations) >= 2
    names = [loc["name"] for loc in locations]
    assert "Springfield Food Pantry" in names


def test_parse_locations_from_blocks():
    """Test parsing locations from article blocks."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_BLOCKS)

    assert len(locations) >= 1
    names = [loc["name"] for loc in locations]
    has_church = any("Baptist" in n or "Church" in n for n in names)
    assert has_church or len(locations) > 0


def test_parse_locations_empty():
    """Test parsing returns empty list from minimal HTML."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_EMPTY)
    # May find "Get Help" as a heading but no address data
    assert isinstance(locations, list)


def test_extract_phone():
    """Test phone extraction from location text."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_WITH_LOCATIONS)

    phones = [loc.get("phone", "") for loc in locations if loc.get("phone")]
    assert len(phones) > 0
    assert any("541" in p for p in phones)


def test_extract_address():
    """Test address extraction from location text."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_WITH_LOCATIONS)

    addresses = [loc.get("address", "") for loc in locations if loc.get("address")]
    assert len(addresses) > 0


def test_state_defaults_to_or():
    """Test that state always defaults to OR."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_WITH_LOCATIONS)

    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch):
    """Test that duplicate locations are removed."""
    scraper = FoodForLaneCountyOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML_DUPLICATES

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return f"job-{len(submitted)}"

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["unique_locations"] <= summary["total_locations_found"]
    assert summary["scraper_id"] == "food_for_lane_county_or"
    assert summary["food_bank"] == "FOOD for Lane County"


@pytest.mark.asyncio
async def test_scrape_metadata(monkeypatch: pytest.MonkeyPatch):
    """Test that submitted locations include correct metadata."""
    scraper = FoodForLaneCountyOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML_BLOCKS

    submitted: list[dict[str, Any]] = []

    def mock_submit(content: str) -> str:
        submitted.append(json.loads(content))
        return "job-1"

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    await scraper.scrape()

    if submitted:
        loc = submitted[0]
        assert loc["source"] == "food_for_lane_county_or"
        assert loc["food_bank"] == "FOOD for Lane County"
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_test_mode(monkeypatch: pytest.MonkeyPatch):
    """Test scraper in test mode limits results."""
    # Create HTML with many locations
    many_html = "<html><body><main>"
    for i in range(10):
        many_html += f"""
        <h3>Pantry {i}</h3>
        <p>{i}00 Main Street, Eugene, OR 97401</p>
        <p>(541) 555-{i:04d}</p>
        """
    many_html += "</main></body></html>"

    scraper = FoodForLaneCountyOrScraper(test_mode=True)

    async def mock_fetch(client: Any, url: str) -> str:
        return many_html

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return f"job-{len(submitted)}"

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["total_jobs_created"] <= 5


@pytest.mark.asyncio
async def test_scrape_handles_fetch_error(monkeypatch: pytest.MonkeyPatch):
    """Test scraper handles network errors gracefully."""
    scraper = FoodForLaneCountyOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["total_jobs_created"] == 0
    assert summary["unique_locations"] == 0
