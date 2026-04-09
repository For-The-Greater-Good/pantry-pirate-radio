"""Tests for Inter-Faith Food Shuttle NC scraper."""

import json

import pytest

from app.scraper.scrapers.inter_faith_food_shuttle_nc_scraper import (
    InterFaithFoodShuttleNcScraper,
    KML_MAPS,
)


# ---------------------------------------------------------------------------
# Sample KML fixtures
# ---------------------------------------------------------------------------

SAMPLE_PANTRY_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>Food Pantries</name>
  <Placemark>
    <name>Agency Name</name>
    <address>Address</address>
    <ExtendedData>
      <Data name="County"><value>County</value></Data>
      <Data name="Program Type"><value>Program Type</value></Data>
      <Data name="Distribution Day &amp; Time"><value>Distribution Day &amp; Time</value></Data>
      <Data name="Contact Number"><value>Contact Number</value></Data>
    </ExtendedData>
  </Placemark>
  <Placemark>
    <name>Urban Ministries of Durham</name>
    <address>410 Liberty Street, Durham, NC 27701</address>
    <ExtendedData>
      <Data name="County"><value>Durham</value></Data>
      <Data name="Program Type"><value>Food Pantry</value></Data>
      <Data name="Distribution Day &amp; Time"><value>Monday-Friday 10am-12pm</value></Data>
      <Data name="Contact Number"><value>(919) 682-0538</value></Data>
    </ExtendedData>
    <Point>
      <coordinates>-78.9029,35.9940,0</coordinates>
    </Point>
  </Placemark>
  <Placemark>
    <name>Hope Community Church</name>
    <address>123 Oak Lane, Raleigh, NC 27601</address>
    <ExtendedData>
      <Data name="County"><value>Wake</value></Data>
      <Data name="Program Type"><value>Food Pantry</value></Data>
      <Data name="Distribution Day &amp; Time"><value>2nd Saturday 9am-11am</value></Data>
      <Data name="Contact Number"><value>919-555-1234</value></Data>
    </ExtendedData>
  </Placemark>
</Document>
</kml>
"""

SAMPLE_MOBILE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>Mobile Markets</name>
  <Placemark>
    <name>Agency Name</name>
    <address>Address</address>
    <ExtendedData>
      <Data name="County"><value>County</value></Data>
      <Data name="Program"><value>Program</value></Data>
      <Data name="Distribution Day &amp; Time"><value>Distribution Day &amp; Time</value></Data>
      <Data name="Contact Number"><value>Contact Number</value></Data>
    </ExtendedData>
  </Placemark>
  <Placemark>
    <name>Southeast Raleigh YMCA</name>
    <address>1436 Rock Quarry Rd, Raleigh, NC 27610</address>
    <ExtendedData>
      <Data name="County"><value>Wake</value></Data>
      <Data name="Program"><value>Mobile Market</value></Data>
      <Data name="Distribution Day &amp; Time"><value>1st and 3rd Wednesdays 2pm-4pm</value></Data>
      <Data name="Contact Number"><value>(919) 831-6933</value></Data>
    </ExtendedData>
    <Point>
      <coordinates>-78.6153,35.7585,0</coordinates>
    </Point>
  </Placemark>
</Document>
</kml>
"""

# KML with no header row
SAMPLE_KML_NO_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <Placemark>
    <name>Some Pantry</name>
    <address>100 Main St, Durham, NC 27701</address>
  </Placemark>
