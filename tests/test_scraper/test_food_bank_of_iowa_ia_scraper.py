"""Tests for Food Bank of Iowa scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.food_bank_of_iowa_ia_scraper import (
    API_URL,
    FoodBankOfIowaIaScraper,
)


SAMPLE_PANTRY: dict[str, Any] = {
    "id": "1",
    "name": "Des Moines Area Religious Council",
    "street": "1435 Mulberry St",
    "city": "Des Moines",
    "state": "IA",
    "postalcode": "50309",
    "latitude": "41.5868",
    "longitude": "-93.6350",
    "county": "Polk",
    "phone": "(515) 277-6969",
    "category": "pantry",
    "website": "https://www.dmreligious.org",
    "fbo": "true",
    "delivery": "false",
}

SAMPLE_MOBILE: dict[str, Any] = {
    "id": "2",
    "name": "Mobile Food Pantry - Ames",
    "street": "2321 N Loop Dr",
    "city": "Ames",
    "state": "IA",
    "postalcode": "50010",
    "latitude": "42.0347",
    "longitude": "-93.6199",
    "county": "Story",
    "phone": "(515) 232-4300",
    "category": "mobile-distribution",
    "website": "",
    "fbo": "false",
    "delivery": "true",
}

SAMPLE_MEAL_SITE: dict[str, Any] = {
    "id": "3",
    "name": "Central Iowa Shelter & Services",
    "street": "1420 Mulberry St",
    "city": "Des Moines",
    "state": "IA",
    "postalcode": "50309",
    "latitude": "41.5870",
    "longitude": "-93.6348",
    "county": "Polk",
    "phone": "(515) 284-5719",
    "category": "meal-site",
    "website": "https://www.centraliowashelter.org",
    "fbo": "false",
    "delivery": "false",
}

SAMPLE_TRAILING_SPACE_STATE: dict[str, Any] = {
    "id": "4",
    "name": "Ottumwa Food Pantry",
    "street": "106 S Court St",
    "city": "Ottumwa",
    "state": "IA ",
    "postalcode": "52501",
    "latitude": "41.0178",
    "longitude": "-92.4113",
    "county": "Wapello",
    "phone": "(641) 682-1410",
    "category": "pantry",
    "website": "",
    "fbo": "false",
    "delivery": "false",
}

SAMPLE_NO_NAME: dict[str, Any] = {
    "id": "5",
    "name": "",
    "street": "999 Unknown St",
    "city": "Nowhere",
    "state": "IA",
    "postalcode": "50000",
    "latitude": "",
    "longitude": "",
    "county": "",
    "phone": "",
    "category": "",
    "website": "",
    "fbo": "false",
    "delivery": "false",
}

SAMPLE_NO_ADDRESS: dict[str, Any] = {
    "id": "6",
    "name": "No Address Pantry",
    "street": "",
    "city": "Des Moines",
    "state": "IA",
    "postalcode": "50309",
    "latitude": "41.5868",
    "longitude": "-93.6350",
    "county": "Polk",
    "phone": "(515) 555-0000",
    "category": "pantry",
    "website": "",
    "fbo": "false",
    "delivery": "false",
}


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FoodBankOfIowaIaScraper()
    assert scraper.scraper_id == "food_bank_of_iowa_ia"
    assert scraper.api_url == API_URL
    assert scraper.test_mode is False


def test_scraper_init_test_mode() -> None:
    """Test scraper initializes with test_mode enabled."""
    scraper = FoodBankOfIowaIaScraper(test_mode=True)
    assert scraper.test_mode is True


def test_build_location_pantry() -> None:
    """Test _build_location with a standard pantry record."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_PANTRY)

    assert location is not None
    assert location["name"] == "Des Moines Area Religious Council"
    assert location["address"] == "1435 Mulberry St"
    assert location["city"] == "Des Moines"
    assert location["state"] == "IA"
    assert location["zip"] == "50309"
    assert location["county"] == "Polk"
    assert location["phone"] == "(515) 277-6969"
    assert location["website"] == "https://www.dmreligious.org"
    assert location["services"] == ["pantry"]
    assert location["latitude"] == 41.5868
    assert location["longitude"] == -93.6350
    assert location["source"] == "food_bank_of_iowa_ia"
    assert location["food_bank"] == "Food Bank of Iowa"


