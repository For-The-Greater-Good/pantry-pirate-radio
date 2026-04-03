"""Tests for Montgomery County Food Bank scraper."""

import json

import pytest
from unittest.mock import patch

from app.scraper.scrapers.montgomery_county_food_bank_tx_scraper import (
    MontgomeryCountyFoodBankTxScraper,
)


# Mock HTML with embedded JSON matching the real page structure.
# The real page has ``var locations = [...]`` inside a <script> tag.
MOCK_PARTNER_PAGE = """
<html>
<body>
<main>
<h1>Partner Agencies</h1>
<div id="content">
<p>Find a food pantry near you.</p>
</div>
</main>
<script>
var locations = [
  {
    "type": "Food Pantry",
    "title": "Community Assistance Center",
    "address": "1022 McCall Ave., Conroe, Texas, 77301",
    "zip": null,
    "contact": "936-539-1096",
    "hours": "Tuesday through Friday 8:30 a.m. - 11:30 am.",
    "weekdays": ["Tuesday", "Wednesday", "Thursday", "Friday"],
    "date": null,
    "latitude": "30.314407",
    "longitude": "-95.466977",
    "website": ""
  },
  {
    "type": "Food Pantry",
    "title": "Willis Food Bank",
    "address": "600 Gerald Street, Ste. 203, Willis, Texas, 77378",
    "zip": null,
    "contact": "(936) 539-1096",
    "hours": "Tuesday and Thursdays 8:30 a.m. - 1:30 p.m.",
    "weekdays": ["Tuesday", "Thursday"],
    "date": null,
    "latitude": "30.430362",
    "longitude": "-95.491302",
    "website": ""
  },
  {
    "type": "Fresh Produce Market",
    "title": "Magnolia Helping Hands",
    "address": "14320 FM 1488, Magnolia, TX 77354",
    "zip": null,
    "contact": "(281) 356-9012",
    "hours": "Friday 9:00 AM - 12:00 PM",
    "weekdays": ["Friday"],
    "date": null,
    "latitude": "30.2",
    "longitude": "-95.7",
    "website": ""
  }
];
</script>
</body>
</html>
"""

# Fallback HTML without JSON — tests regex address extraction
MOCK_FALLBACK_PAGE = """
<html>
<body>
<main>
<p>3500 N Loop 336 W, Conroe, TX 77304</p>
<p>22116 Russell Drive, New Caney, TX 77357</p>
</main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Test scraper initializes with correct parameters."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    assert scraper.scraper_id == "montgomery_county_food_bank_tx"
    assert "mcfoodbank.org" in scraper.partner_url
    assert scraper.test_mode is False


@pytest.mark.asyncio
async def test_scraper_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = MontgomeryCountyFoodBankTxScraper(test_mode=True)
    assert scraper.test_mode is True


@pytest.mark.asyncio
async def test_extract_json_locations():
    """Test extracting location data from embedded JSON."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    raw = scraper._extract_json_locations(MOCK_PARTNER_PAGE)
    assert len(raw) == 3
    assert raw[0]["title"] == "Community Assistance Center"
    assert "Conroe" in raw[0]["address"]


@pytest.mark.asyncio
async def test_parse_locations():
    """Test parsing locations from HTML with embedded JSON."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_PARTNER_PAGE)

    assert len(locations) == 3
    names = [loc["name"] for loc in locations]
    assert "Community Assistance Center" in names
    assert "Willis Food Bank" in names
    assert "Magnolia Helping Hands" in names


@pytest.mark.asyncio
async def test_parse_locations_extracts_phone():
    """Test that phone numbers are extracted from contact field."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_PARTNER_PAGE)

    phones = [loc.get("phone", "") for loc in locations]
    assert any("936" in p for p in phones)


@pytest.mark.asyncio
async def test_parse_locations_extracts_hours():
    """Test that hours are extracted from JSON data."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_PARTNER_PAGE)

    hours = [loc.get("hours", "") for loc in locations]
    assert any("Tuesday" in h for h in hours)


@pytest.mark.asyncio
async def test_parse_locations_extracts_zip():
    """Test that zip codes are extracted from addresses."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_PARTNER_PAGE)

    zips = [loc.get("zip", "") for loc in locations]
    assert "77301" in zips
    assert "77378" in zips


