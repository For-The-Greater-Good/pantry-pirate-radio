"""Tests for Galveston County Food Bank scraper."""

import json
import urllib.parse

import pytest
from unittest.mock import patch

from app.scraper.scrapers.galveston_county_food_bank_tx_scraper import (
    GalvestonCountyFoodBankTxScraper,
)


def _build_elfsight_html(markers: list[dict]) -> str:
    """Build mock HTML with an Elfsight Google Maps widget."""
    config = {
        "markers": markers,
        "categories": [],
        "mapType": "roadmap",
    }
    encoded = urllib.parse.quote(json.dumps(config))
    return (
        '<html><body><main>'
        f'<div data-elfsight-google-maps-options="{encoded}"></div>'
        '</main></body></html>'
    )


MOCK_MARKERS = [
    {
        "position": "800 Grand Ave., Bacliff, TX",
        "coordinates": "29.5035924, -94.98879529999999",
        "infoTitle": "Lighthouse Christian Ministries",
        "category": "food-pantry",
        "infoDescription": "",
        "infoPhone": "281-339-3033",
        "infoWorkingHours": "",
    },
    {
        "position": "805 9th Street, San Leon, TX",
        "coordinates": "29.484838, -94.9222362",
        "infoTitle": "San Leon Community Church",
        "category": "food-pantry",
        "infoDescription": "Pantry &amp; Kidz Pacz host site",
        "infoPhone": "281-339-1347",
        "infoWorkingHours": "",
    },
    {
        "position": "1020 Diamond Rd., Crystal Beach, TX",
        "coordinates": "29.4587704, -94.6388514",
        "infoTitle": "Crystal Beach Community Church",
        "category": "food-pantry",
        "infoDescription": "",
        "infoPhone": "409-543-4087",
        "infoWorkingHours": "",
    },
]

MOCK_ELFSIGHT_PAGE = _build_elfsight_html(MOCK_MARKERS)


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = GalvestonCountyFoodBankTxScraper()
    assert scraper.scraper_id == "galveston_county_food_bank_tx"
    assert "galvestoncountyfoodbank.org" in scraper.base_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = GalvestonCountyFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_parse_elfsight_markers():
    """Test parsing markers from Elfsight widget data."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_elfsight_markers(MOCK_ELFSIGHT_PAGE)

    assert len(locations) == 3
    names = [loc["name"] for loc in locations]
    assert "Lighthouse Christian Ministries" in names
    assert "San Leon Community Church" in names
    assert "Crystal Beach Community Church" in names


@pytest.mark.asyncio
async def test_parse_elfsight_extracts_phones():
    """Test that phone numbers are extracted from markers."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_elfsight_markers(MOCK_ELFSIGHT_PAGE)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("281" in p for p in phones)
    assert any("409" in p for p in phones)


@pytest.mark.asyncio
async def test_parse_elfsight_extracts_addresses():
    """Test that addresses are extracted from position field."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_elfsight_markers(MOCK_ELFSIGHT_PAGE)

    addresses = [loc.get("address", "") for loc in locations]
    assert any("Grand Ave" in a for a in addresses)
    assert any("Diamond Rd" in a for a in addresses)


@pytest.mark.asyncio
async def test_parse_elfsight_extracts_cities():
    """Test that cities are parsed from position field."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_elfsight_markers(MOCK_ELFSIGHT_PAGE)

    cities = [loc.get("city", "") for loc in locations]
    assert "Bacliff" in cities
    assert "San Leon" in cities
    assert "Crystal Beach" in cities


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_ELFSIGHT_PAGE)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty HTML gracefully."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)


@pytest.mark.asyncio
async def test_parse_elfsight_no_widget():
    """Test returns empty list when no Elfsight widget found."""
    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_elfsight_markers(
        "<html><body><p>No map</p></body></html>"
    )
    assert locations == []


@pytest.mark.asyncio
async def test_parse_elfsight_deduplicates():
    """Test that duplicate markers are deduplicated."""
    dup_markers = [MOCK_MARKERS[0], MOCK_MARKERS[0]]
    html = _build_elfsight_html(dup_markers)

    scraper = GalvestonCountyFoodBankTxScraper()
    locations = scraper._parse_elfsight_markers(html)
    assert len(locations) == 1


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = GalvestonCountyFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    async def mock_fetch(client, url):
        return MOCK_ELFSIGHT_PAGE

    with patch.object(scraper, "_fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "galveston_county_food_bank_tx"
    assert summary["food_bank"] == "Galveston County Food Bank"

    if submitted:
        assert submitted[0]["source"] == "galveston_county_food_bank_tx"
        assert submitted[0]["food_bank"] == "Galveston County Food Bank"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = GalvestonCountyFoodBankTxScraper(test_mode=True)

    async def mock_fetch(client, url):
        return MOCK_ELFSIGHT_PAGE

    with patch.object(scraper, "_fetch_page", side_effect=mock_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_123"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "total_jobs_created" in summary
