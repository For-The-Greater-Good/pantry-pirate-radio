"""Tests for Marion Polk Food Share OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.marion_polk_food_share_or_scraper import (
    MarionPolkFoodShareOrScraper,
)

# Mock page HTML with Posts Table Pro nonce and table config
SAMPLE_PAGE_HTML = """
<html><body>
<script>
var posts_table_params = {"ajax_url":"https://marionpolkfoodshare.org/wp-admin/admin-ajax.php","ajax_nonce":"abc123def456","ajax_action":"ptp_load_posts"};
</script>
<table id="ptp_abcdef123456_1" class="posts-data-table" data-config="{}">
<thead><tr>
<th data-name="cf_community_name" data-data="cf:community_name">Community</th>
<th data-name="cf_venue_name" data-data="cf:venue_name">Name</th>
<th data-name="cf_address" data-data="cf:address">Address</th>
<th data-name="cf_resource_type" data-data="cf:resource_type">Service</th>
<th data-name="cf_days_and_hours_of_operation" data-data="cf:days_and_hours_of_operation">Hours</th>
</tr></thead>
</table>
</body></html>
"""

# Mock AJAX response data
SAMPLE_AJAX_RESPONSE = {
    "draw": 1,
    "recordsFiltered": 3,
    "recordsTotal": 3,
    "data": [
        {
            "cf:community_name": "Salem - West",
            "cf:venue_name": "AWARE Food Bank",
            "cf:address": '<p><a href="https://maps.google.com/">1660 Salem Industrial Dr\nSalem, OR 97302</a><br>\n<a href="tel:+15039815828">(503) 981-5828</a></p>',
            "cf:resource_type": "Food Pantry",
            "cf:days_and_hours_of_operation": "<p>Mon-Fri 9am-noon</p>",
        },
        {
            "cf:community_name": "Woodburn",
            "cf:venue_name": "Woodburn Food Pantry",
            "cf:address": '<p>152 Arthur St.<br>Woodburn, OR 97071<br><a href="tel:+15039815828">(503) 981-5828</a></p>',
            "cf:resource_type": "Food Pantry",
            "cf:days_and_hours_of_operation": "<p>Tuesdays 10am-2pm</p>",
        },
        {
            "cf:community_name": "Keizer",
            "cf:venue_name": "Keizer Community Pantry",
            "cf:address": '<p>980 Chemawa Rd<br>Keizer, OR 97303<br><a href="tel:+15035551234">(503) 555-1234</a></p>',
            "cf:resource_type": "Food Pantry",
            "cf:days_and_hours_of_operation": "<p>Wed &amp; Fri 1-4pm</p>",
        },
    ],
}

# Simple static HTML for fallback parsing
SAMPLE_STATIC_HTML = """
<html><body><main>
  <h3>Marion Polk Food Share Warehouse</h3>
  <p>1660 Salem Industrial Drive<br>
  Salem, OR 97302<br>
  (503) 555-1234<br>
  Hours: Mon-Fri 8am-5pm</p>

  <h3>Keizer Community Pantry</h3>
  <p>980 Chemawa Road<br>
  Keizer, OR 97303<br>
  (503) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = MarionPolkFoodShareOrScraper()
    assert scraper.scraper_id == "marion_polk_food_share_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = MarionPolkFoodShareOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_extract_nonce_and_table_id():
    """Test extracting AJAX nonce and table ID from page HTML."""
    scraper = MarionPolkFoodShareOrScraper()
    nonce, table_id = scraper._extract_nonce_and_table_id(SAMPLE_PAGE_HTML)
    assert nonce == "abc123def456"
    assert table_id == "ptp_abcdef123456_1"


def test_extract_columns_config():
    """Test extracting column config from table headers."""
    scraper = MarionPolkFoodShareOrScraper()
    columns = scraper._extract_columns_config(SAMPLE_PAGE_HTML)
    assert len(columns) >= 5
    data_keys = [c["data"] for c in columns]
    assert "cf:venue_name" in data_keys
    assert "cf:address" in data_keys


def test_parse_ajax_locations():
    """Test parsing locations from AJAX response data."""
    scraper = MarionPolkFoodShareOrScraper()
    locations = scraper._parse_ajax_locations(SAMPLE_AJAX_RESPONSE["data"])
    assert len(locations) == 3

    names = [loc["name"] for loc in locations]
    assert "AWARE Food Bank" in names
    assert "Woodburn Food Pantry" in names
    assert "Keizer Community Pantry" in names

    for loc in locations:
        assert loc["state"] == "OR"


def test_parse_ajax_extracts_phones():
    """Test that phone numbers are extracted from AJAX data."""
    scraper = MarionPolkFoodShareOrScraper()
    locations = scraper._parse_ajax_locations(SAMPLE_AJAX_RESPONSE["data"])
    phones = [loc.get("phone", "") for loc in locations]
    assert any("503" in p for p in phones)


def test_parse_ajax_extracts_hours():
    """Test that hours are extracted from AJAX data."""
    scraper = MarionPolkFoodShareOrScraper()
    locations = scraper._parse_ajax_locations(SAMPLE_AJAX_RESPONSE["data"])
    hours = [loc.get("hours", "") for loc in locations]
    assert any("9am" in h or "10am" in h for h in hours)


def test_parse_address_html():
    """Test parsing address HTML field."""
    scraper = MarionPolkFoodShareOrScraper()
    addr_html = (
        '<p>152 Arthur St.<br>Woodburn, OR 97071<br>'
        '<a href="tel:+15039815828">(503) 981-5828</a></p>'
    )
    address, city, zip_code, phone = scraper._parse_address_html(addr_html)
    assert "152 Arthur St" in address
    assert city == "Woodburn"
    assert zip_code == "97071"
    assert "503" in phone


def test_parse_locations_static_fallback():
    """Test static HTML parsing as fallback."""
    scraper = MarionPolkFoodShareOrScraper()
    locations = scraper._parse_locations(SAMPLE_STATIC_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


def test_strip_html():
    """Test HTML stripping utility."""
    scraper = MarionPolkFoodShareOrScraper()
    assert scraper._strip_html("<p>Hello <b>world</b></p>") == "Hello; world"
    assert scraper._strip_html("") == ""
    assert scraper._strip_html("<p>Simple</p>") == "Simple"


@pytest.mark.asyncio
async def test_scrape_workflow_ajax(monkeypatch: pytest.MonkeyPatch):
    """Test scrape workflow using AJAX path."""
    scraper = MarionPolkFoodShareOrScraper()

    call_count = 0

    async def mock_fetch(client: Any, url: str) -> str:
        nonlocal call_count
        call_count += 1
        return SAMPLE_PAGE_HTML

    async def mock_table_data(
        client: Any, nonce: str, table_id: str, columns: Any
    ) -> list:
        return SAMPLE_AJAX_RESPONSE["data"]

    submitted: list[dict[str, Any]] = []

    def mock_submit(content: str) -> str:
        submitted.append(json.loads(content))
        return "job-1"

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "_fetch_table_data", mock_table_data)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "marion_polk_food_share_or"
    assert summary["food_bank"] == "Marion Polk Food Share"
    assert summary["total_jobs_created"] == 3
    assert len(submitted) == 3
    assert submitted[0]["source"] == "marion_polk_food_share_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = MarionPolkFoodShareOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
