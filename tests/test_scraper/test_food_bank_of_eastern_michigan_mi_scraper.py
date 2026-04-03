"""Tests for Food Bank of Eastern Michigan scraper."""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_eastern_michigan_mi_scraper import (
    FoodBankOfEasternMichiganMiScraper,
)


SAMPLE_LOCATION_LIST = [
    {"sl_id": "101"},
    {"sl_id": "102"},
    {"sl_id": "103"},
]

SAMPLE_LOCATION_DETAIL: Dict[str, Any] = {
    "sl_id": "101",
    "sl_store": "Flint Community Food Bank",
    "sl_address": "123 Main St",
    "sl_address2": "Suite 200",
    "sl_city": "Flint",
    "sl_state": "MI",
    "sl_zip": "48501",
    "sl_latitude": "43.0125",
    "sl_longitude": "-83.6875",
    "sl_phone": "(810) 555-1234",
    "sl_hours": "Mon-Fri 9am-5pm",
    "sl_email": "info@flintfoodbank.org",
    "sl_url": "https://www.flintfoodbank.org",
    "sl_description": "Food assistance for Genesee County residents",
    "sl_tags": "pantry,snap",
}

SAMPLE_MINIMAL_LOCATION: Dict[str, Any] = {
    "sl_id": "102",
    "sl_store": "Saginaw Pantry",
    "sl_address": "456 State St",
    "sl_city": "Saginaw",
    "sl_state": "MI",
    "sl_zip": "48601",
    "sl_latitude": "43.4195",
    "sl_longitude": "-83.9508",
    "sl_phone": "",
    "sl_hours": "",
    "sl_email": "",
    "sl_url": "",
    "sl_description": "",
    "sl_tags": "",
}

SAMPLE_NO_NAME: Dict[str, Any] = {
    "sl_id": "200",
    "sl_store": "",
    "sl_address": "789 Unknown Rd",
    "sl_city": "Bay City",
    "sl_state": "MI",
    "sl_zip": "48706",
    "sl_latitude": "43.5945",
    "sl_longitude": "-83.8889",
    "sl_phone": "",
    "sl_hours": "",
    "sl_email": "",
    "sl_url": "",
    "sl_description": "",
    "sl_tags": "",
}

SAMPLE_NO_ADDRESS: Dict[str, Any] = {
    "sl_id": "201",
    "sl_store": "Missing Address Pantry",
    "sl_address": "",
    "sl_city": "Flint",
    "sl_state": "MI",
    "sl_zip": "48501",
    "sl_latitude": "43.0125",
    "sl_longitude": "-83.6875",
    "sl_phone": "",
    "sl_hours": "",
    "sl_email": "",
    "sl_url": "",
    "sl_description": "",
    "sl_tags": "",
}

SAMPLE_NO_CITY: Dict[str, Any] = {
    "sl_id": "202",
    "sl_store": "Missing City Pantry",
    "sl_address": "100 Some Rd",
    "sl_city": "",
    "sl_state": "MI",
    "sl_zip": "48501",
    "sl_latitude": "43.0125",
    "sl_longitude": "-83.6875",
    "sl_phone": "",
    "sl_hours": "",
    "sl_email": "",
    "sl_url": "",
    "sl_description": "",
    "sl_tags": "",
}

SAMPLE_INVALID_COORDS: Dict[str, Any] = {
    "sl_id": "203",
    "sl_store": "Bad Coords Pantry",
    "sl_address": "200 Oak Ave",
    "sl_city": "Midland",
    "sl_state": "MI",
    "sl_zip": "48640",
    "sl_latitude": "invalid",
    "sl_longitude": "bad",
    "sl_phone": "",
    "sl_hours": "",
    "sl_email": "",
    "sl_url": "",
    "sl_description": "",
    "sl_tags": "",
}