@pytest.mark.asyncio
async def test_parse_locations_sets_state():
    """Test that state defaults to TX."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_PARTNER_PAGE)

    for loc in locations:
        assert loc["state"] == "TX"


@pytest.mark.asyncio
async def test_parse_locations_deduplicates():
    """Test that duplicate locations are removed."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    # Create HTML with duplicate entries
    dup_html = """
    <html><body>
    <script>
    var locations = [
      {"type": "Food Pantry", "title": "Test Pantry",
       "address": "100 Main St, Conroe, TX 77301",
       "contact": "555-1234", "hours": "Mon 9-5",
       "weekdays": [], "zip": null, "date": null,
       "latitude": "30.3", "longitude": "-95.5", "website": ""},
      {"type": "Food Pantry", "title": "Test Pantry",
       "address": "100 Main St, Conroe, TX 77301",
       "contact": "555-1234", "hours": "Mon 9-5",
       "weekdays": [], "zip": null, "date": null,
       "latitude": "30.3", "longitude": "-95.5", "website": ""}
    ];
    </script>
    </body></html>
    """
    locations = scraper._parse_locations(dup_html)
    assert len(locations) == 1


@pytest.mark.asyncio
async def test_parse_locations_fallback():
    """Test fallback regex parsing when no JSON is found."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations(MOCK_FALLBACK_PAGE)
    assert len(locations) >= 1
    addresses = [loc["address"] for loc in locations]
    assert any("Conroe" in a or "New Caney" in a for a in addresses)


@pytest.mark.asyncio
async def test_parse_locations_empty_html():
    """Test parsing handles empty HTML gracefully."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    locations = scraper._parse_locations("<html><body></body></html>")
    assert isinstance(locations, list)
    assert len(locations) == 0


@pytest.mark.asyncio
async def test_scrape_with_browser():
    """Test scraper uses browser and parses results."""
    scraper = MontgomeryCountyFoodBankTxScraper()
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper"
        ".fetch_html_with_browser",
        return_value=MOCK_PARTNER_PAGE,
    ):
        with patch.object(
            scraper, "submit_to_queue", side_effect=capture
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 3
    assert len(submitted) == 3
    assert submitted[0]["source"] == "montgomery_county_food_bank_tx"
    assert submitted[0]["food_bank"] == "Montgomery County Food Bank"


@pytest.mark.asyncio
async def test_scrape_handles_none_response():
    """Test scraper handles None from browser gracefully."""
    scraper = MontgomeryCountyFoodBankTxScraper()

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper"
        ".fetch_html_with_browser",
        return_value=None,
    ):
        with patch.object(
            scraper, "submit_to_queue", return_value="job_123"
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0


@pytest.mark.asyncio
async def test_scrape_metadata():
    """Test that scraped locations include correct metadata."""
    scraper = MontgomeryCountyFoodBankTxScraper(test_mode=True)
    submitted: list[dict] = []

    def capture(data: str) -> str:
        submitted.append(json.loads(data))
        return "job_123"

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper"
        ".fetch_html_with_browser",
        return_value=MOCK_PARTNER_PAGE,
    ):
        with patch.object(
            scraper, "submit_to_queue", side_effect=capture
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "montgomery_county_food_bank_tx"
    assert summary["food_bank"] == "Montgomery County Food Bank"

    if submitted:
        assert submitted[0]["source"] == "montgomery_county_food_bank_tx"
        assert submitted[0]["food_bank"] == "Montgomery County Food Bank"


@pytest.mark.asyncio
async def test_scrape_returns_valid_summary():
    """Test that scrape returns a valid JSON summary."""
    scraper = MontgomeryCountyFoodBankTxScraper(test_mode=True)

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper"
        ".fetch_html_with_browser",
        return_value=MOCK_PARTNER_PAGE,
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


@pytest.mark.asyncio
async def test_scrape_test_mode_limits():
    """Test that test mode limits results to 5."""
    scraper = MontgomeryCountyFoodBankTxScraper(test_mode=True)

    items = []
    for i in range(10):
        items.append(
            {
                "type": "Food Pantry",
                "title": f"Pantry {i}",
                "address": f"{100 + i} Main St, Conroe, TX {77300 + i}",
                "contact": f"555-{1000 + i}",
                "hours": "Mon 9-5",
                "weekdays": [],
                "zip": None,
                "date": None,
                "latitude": "30.3",
                "longitude": "-95.5",
                "website": "",
            }
        )
    big_html = (
        '<html><body><script>var locations = '
        + json.dumps(items)
        + ";</script></body></html>"
    )

    with patch(
        "app.scraper.scrapers.montgomery_county_food_bank_tx_scraper"
        ".fetch_html_with_browser",
        return_value=big_html,
    ):
        with patch.object(
            scraper, "submit_to_queue", return_value="job_123"
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] <= 5