def test_build_location_fbo_true() -> None:
    """Test fbo field is included as metadata when 'true'."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_PANTRY)

    assert location is not None
    assert location["fbo_member"] is True


def test_build_location_fbo_false() -> None:
    """Test fbo field is omitted when 'false'."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_MOBILE)

    assert location is not None
    assert "fbo_member" not in location


def test_build_location_delivery_true() -> None:
    """Test delivery field is included as metadata when 'true'."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_MOBILE)

    assert location is not None
    assert location["delivery_available"] is True


def test_build_location_delivery_false() -> None:
    """Test delivery field is omitted when 'false'."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_PANTRY)

    assert location is not None
    assert "delivery_available" not in location


def test_build_location_category_mapping() -> None:
    """Test different category values are mapped to services."""
    scraper = FoodBankOfIowaIaScraper()

    mobile = scraper._build_location(SAMPLE_MOBILE)
    assert mobile is not None
    assert mobile["services"] == ["mobile-distribution"]

    meal = scraper._build_location(SAMPLE_MEAL_SITE)
    assert meal is not None
    assert meal["services"] == ["meal-site"]


def test_build_location_empty_category() -> None:
    """Test empty category results in empty services list."""
    scraper = FoodBankOfIowaIaScraper()
    record = {**SAMPLE_PANTRY, "category": ""}
    location = scraper._build_location(record)

    assert location is not None
    assert location["services"] == []


def test_build_location_state_trimming() -> None:
    """Test trailing whitespace on state field is trimmed."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_TRAILING_SPACE_STATE)

    assert location is not None
    assert location["state"] == "IA"
    assert location["name"] == "Ottumwa Food Pantry"


def test_build_location_no_name_returns_none() -> None:
    """Test record with empty name is skipped."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_NO_NAME)
    assert location is None


def test_build_location_no_address_returns_none() -> None:
    """Test record with empty address is skipped."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_NO_ADDRESS)
    assert location is None


def test_build_location_empty_website() -> None:
    """Test empty website is stored as empty string."""
    scraper = FoodBankOfIowaIaScraper()
    location = scraper._build_location(SAMPLE_MOBILE)

    assert location is not None
    assert location["website"] == ""


def test_build_location_invalid_coordinates() -> None:
    """Test invalid coordinates are handled gracefully."""
    scraper = FoodBankOfIowaIaScraper()
    record = {**SAMPLE_PANTRY, "latitude": "invalid", "longitude": "bad"}
    location = scraper._build_location(record)

    assert location is not None
    assert "latitude" not in location
    assert "longitude" not in location


def test_build_location_missing_coordinates() -> None:
    """Test missing coordinates are handled gracefully."""
    scraper = FoodBankOfIowaIaScraper()
    record = {**SAMPLE_PANTRY, "latitude": "", "longitude": ""}
    location = scraper._build_location(record)

    assert location is not None
    assert "latitude" not in location
    assert "longitude" not in location


async def test_fetch_data_success() -> None:
    """Test successful data fetch from API."""
    scraper = FoodBankOfIowaIaScraper()
    expected_data = [SAMPLE_PANTRY, SAMPLE_MOBILE]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = expected_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    import httpx as httpx_module
    from unittest.mock import patch

    with patch.object(httpx_module, "AsyncClient", return_value=mock_client):
        result = await scraper._fetch_data()

    assert result == expected_data
    mock_client.get.assert_called_once()


async def test_fetch_data_retry_on_failure() -> None:
    """Test retry logic when first attempt fails."""
    scraper = FoodBankOfIowaIaScraper()
    scraper.retry_delay = 0.01  # Speed up test

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [SAMPLE_PANTRY]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[httpx.HTTPError("Server error"), mock_response]
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    import httpx as httpx_module
    from unittest.mock import patch

    with patch.object(httpx_module, "AsyncClient", return_value=mock_client):
        result = await scraper._fetch_data()

    assert result == [SAMPLE_PANTRY]
    assert mock_client.get.call_count == 2


async def test_fetch_data_all_retries_exhausted() -> None:
    """Test that exception is raised when all retries fail."""
    scraper = FoodBankOfIowaIaScraper()
    scraper.retry_delay = 0.01
    scraper.max_retries = 2

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Server error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    import httpx as httpx_module
    from unittest.mock import patch

    with patch.object(httpx_module, "AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPError):
            await scraper._fetch_data()

    assert mock_client.get.call_count == 2


async def test_scrape_submits_valid_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that scrape submits only valid locations to the queue."""
    scraper = FoodBankOfIowaIaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch() -> list[dict[str, Any]]:
        return [SAMPLE_PANTRY, SAMPLE_MOBILE, SAMPLE_NO_NAME, SAMPLE_NO_ADDRESS]

    monkeypatch.setattr(scraper, "_fetch_data", mock_fetch)

    result = await scraper.scrape()

    # Only 2 valid locations should be submitted (no_name and no_address skipped)
    assert len(submitted_jobs) == 2

    # Verify submitted data
    job_1 = json.loads(submitted_jobs[0])
    assert job_1["name"] == "Des Moines Area Religious Council"
    assert job_1["source"] == "food_bank_of_iowa_ia"
    assert job_1["food_bank"] == "Food Bank of Iowa"

    job_2 = json.loads(submitted_jobs[1])
    assert job_2["name"] == "Mobile Food Pantry - Ames"

    # Verify summary
    summary = json.loads(result)
    assert summary["total_submitted"] == 2
    assert summary["total_skipped"] == 2
    assert summary["total_fetched"] == 4