SAMPLE_PAGES_URL: Dict[str, Any] = {
    "sl_id": "204",
    "sl_store": "Pages URL Pantry",
    "sl_address": "300 Elm St",
    "sl_city": "Lapeer",
    "sl_state": "MI",
    "sl_zip": "48446",
    "sl_latitude": "43.0514",
    "sl_longitude": "-83.3188",
    "sl_phone": "",
    "sl_hours": "",
    "sl_email": "",
    "sl_url": "",
    "sl_pages_url": "https://pages.example.com/pantry",
    "sl_description": "",
    "sl_tags": "",
}


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    assert scraper.scraper_id == "food_bank_of_eastern_michigan_mi"
    assert "fbem.org" in scraper.api_url
    assert scraper.test_mode is False


def test_scraper_init_test_mode() -> None:
    """Test scraper initializes with test_mode enabled."""
    scraper = FoodBankOfEasternMichiganMiScraper(test_mode=True)
    assert scraper.test_mode is True


def test_scraper_init_custom_id() -> None:
    """Test scraper accepts custom scraper_id."""
    scraper = FoodBankOfEasternMichiganMiScraper(scraper_id="custom_id")
    assert scraper.scraper_id == "custom_id"


def test_parse_location_full_details() -> None:
    """Test parse_location with all fields populated."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_LOCATION_DETAIL)

    assert location is not None
    assert location["name"] == "Flint Community Food Bank"
    assert location["address"] == "123 Main St Suite 200"
    assert location["city"] == "Flint"
    assert location["state"] == "MI"
    assert location["zip"] == "48501"
    assert location["phone"] == "(810) 555-1234"
    assert location["hours"] == "Mon-Fri 9am-5pm"
    assert location["email"] == "info@flintfoodbank.org"
    assert location["website"] == "https://www.flintfoodbank.org"
    assert location["notes"] == "Food assistance for Genesee County residents"
    assert location["tags"] == "pantry,snap"
    assert location["latitude"] == 43.0125
    assert location["longitude"] == -83.6875


def test_parse_location_minimal() -> None:
    """Test parse_location with only required fields."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_MINIMAL_LOCATION)

    assert location is not None
    assert location["name"] == "Saginaw Pantry"
    assert location["address"] == "456 State St"
    assert location["city"] == "Saginaw"
    assert location["state"] == "MI"
    assert location["zip"] == "48601"
    # Optional fields should not be present when empty
    assert "phone" not in location
    assert "hours" not in location
    assert "email" not in location
    assert "website" not in location
    assert "notes" not in location
    assert "tags" not in location


def test_parse_location_no_name_returns_none() -> None:
    """Test location with empty name is skipped."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_NO_NAME)
    assert location is None


def test_parse_location_no_address_returns_none() -> None:
    """Test location with empty address is skipped."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_NO_ADDRESS)
    assert location is None


def test_parse_location_no_city_returns_none() -> None:
    """Test location with empty city is skipped."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_NO_CITY)
    assert location is None


def test_parse_location_invalid_coordinates() -> None:
    """Test invalid coordinates are handled gracefully."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_INVALID_COORDS)

    assert location is not None
    assert "latitude" not in location
    assert "longitude" not in location


def test_parse_location_missing_coordinates() -> None:
    """Test empty coordinates are handled gracefully."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    record = {**SAMPLE_LOCATION_DETAIL, "sl_latitude": "", "sl_longitude": ""}
    location = scraper.parse_location(record)

    assert location is not None
    assert "latitude" not in location
    assert "longitude" not in location


def test_parse_location_pages_url_fallback() -> None:
    """Test sl_pages_url is used when sl_url is empty."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_PAGES_URL)

    assert location is not None
    assert location["website"] == "https://pages.example.com/pantry"


def test_parse_location_default_state() -> None:
    """Test default state is MI when sl_state is missing."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    record = {**SAMPLE_LOCATION_DETAIL}
    del record["sl_state"]
    location = scraper.parse_location(record)

    assert location is not None
    assert location["state"] == "MI"


def test_parse_location_state_trimming() -> None:
    """Test trailing whitespace on state field is trimmed."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    record = {**SAMPLE_LOCATION_DETAIL, "sl_state": "MI "}
    location = scraper.parse_location(record)

    assert location is not None
    assert location["state"] == "MI"


