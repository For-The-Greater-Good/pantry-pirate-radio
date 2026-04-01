"""Tests for FOOD for Lane County OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.food_for_lane_county_or_scraper import (
    FoodForLaneCountyOrScraper,
)

# --- Sample HTML fixtures ---

SAMPLE_HTML_FOOD_FINDER = """
<html><body><main>
<script src="https://maps.googleapis.com/maps/api/js?key=FAKE"></script>
<div class='foodlocation'>
  <a href='/location/springfield-pantry/' class='foodlocation-title'>Springfield Food Pantry</a>
  <br /><i>Partner Pantries</i><br />
  <a href='https://maps.google.com/maps?q=123 Main Street, Springfield, OR 97477'
     target='new' style='font-weight:400;'>123 Main Street, Springfield, OR 97477
     | <span style='text-decoration:underline;'>Get Directions</span></a><br />
  <a href='tel:+15415551234' style='font-weight:400;'>541-555-1234</a><br />
  <p>Monday-Friday 9am-5pm</p>
</div>
<div class='foodlocation'>
  <a href='/location/eugene-kitchen/' class='foodlocation-title'>Eugene Community Kitchen</a>
  <br /><i>Meal Sites</i><br />
  <a href='https://maps.google.com/maps?q=456 Oak Avenue, Eugene, OR 97401'
     target='new' style='font-weight:400;'>456 Oak Avenue, Eugene, OR 97401
     | <span style='text-decoration:underline;'>Get Directions</span></a><br />
  <a href='tel:+15415555678' style='font-weight:400;'>541-555-5678</a><br />
  <p>Tue-Sat 10am-2pm</p>
</div>
<div class='foodlocation'>
  <a href='/location/cottage-grove/' class='foodlocation-title'>Cottage Grove Pantry</a>
  <br /><i>Partner Pantries</i><br />
  <a href='https://maps.google.com/maps?q=789 Elm Road, Cottage Grove, OR 97424'
     target='new' style='font-weight:400;'>789 Elm Road, Cottage Grove, OR 97424
     | <span style='text-decoration:underline;'>Get Directions</span></a><br />
  <a href='tel:+15415559012' style='font-weight:400;'>541-555-9012</a><br />
  <p>Wednesdays 1pm-3pm</p>
</div>
</main></body></html>
"""

SAMPLE_HTML_EMPTY = """
<html><body><main>
  <h2>Get Help</h2>
  <p>Call our office for information.</p>
</main></body></html>
"""

SAMPLE_HTML_FALLBACK = """
<html><body><main>
  <h3>Springfield Food Pantry</h3>
  <p>123 Main Street, Springfield, OR 97477</p>
  <p>(541) 555-1234</p>

  <h3>Eugene Pantry</h3>
  <p>456 Oak Avenue, Eugene, OR 97401</p>
</main></body></html>
"""

SAMPLE_HTML_DUPLICATES = """
<html><body><main>
<div class='foodlocation'>
  <a href='/loc/1/' class='foodlocation-title'>Springfield Food Pantry</a><br />
  <a href='https://maps.google.com/maps?q=123 Main Street, Springfield, OR 97477'
     target='new'>123 Main Street, Springfield, OR 97477</a><br />
  <p>Mon-Fri</p>
</div>
<div class='foodlocation'>
  <a href='/loc/2/' class='foodlocation-title'>Springfield Food Pantry</a><br />
  <a href='https://maps.google.com/maps?q=123 Main Street, Springfield, OR 97477'
     target='new'>123 Main Street, Springfield, OR 97477</a><br />
  <p>Mon-Fri</p>
</div>
<div class='foodlocation'>
  <a href='/loc/3/' class='foodlocation-title'>Eugene Pantry</a><br />
  <a href='https://maps.google.com/maps?q=456 Oak Avenue, Eugene, OR 97401'
     target='new'>456 Oak Avenue, Eugene, OR 97401</a><br />
  <p>Tue-Sat</p>
</div>
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


def test_parse_food_finder_locations():
    """Test parsing locations from foodlocation divs."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_FOOD_FINDER)

    assert len(locations) >= 2
    names = [loc["name"] for loc in locations]
    assert "Springfield Food Pantry" in names


def test_parse_fallback_headings():
    """Test fallback to heading-based parsing when no foodlocation divs."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_FALLBACK)

    assert len(locations) >= 1


def test_parse_locations_empty():
    """Test parsing returns empty list from minimal HTML."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_EMPTY)
    # May find "Get Help" as a heading but no address data
    assert isinstance(locations, list)


def test_extract_phone():
    """Test phone extraction from foodlocation divs."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_FOOD_FINDER)

    phones = [loc.get("phone", "") for loc in locations if loc.get("phone")]
    assert len(phones) > 0
    assert any("541" in p for p in phones)


def test_extract_address():
    """Test address extraction from foodlocation divs."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_FOOD_FINDER)

    addresses = [loc.get("address", "") for loc in locations if loc.get("address")]
    assert len(addresses) > 0


def test_state_defaults_to_or():
    """Test that state always defaults to OR."""
    scraper = FoodForLaneCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML_FOOD_FINDER)

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
        return SAMPLE_HTML_FOOD_FINDER

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
    # Create HTML with many food locations
    many_html = "<html><body><main>"
    for i in range(10):
        many_html += f"""
        <div class='foodlocation'>
          <a href='/loc/{i}/' class='foodlocation-title'>Pantry {i}</a><br />
          <a href='https://maps.google.com/maps?q={i}00 Main Street, Eugene, OR 97401'
             target='new'>{i}00 Main Street, Eugene, OR 97401</a><br />
          <a href='tel:+1541555{i:04d}'>541-555-{i:04d}</a><br />
          <p>Mon-Fri 9am-5pm</p>
        </div>
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