async def test_scrape_test_mode_limits_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that test_mode limits processing to 5 records."""
    scraper = FoodBankOfIowaIaScraper(test_mode=True)

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    # Create 10 valid records
    many_records = []
    for i in range(10):
        record = {
            **SAMPLE_PANTRY,
            "id": str(i),
            "name": f"Pantry {i}",
        }
        many_records.append(record)

    async def mock_fetch() -> list[dict[str, Any]]:
        return many_records

    monkeypatch.setattr(scraper, "_fetch_data", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Test mode should limit to 5
    assert summary["total_submitted"] == 5
    assert summary["total_fetched"] == 5
    assert summary["test_mode"] is True


async def test_scrape_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scraper handles empty API response."""
    scraper = FoodBankOfIowaIaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch() -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(scraper, "_fetch_data", mock_fetch)

    result = await scraper.scrape()

    assert len(submitted_jobs) == 0
    summary = json.loads(result)
    assert summary["total_submitted"] == 0
    assert summary["total_fetched"] == 0


async def test_scrape_metadata_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that metadata fields (source, food_bank) are set correctly."""
    scraper = FoodBankOfIowaIaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch() -> list[dict[str, Any]]:
        return [SAMPLE_PANTRY]

    monkeypatch.setattr(scraper, "_fetch_data", mock_fetch)

    await scraper.scrape()

    assert len(submitted_jobs) == 1
    location = json.loads(submitted_jobs[0])
    assert location["source"] == "food_bank_of_iowa_ia"
    assert location["food_bank"] == "Food Bank of Iowa"


async def test_scrape_preserves_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that latitude and longitude are preserved in submitted data."""
    scraper = FoodBankOfIowaIaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch() -> list[dict[str, Any]]:
        return [SAMPLE_PANTRY]

    monkeypatch.setattr(scraper, "_fetch_data", mock_fetch)

    await scraper.scrape()

    location = json.loads(submitted_jobs[0])
    assert location["latitude"] == 41.5868
    assert location["longitude"] == -93.6350


async def test_scrape_state_trimming_in_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that state field with trailing space is trimmed in full workflow."""
    scraper = FoodBankOfIowaIaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch() -> list[dict[str, Any]]:
        return [SAMPLE_TRAILING_SPACE_STATE]

    monkeypatch.setattr(scraper, "_fetch_data", mock_fetch)

    await scraper.scrape()

    assert len(submitted_jobs) == 1
    location = json.loads(submitted_jobs[0])
    assert location["state"] == "IA"
    assert not location["state"].endswith(" ")