def test_parse_location_address2_combined() -> None:
    """Test address and address2 are combined with space."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_LOCATION_DETAIL)

    assert location is not None
    assert location["address"] == "123 Main St Suite 200"


def test_parse_location_no_address2() -> None:
    """Test address without address2 is just the primary address."""
    scraper = FoodBankOfEasternMichiganMiScraper()
    location = scraper.parse_location(SAMPLE_MINIMAL_LOCATION)

    assert location is not None
    assert location["address"] == "456 State St"


async def test_fetch_location_ids_success() -> None:
    """Test successful fetch of location IDs."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = SAMPLE_LOCATION_LIST

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        ids = await scraper.fetch_location_ids()

    assert ids == ["101", "102", "103"]
    mock_client.get.assert_called_once_with(scraper.api_url)


async def test_fetch_location_ids_filters_missing_sl_id() -> None:
    """Test location IDs without sl_id field are filtered out."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    data_with_missing = [
        {"sl_id": "101"},
        {"other_field": "no_id"},
        {"sl_id": "103"},
    ]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = data_with_missing

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        ids = await scraper.fetch_location_ids()

    assert ids == ["101", "103"]


async def test_fetch_location_ids_http_error() -> None:
    """Test HTTP error is propagated when fetching IDs."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Server error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPError):
            await scraper.fetch_location_ids()


async def test_fetch_location_details_success() -> None:
    """Test successful fetch of location details."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = SAMPLE_LOCATION_DETAIL

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await scraper.fetch_location_details("101")

    assert result == SAMPLE_LOCATION_DETAIL
    mock_client.get.assert_called_once_with(f"{scraper.api_url}/101")


async def test_fetch_location_details_http_error_returns_none() -> None:
    """Test HTTP error returns None instead of raising."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Not found"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await scraper.fetch_location_details("999")

    assert result is None


async def test_scrape_full_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full scrape workflow: fetch IDs, fetch details, submit to queue."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch_ids() -> list[str]:
        return ["101", "102"]

    monkeypatch.setattr(scraper, "fetch_location_ids", mock_fetch_ids)

    call_count = 0

    async def mock_fetch_details(location_id: str) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if location_id == "101":
            return SAMPLE_LOCATION_DETAIL
        return SAMPLE_MINIMAL_LOCATION

    monkeypatch.setattr(scraper, "fetch_location_details", mock_fetch_details)

    result = await scraper.scrape()

    assert len(submitted_jobs) == 2
    assert call_count == 2

    # Verify first submitted job
    job_1 = json.loads(submitted_jobs[0])
    assert job_1["name"] == "Flint Community Food Bank"
    assert job_1["source"] == "food_bank_of_eastern_michigan_mi"
    assert job_1["food_bank"] == "Food Bank of Eastern Michigan"

    # Verify second submitted job
    job_2 = json.loads(submitted_jobs[1])
    assert job_2["name"] == "Saginaw Pantry"
    assert job_2["source"] == "food_bank_of_eastern_michigan_mi"

    # Verify summary
    summary = json.loads(result)
    assert summary["scraper_id"] == "food_bank_of_eastern_michigan_mi"
    assert summary["food_bank"] == "Food Bank of Eastern Michigan"
    assert summary["total_locations_found"] == 2
    assert summary["successfully_parsed"] == 2
    assert summary["total_jobs_created"] == 2


async def test_scrape_skips_invalid_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that scrape skips locations with missing name or address."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch_ids() -> list[str]:
        return ["101", "200", "201"]

    monkeypatch.setattr(scraper, "fetch_location_ids", mock_fetch_ids)

    details_map = {
        "101": SAMPLE_LOCATION_DETAIL,
        "200": SAMPLE_NO_NAME,
        "201": SAMPLE_NO_ADDRESS,
    }

    async def mock_fetch_details(location_id: str) -> Dict[str, Any]:
        return details_map[location_id]

    monkeypatch.setattr(scraper, "fetch_location_details", mock_fetch_details)

    result = await scraper.scrape()

    # Only one valid location should be submitted
    assert len(submitted_jobs) == 1
    job = json.loads(submitted_jobs[0])
    assert job["name"] == "Flint Community Food Bank"

    summary = json.loads(result)
    assert summary["total_locations_found"] == 3
    assert summary["successfully_parsed"] == 1
    assert summary["total_jobs_created"] == 1


