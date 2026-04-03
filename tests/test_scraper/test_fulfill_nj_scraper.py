"""Tests for Fulfill NJ scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.fulfill_nj_scraper import FulfillNjScraper


SAMPLE_STORE_VALID: dict[str, Any] = {
    "id": "101",
    "title": "St. Mark's Food Pantry",
    "street": "247 Carr Ave",
    "city": "Keansburg",
    "state": "NJ",
    "postal_code": "07734",
    "lat": "40.4418",
    "lng": "-74.1299",
    "phone": "(732) 555-1234",
    "description_2": "Monday 10am-12pm, Wednesday 5pm-7pm",
    "description": "Serves Keansburg and surrounding areas",
    "categories": "Food Pantry",
}

SAMPLE_STORE_VALID_2: dict[str, Any] = {
    "id": "202",
    "title": "Ocean Township Community Center",
    "street": "75 Davis Ave",
    "city": "Ocean Township",
    "state": "NJ",
    "postal_code": "07712",
    "lat": "40.2542",
    "lng": "-74.0291",
    "phone": "(732) 555-5678",
    "description_2": "Thursday 9am-11am",
    "description": "",
    "categories": "Food Distribution",
}

SAMPLE_STORE_NO_TITLE: dict[str, Any] = {
    "id": "303",
    "title": "",
    "street": "100 Main St",
    "city": "Asbury Park",
    "state": "NJ",
    "postal_code": "07712",
    "lat": "40.2201",
    "lng": "-74.0121",
}

SAMPLE_STORE_MISSING_TITLE: dict[str, Any] = {
    "id": "404",
    "street": "200 Broadway",
    "city": "Long Branch",
    "state": "NJ",
    "postal_code": "07740",
}

SAMPLE_STORE_NO_COORDS: dict[str, Any] = {
    "id": "505",
    "title": "No Coords Pantry",
    "street": "300 Ocean Ave",
    "city": "Belmar",
    "state": "NJ",
    "postal_code": "07719",
    "lat": "",
    "lng": "",
    "phone": "",
    "description_2": "",
    "description": "",
    "categories": "",
}


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FulfillNjScraper()
    assert scraper.scraper_id == "fulfill_nj"
    assert "fulfillnj.org" in scraper.api_url
    assert "asl_load_stores" in scraper.api_url


def test_is_valid_accepts_valid_store() -> None:
    """Test _is_valid returns True for stores with a title."""
    scraper = FulfillNjScraper()
    assert scraper._is_valid(SAMPLE_STORE_VALID) is True


def test_is_valid_rejects_empty_title() -> None:
    """Test _is_valid filters out stores with empty title."""
    scraper = FulfillNjScraper()
    assert scraper._is_valid(SAMPLE_STORE_NO_TITLE) is False


def test_is_valid_rejects_missing_title() -> None:
    """Test _is_valid filters out stores without a title key."""
    scraper = FulfillNjScraper()
    assert scraper._is_valid(SAMPLE_STORE_MISSING_TITLE) is False


def test_is_valid_rejects_whitespace_title() -> None:
    """Test _is_valid filters out stores with whitespace-only title."""
    scraper = FulfillNjScraper()
    store = {**SAMPLE_STORE_VALID, "title": "   "}
    assert scraper._is_valid(store) is False


def test_parse_location_full_data() -> None:
    """Test parsing a store with all fields populated."""
    scraper = FulfillNjScraper()
    loc = scraper._parse_location(SAMPLE_STORE_VALID)

    assert loc["name"] == "St. Mark's Food Pantry"
    assert loc["address"] == "247 Carr Ave"
    assert loc["city"] == "Keansburg"
    assert loc["state"] == "NJ"
    assert loc["zip"] == "07734"
    assert loc["phone"] == "(732) 555-1234"
    assert loc["latitude"] == 40.4418
    assert loc["longitude"] == -74.1299
    assert loc["hours"] == "Monday 10am-12pm, Wednesday 5pm-7pm"
    assert loc["description"] == "Serves Keansburg and surrounding areas"
    assert loc["categories"] == "Food Pantry"
    assert loc["source"] == "fulfill_nj"
    assert loc["food_bank"] == "Fulfill"


def test_parse_location_empty_coords() -> None:
    """Test parsing handles empty coordinate strings."""
    scraper = FulfillNjScraper()
    loc = scraper._parse_location(SAMPLE_STORE_NO_COORDS)

    assert loc["latitude"] is None
    assert loc["longitude"] is None
    assert loc["name"] == "No Coords Pantry"


def test_parse_location_none_coords() -> None:
    """Test parsing handles None coordinates."""
    scraper = FulfillNjScraper()
    store = {**SAMPLE_STORE_VALID, "lat": None, "lng": None}
    loc = scraper._parse_location(store)

    assert loc["latitude"] is None
    assert loc["longitude"] is None


def test_parse_location_invalid_coords() -> None:
    """Test parsing handles non-numeric coordinate strings."""
    scraper = FulfillNjScraper()
    store = {**SAMPLE_STORE_VALID, "lat": "invalid", "lng": "bad"}
    loc = scraper._parse_location(store)

    assert loc["latitude"] is None
    assert loc["longitude"] is None


def test_parse_location_defaults_state_to_nj() -> None:
    """Test parsing defaults empty state to NJ."""
    scraper = FulfillNjScraper()
    store = {**SAMPLE_STORE_VALID, "state": ""}
    loc = scraper._parse_location(store)

    assert loc["state"] == "NJ"


async def test_fetch_stores_success() -> None:
    """Test successful store data fetch."""
    scraper = FulfillNjScraper()
    expected_data = [SAMPLE_STORE_VALID, SAMPLE_STORE_VALID_2]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = expected_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await scraper._fetch_stores(mock_client)

    assert result == expected_data
    mock_client.get.assert_called_once()


async def test_fetch_stores_retry_on_failure() -> None:
    """Test retry logic when first attempt fails."""
    scraper = FulfillNjScraper()
    scraper.retry_delay = 0.01

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [SAMPLE_STORE_VALID]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[httpx.HTTPError("Server error"), mock_response]
    )

    result = await scraper._fetch_stores(mock_client)

    assert result == [SAMPLE_STORE_VALID]
    assert mock_client.get.call_count == 2


async def test_fetch_stores_all_retries_exhausted() -> None:
    """Test that exception is raised when all retries fail."""
    scraper = FulfillNjScraper()
    scraper.retry_delay = 0.01
    scraper.max_retries = 2

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Server error"))

    with pytest.raises(httpx.HTTPError):
        await scraper._fetch_stores(mock_client)

    assert mock_client.get.call_count == 2


async def test_scrape_submits_valid_stores_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that scrape submits only valid stores."""
    scraper = FulfillNjScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return [
            SAMPLE_STORE_VALID,
            SAMPLE_STORE_VALID_2,
            SAMPLE_STORE_NO_TITLE,
            SAMPLE_STORE_MISSING_TITLE,
        ]

    monkeypatch.setattr(scraper, "_fetch_stores", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Only 2 valid stores should be submitted
    assert len(submitted_jobs) == 2
    assert summary["total_jobs_created"] == 2
    assert summary["valid_locations"] == 2
    assert summary["total_fetched"] == 4

    # Verify submitted data
    job_1 = json.loads(submitted_jobs[0])
    assert job_1["name"] == "St. Mark's Food Pantry"
    assert job_1["source"] == "fulfill_nj"
    assert job_1["food_bank"] == "Fulfill"

    job_2 = json.loads(submitted_jobs[1])
    assert job_2["name"] == "Ocean Township Community Center"


async def test_scrape_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scraper handles empty API response."""
    scraper = FulfillNjScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(scraper, "_fetch_stores", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert len(submitted_jobs) == 0
    assert summary["total_fetched"] == 0
    assert summary["total_jobs_created"] == 0


async def test_scrape_summary_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that scrape returns a valid JSON summary."""
    scraper = FulfillNjScraper()

    def mock_submit(content: str) -> str:
        return "job-1"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return [SAMPLE_STORE_VALID]

    monkeypatch.setattr(scraper, "_fetch_stores", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "fulfill_nj"
    assert summary["food_bank"] == "Fulfill"
    assert summary["source"] == "https://fulfillnj.org"
    assert "total_fetched" in summary
    assert "valid_locations" in summary
    assert "total_jobs_created" in summary