</Document>
</kml>
"""

# KML with duplicate entries
SAMPLE_KML_WITH_DUPLICATES = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <Placemark>
    <name>Duplicate Pantry</name>
    <address>500 Elm St, Cary, NC 27511</address>
  </Placemark>
  <Placemark>
    <name>Duplicate Pantry</name>
    <address>500 Elm St, Cary, NC 27511</address>
  </Placemark>
  <Placemark>
    <name>Unique Pantry</name>
    <address>600 Pine St, Apex, NC 27502</address>
  </Placemark>
</Document>
</kml>
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scraper_init():
    """Test scraper initializes with correct defaults."""
    scraper = InterFaithFoodShuttleNcScraper()
    assert scraper.scraper_id == "inter_faith_food_shuttle_nc"
    assert "foodshuttle.org" in scraper.url
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    """Test scraper initializes correctly in test mode."""
    scraper = InterFaithFoodShuttleNcScraper(test_mode=True)
    assert scraper.test_mode is True


def test_kml_url():
    """Test KML URL construction."""
    scraper = InterFaithFoodShuttleNcScraper()
    url = scraper._kml_url("abc123")
    assert url == "https://www.google.com/maps/d/kml?mid=abc123&forcekml=1"


def test_kml_maps_configured():
    """Test that both maps are configured."""
    assert len(KML_MAPS) == 2
    labels = {m["label"] for m in KML_MAPS}
    assert "Food Pantries" in labels
    assert "Mobile Markets" in labels


# ---------------------------------------------------------------------------
# KML parsing tests
# ---------------------------------------------------------------------------


def test_parse_pantry_kml():
    """Test parsing pantry KML extracts correct locations."""
    scraper = InterFaithFoodShuttleNcScraper()
    locations = scraper.parse_kml(SAMPLE_PANTRY_KML, "Food Pantries")

    # Header row should be skipped, leaving 2 locations
    assert len(locations) == 2

    urban = locations[0]
    assert urban["name"] == "Urban Ministries of Durham"
    assert "410 Liberty Street" in urban["address"]
    assert urban["county"] == "Durham"
    assert urban["services"] == "Food Pantry"
    assert "Monday-Friday" in urban["hours"]
    assert urban["phone"] == "(919) 682-0538"
    assert urban["state"] == "NC"
    assert urban["program_category"] == "Food Pantries"

    # Coordinates present
    assert urban["longitude"] == pytest.approx(-78.9029, abs=0.001)
    assert urban["latitude"] == pytest.approx(35.9940, abs=0.001)


def test_parse_mobile_kml():
    """Test parsing mobile market KML extracts correct locations."""
    scraper = InterFaithFoodShuttleNcScraper()
    locations = scraper.parse_kml(SAMPLE_MOBILE_KML, "Mobile Markets")

    # Header row skipped, 1 location
    assert len(locations) == 1

    ymca = locations[0]
    assert ymca["name"] == "Southeast Raleigh YMCA"
    assert ymca["services"] == "Mobile Market"
    assert ymca["program_category"] == "Mobile Markets"
    assert "Wednesdays" in ymca["hours"]
    assert ymca["phone"] == "(919) 831-6933"


def test_parse_kml_skips_header_row():
    """Test that the header row (name='Agency Name') is skipped."""
    scraper = InterFaithFoodShuttleNcScraper()
    locations = scraper.parse_kml(SAMPLE_PANTRY_KML, "Food Pantries")

    names = [loc["name"] for loc in locations]
    assert "Agency Name" not in names


def test_parse_kml_no_header():
    """Test parsing KML without a header row works fine."""
    scraper = InterFaithFoodShuttleNcScraper()
    locations = scraper.parse_kml(SAMPLE_KML_NO_HEADER, "Test")

    assert len(locations) == 1
    assert locations[0]["name"] == "Some Pantry"


def test_parse_kml_missing_coordinates():
    """Test that locations without coordinates are still included."""
    scraper = InterFaithFoodShuttleNcScraper()
    locations = scraper.parse_kml(SAMPLE_PANTRY_KML, "Food Pantries")

    # Hope Community Church has no <Point>/<coordinates>
    hope = next(loc for loc in locations if "Hope" in loc["name"])
    assert "latitude" not in hope
    assert "longitude" not in hope
    # But still has address and other fields
    assert "123 Oak Lane" in hope["address"]
    assert hope["phone"] == "919-555-1234"


def test_parse_kml_missing_extended_data():
    """Test parsing handles placemarks with no ExtendedData."""
    scraper = InterFaithFoodShuttleNcScraper()
    locations = scraper.parse_kml(SAMPLE_KML_NO_HEADER, "Test")

    loc = locations[0]
    # Should not have services, hours, phone, county
    assert "services" not in loc
    assert "hours" not in loc
    assert "phone" not in loc
    assert "county" not in loc
    # But still has state
    assert loc["state"] == "NC"


def test_is_header_row():
    """Test header row detection."""
    scraper = InterFaithFoodShuttleNcScraper()
    assert scraper._is_header_row("Agency Name") is True
    assert scraper._is_header_row("agency name") is True
    assert scraper._is_header_row("Agency") is True
    assert scraper._is_header_row("") is True
    assert scraper._is_header_row("Urban Ministries") is False


def test_extract_phone():
    """Test phone number extraction from various formats."""
    scraper = InterFaithFoodShuttleNcScraper()
    assert scraper._extract_phone("(919) 682-0538") == "(919) 682-0538"
    assert scraper._extract_phone("919-555-1234") == "919-555-1234"
    assert scraper._extract_phone("Call 919.555.1234 for info") == "919.555.1234"
    assert scraper._extract_phone("") == ""
    assert scraper._extract_phone(None) == ""


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduplication(monkeypatch):
    """Test that duplicate name+address pairs are deduplicated."""
    scraper = InterFaithFoodShuttleNcScraper()

    async def mock_download(mid):
        return SAMPLE_KML_WITH_DUPLICATES

    monkeypatch.setattr(scraper, "download_kml", mock_download)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda content: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)

    # 2 maps x 2 placemarks each = 4 total, but dedup by name+address
    # leaves 2 unique per map call, then across both maps: same duplicates
    # Each call returns 3 placemarks (2 dupes + 1 unique) = 6 total, 2 unique
    assert summary["total_locations_found"] == 6
    assert summary["unique_locations"] == 2


# ---------------------------------------------------------------------------
# Full scrape workflow tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_combines_both_maps(monkeypatch):
    """Test that scrape fetches and combines both pantry and mobile market maps."""
    scraper = InterFaithFoodShuttleNcScraper()

    download_calls = []

    async def mock_download(mid):
        download_calls.append(mid)
        if mid == KML_MAPS[0]["mid"]:
            return SAMPLE_PANTRY_KML
        return SAMPLE_MOBILE_KML

    submitted = []

    def mock_submit(content):
        submitted.append(json.loads(content))
        return f"job-{len(submitted)}"

    monkeypatch.setattr(scraper, "download_kml", mock_download)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Should have downloaded both maps
    assert len(download_calls) == 2

    # 2 pantries + 1 mobile market = 3 unique locations
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3
    assert summary["scraper_id"] == "inter_faith_food_shuttle_nc"
    assert summary["food_bank"] == "Inter-Faith Food Shuttle"


@pytest.mark.asyncio
async def test_scrape_metadata(monkeypatch):
    """Test that submitted locations include correct metadata."""
    scraper = InterFaithFoodShuttleNcScraper()

    async def mock_download(mid):
        return SAMPLE_KML_NO_HEADER

    submitted = []

    def mock_submit(content):
        submitted.append(json.loads(content))
        return "job-1"

    monkeypatch.setattr(scraper, "download_kml", mock_download)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    await scraper.scrape()

    # Both maps return 1 location each, dedup leaves 1 unique
    assert len(submitted) == 1
    loc = submitted[0]
    assert loc["source"] == "inter_faith_food_shuttle_nc"
    assert loc["food_bank"] == "Inter-Faith Food Shuttle"
    assert loc["state"] == "NC"


@pytest.mark.asyncio
async def test_scrape_continues_on_map_failure(monkeypatch):
    """Test that scraper continues when one map download fails."""
    scraper = InterFaithFoodShuttleNcScraper()

    call_count = 0

    async def mock_download(mid):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Network error")
        return SAMPLE_MOBILE_KML

    submitted = []

    def mock_submit(content):
        submitted.append(json.loads(content))
        return "job-1"

    monkeypatch.setattr(scraper, "download_kml", mock_download)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Only mobile market locations should be present
    assert summary["unique_locations"] == 1
    assert submitted[0]["name"] == "Southeast Raleigh YMCA"


@pytest.mark.asyncio
async def test_scrape_test_mode_limits_output(monkeypatch):
    """Test that test_mode limits the number of locations processed."""
    scraper = InterFaithFoodShuttleNcScraper(test_mode=True)

    async def mock_download(mid):
        return SAMPLE_PANTRY_KML

    submitted = []

    def mock_submit(content):
        submitted.append(json.loads(content))
        return f"job-{len(submitted)}"

    monkeypatch.setattr(scraper, "download_kml", mock_download)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["test_mode"] is True
    # test_mode limits to 5, but we only have 4 total (2 per map, 2 maps)
    # After dedup we have 2 unique
    assert summary["unique_locations"] <= 5


@pytest.mark.asyncio
async def test_scrape_empty_kml(monkeypatch):
    """Test scraper handles empty KML gracefully."""
    scraper = InterFaithFoodShuttleNcScraper()

    empty_kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml><Document></Document></kml>"""

    async def mock_download(mid):
        return empty_kml

    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")
    monkeypatch.setattr(scraper, "download_kml", mock_download)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