async def test_scrape_test_mode_limits_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that test_mode limits processing to first 5 locations."""
    scraper = FoodBankOfEasternMichiganMiScraper(test_mode=True)

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    # Return 10 IDs
    async def mock_fetch_ids() -> list[str]:
        return [str(i) for i in range(10)]

    monkeypatch.setattr(scraper, "fetch_location_ids", mock_fetch_ids)

    async def mock_fetch_details(location_id: str) -> Dict[str, Any]:
        return {
            **SAMPLE_LOCATION_DETAIL,
            "sl_id": location_id,
            "sl_store": f"Pantry {location_id}",
        }

    monkeypatch.setattr(scraper, "fetch_location_details", mock_fetch_details)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Test mode should limit to 5
    assert summary["total_locations_found"] == 5
    assert summary["total_jobs_created"] == 5
    assert summary["test_mode"] is True
    assert len(submitted_jobs) == 5


async def test_scrape_handles_failed_detail_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scrape continues when individual location detail fetch fails."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch_ids() -> list[str]:
        return ["101", "999", "102"]

    monkeypatch.setattr(scraper, "fetch_location_ids", mock_fetch_ids)

    async def mock_fetch_details(location_id: str) -> Any:
        if location_id == "999":
            return None  # Simulates failed fetch
        if location_id == "101":
            return SAMPLE_LOCATION_DETAIL
        return SAMPLE_MINIMAL_LOCATION

    monkeypatch.setattr(scraper, "fetch_location_details", mock_fetch_details)

    result = await scraper.scrape()

    # Two valid locations should be submitted (failed one skipped)
    assert len(submitted_jobs) == 2
    summary = json.loads(result)
    assert summary["total_locations_found"] == 3
    assert summary["successfully_parsed"] == 2
    assert summary["total_jobs_created"] == 2


async def test_scrape_empty_location_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scraper handles empty location list gracefully."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch_ids() -> list[str]:
        return []

    monkeypatch.setattr(scraper, "fetch_location_ids", mock_fetch_ids)

    result = await scraper.scrape()

    assert len(submitted_jobs) == 0
    summary = json.loads(result)
    assert summary["total_locations_found"] == 0
    assert summary["successfully_parsed"] == 0
    assert summary["total_jobs_created"] == 0


async def test_scrape_preserves_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test latitude and longitude are preserved in submitted data."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch_ids() -> list[str]:
        return ["101"]

    monkeypatch.setattr(scraper, "fetch_location_ids", mock_fetch_ids)

    async def mock_fetch_details(location_id: str) -> Dict[str, Any]:
        return SAMPLE_LOCATION_DETAIL

    monkeypatch.setattr(scraper, "fetch_location_details", mock_fetch_details)

    await scraper.scrape()

    location = json.loads(submitted_jobs[0])
    assert location["latitude"] == 43.0125
    assert location["longitude"] == -83.6875


async def test_scrape_metadata_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test source and food_bank metadata are set correctly."""
    scraper = FoodBankOfEasternMichiganMiScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch_ids() -> list[str]:
        return ["101"]

    monkeypatch.setattr(scraper, "fetch_location_ids", mock_fetch_ids)

    async def mock_fetch_details(location_id: str) -> Dict[str, Any]:
        return SAMPLE_LOCATION_DETAIL

    monkeypatch.setattr(scraper, "fetch_location_details", mock_fetch_details)

    await scraper.scrape()

    assert len(submitted_jobs) == 1
    location = json.loads(submitted_jobs[0])
    assert location["source"] == "food_bank_of_eastern_michigan_mi"
    assert location["food_bank"] == "Food Bank of Eastern Michigan"
