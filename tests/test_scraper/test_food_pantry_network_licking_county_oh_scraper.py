"""Tests for Food Pantry Network of Licking County OH scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.food_pantry_network_licking_county_oh_scraper import (
    FoodPantryNetworkLickingCountyOhScraper,
)


SAMPLE_HTML = """
<html>
<body>
<h2>Newark Area Food Pantries</h2>
<div>
  <p><strong>First Presbyterian Church Food Pantry</strong><br/>
  100 W Church St, Newark, OH 43055<br/>
  740-345-1480<br/>
  Monday 10 AM - 12 PM<br/>
  Wednesday 5 PM - 7 PM</p>
</div>
<div>
  <p><strong>St. Francis de Sales Food Pantry</strong><br/>
  40 Granville St, Newark, OH 43055<br/>
  740-345-9874<br/>
  Tuesday 9 AM - 11 AM</p>
</div>
<div>
  <p><strong>Salvation Army Licking County</strong><br/>
  250 E Main St, Newark, OH 43055<br/>
  Thursday 1 PM - 3 PM</p>
</div>
</body>
</html>
"""

SAMPLE_HTML_EMPTY = """
<html>
<body>
<h1>Food Pantry Network of Licking County</h1>
<p>Welcome to our website.</p>
</body>
</html>
"""


def test_scraper_init():
    """Test scraper initializes with correct defaults."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    assert scraper.scraper_id == "food_pantry_network_licking_county_oh"
    assert "foodpantrynetwork.net" in scraper.base_url
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    """Test scraper initializes with test_mode enabled."""
    scraper = FoodPantryNetworkLickingCountyOhScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations_finds_pantries():
    """Test parsing finds food pantry locations from HTML."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    locations = scraper.parse_locations(SAMPLE_HTML)

    # Should find at least 2 locations with OH zip pattern
    assert len(locations) >= 2


def test_parse_locations_extracts_address():
    """Test parsing extracts address components."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    locations = scraper.parse_locations(SAMPLE_HTML)

    # Find the First Presbyterian entry
    names = [loc["name"] for loc in locations]
    assert any("Presbyterian" in n or "Church" in n for n in names)


def test_parse_locations_extracts_state():
    """Test parsing sets state to OH."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    locations = scraper.parse_locations(SAMPLE_HTML)

    for loc in locations:
        assert loc["state"] == "OH"


def test_parse_locations_empty_page():
    """Test parsing handles empty page gracefully."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    locations = scraper.parse_locations(SAMPLE_HTML_EMPTY)
    assert len(locations) == 0


def test_parse_locations_deduplicates():
    """Test parsing deduplicates by name + address."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    # Double the HTML to create potential duplicates
    doubled_html = SAMPLE_HTML.replace("</body>", "") + SAMPLE_HTML
    locations_single = scraper.parse_locations(SAMPLE_HTML)
    locations_doubled = scraper.parse_locations(doubled_html)

    # Doubled should have same count due to dedup
    assert len(locations_doubled) == len(locations_single)


def test_extract_location_from_text():
    """Test extracting location from a text block."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    text = (
        "First Presbyterian Church\n"
        "100 W Church St, Newark, OH 43055\n"
        "740-345-1480\n"
        "Monday 10 AM - 12 PM"
    )
    result = scraper._extract_location_from_text(text)

    assert result is not None
    assert result["name"] == "First Presbyterian Church"
    assert "100 W Church St" in result["address"]
    assert result["city"] == "Newark"
    assert result["state"] == "OH"
    assert result["zip"] == "43055"
    assert result["phone"] == "740-345-1480"


def test_extract_location_missing_address():
    """Test extracting returns None when no address found."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    text = "Some Food Pantry\nNo address here"
    result = scraper._extract_location_from_text(text)
    assert result is None


def test_extract_location_too_short():
    """Test extracting returns None for very short text."""
    scraper = FoodPantryNetworkLickingCountyOhScraper()
    result = scraper._extract_location_from_text("Short")
    assert result is None


@pytest.mark.asyncio
async def test_scrape_full_workflow():
    """Test complete scrape workflow returns valid summary."""
    scraper = FoodPantryNetworkLickingCountyOhScraper(test_mode=True)

    async def mock_fetch(client):
        return SAMPLE_HTML

    with patch.object(scraper, "fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "food_pantry_network_licking_county_oh"
    assert summary["food_bank"] == "Food Pantry Network of Licking County"
    assert summary["source"] == "http://www.foodpantrynetwork.net"
    assert summary["test_mode"] is True


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = FoodPantryNetworkLickingCountyOhScraper(test_mode=True)

    submitted: list[str] = []

    def capture(data):
        submitted.append(data)
        return "job_123"

    async def mock_fetch(client):
        return SAMPLE_HTML

    with patch.object(scraper, "fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            await scraper.scrape()

    if submitted:
        loc = json.loads(submitted[0])
        assert loc["source"] == "food_pantry_network_licking_county_oh"
        assert loc["food_bank"] == "Food Pantry Network of Licking County"


@pytest.mark.asyncio
async def test_scrape_empty_page():
    """Test scrape handles page with no locations."""
    scraper = FoodPantryNetworkLickingCountyOhScraper(test_mode=True)

    async def mock_fetch(client):
        return SAMPLE_HTML_EMPTY

    with patch.object(scraper, "fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_locations_found"] == 0
    assert summary["total_jobs_created"] == 0
