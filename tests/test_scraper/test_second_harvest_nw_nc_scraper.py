"""Tests for Second Harvest Food Bank of Northwest NC scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.second_harvest_nw_nc_scraper import (
    ID_PREFIX_PATTERN,
    SecondHarvestNwNcScraper,
    clean_name,
)


# --- Sample API responses using short field names ---

SAMPLE_PANTRY: dict[str, Any] = {
    "n": "Grace Community Food Pantry",
    "a": "100 Main Street",
    "c": "Winston-Salem",
    "s": "NC",
    "z": "27101",
    "p": "(336) 555-1234",
    "t": "PANTRY",
    "h": "Mon 9am-12pm, Wed 1pm-4pm",
}

SAMPLE_SOUP_KITCHEN: dict[str, Any] = {
    "n": "Downtown Soup Kitchen",
    "a": "200 Elm Street",
    "c": "Greensboro",
    "s": "NC",
    "z": "27401",
    "p": "(336) 555-5678",
    "t": "SOUP KITCHEN",
    "h": "Mon-Fri 11am-1pm",
}

SAMPLE_WITH_ID_PREFIX: dict[str, Any] = {
    "n": "1155EMP01 Northside Food Pantry",
    "a": "300 Oak Avenue",
    "c": "High Point",
    "s": "NC",
    "z": "27260",
    "p": "(336) 555-9012",
    "t": "PANTRY",
    "h": "Tue & Thu 10am-2pm",
}

SAMPLE_EMPTY_NAME: dict[str, Any] = {
    "n": "",
    "a": "400 Pine Road",
    "c": "Kernersville",
    "s": "NC",
    "z": "27284",
    "p": "",
    "t": "PANTRY",
    "h": "",
}

SAMPLE_MISSING_NAME: dict[str, Any] = {
    "a": "500 Maple Lane",
    "c": "Lexington",
    "s": "NC",
    "z": "27292",
    "p": "",
    "t": "PANTRY",
    "h": "",
}


def test_scraper_initialization() -> None:
    """Test scraper initializes with correct parameters."""
    scraper = SecondHarvestNwNcScraper()
    assert scraper.scraper_id == "second_harvest_nw_nc"
    assert "foodfinder.secondharvestnwnc.org" in scraper.source_url
    assert scraper.test_mode is False


def test_scraper_initialization_test_mode() -> None:
    """Test scraper initializes correctly in test mode."""
    scraper = SecondHarvestNwNcScraper(test_mode=True)
    assert scraper.test_mode is True


def test_clean_name_strips_id_prefix() -> None:
    """Test that ID prefixes are stripped from names."""
    assert clean_name("1155EMP01 Northside Food Pantry") == "Northside Food Pantry"
    assert clean_name("2200ABC99 Community Kitchen") == "Community Kitchen"
    assert clean_name("9999XYZ01 Grace Church Pantry") == "Grace Church Pantry"


def test_clean_name_preserves_normal_names() -> None:
    """Test that names without ID prefixes are unchanged."""
    assert clean_name("Grace Community Food Pantry") == "Grace Community Food Pantry"
    assert clean_name("Downtown Soup Kitchen") == "Downtown Soup Kitchen"
    assert clean_name("St. Mary's Food Bank") == "St. Mary's Food Bank"


def test_clean_name_handles_edge_cases() -> None:
    """Test clean_name with empty/whitespace strings."""
    assert clean_name("") == ""
    assert clean_name("   ") == ""


def test_id_prefix_pattern() -> None:
    """Test the ID prefix regex directly."""
    assert ID_PREFIX_PATTERN.match("1155EMP01 Foo") is not None
    assert ID_PREFIX_PATTERN.match("2200ABC99 Bar") is not None
    assert ID_PREFIX_PATTERN.match("Grace Community") is None
    assert ID_PREFIX_PATTERN.match("123 Main St Pantry") is None


def test_parse_location_pantry() -> None:
    """Test parsing a pantry location from API data."""
    scraper = SecondHarvestNwNcScraper()
    result = scraper._parse_location(SAMPLE_PANTRY)

    assert result is not None
    assert result["name"] == "Grace Community Food Pantry"
    assert result["address"] == "100 Main Street"
    assert result["city"] == "Winston-Salem"
    assert result["state"] == "NC"
    assert result["zip"] == "27101"
    assert result["phone"] == "(336) 555-1234"
    assert result["type"] == "PANTRY"
    assert result["hours"] == "Mon 9am-12pm, Wed 1pm-4pm"
    assert "Food Pantry" in result["services"]
    assert result["full_address"] == "100 Main Street, Winston-Salem, NC, 27101"


def test_parse_location_soup_kitchen() -> None:
    """Test parsing a soup kitchen location from API data."""
    scraper = SecondHarvestNwNcScraper()
    result = scraper._parse_location(SAMPLE_SOUP_KITCHEN)

    assert result is not None
    assert result["name"] == "Downtown Soup Kitchen"
    assert "Soup Kitchen" in result["services"]
    assert "Food Pantry" not in result["services"]


def test_parse_location_strips_id_prefix() -> None:
    """Test that ID prefixes are stripped during parsing."""
    scraper = SecondHarvestNwNcScraper()
    result = scraper._parse_location(SAMPLE_WITH_ID_PREFIX)

    assert result is not None
    assert result["name"] == "Northside Food Pantry"
    assert "1155EMP01" not in result["name"]


def test_parse_location_empty_name_returns_none() -> None:
    """Test that empty name results in None (filtered out)."""
    scraper = SecondHarvestNwNcScraper()
    result = scraper._parse_location(SAMPLE_EMPTY_NAME)
    assert result is None


def test_parse_location_missing_name_returns_none() -> None:
    """Test that missing name field results in None."""
    scraper = SecondHarvestNwNcScraper()
    result = scraper._parse_location(SAMPLE_MISSING_NAME)
    assert result is None


def test_parse_location_defaults_state_to_nc() -> None:
    """Test that state defaults to NC when not provided."""
    scraper = SecondHarvestNwNcScraper()
    record: dict[str, Any] = {"n": "Test Pantry", "a": "123 Test St", "c": "Elkin"}
    result = scraper._parse_location(record)
    assert result is not None
    assert result["state"] == "NC"


async def test_fetch_locations_success() -> None:
    """Test successful API fetch."""
    scraper = SecondHarvestNwNcScraper()
    expected_data = [SAMPLE_PANTRY, SAMPLE_SOUP_KITCHEN]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = expected_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await scraper._fetch_locations(mock_client)

    assert result == expected_data
    mock_client.get.assert_called_once()


async def test_fetch_locations_retry_on_failure() -> None:
    """Test retry logic when first attempt fails."""
    scraper = SecondHarvestNwNcScraper()
    scraper.retry_delay = 0.01  # Speed up test

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [SAMPLE_PANTRY]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[httpx.HTTPError("Server error"), mock_response]
    )

    result = await scraper._fetch_locations(mock_client)

    assert result == [SAMPLE_PANTRY]
    assert mock_client.get.call_count == 2


async def test_fetch_locations_all_retries_exhausted() -> None:
    """Test that exception is raised when all retries fail."""
    scraper = SecondHarvestNwNcScraper()
    scraper.retry_delay = 0.01
    scraper.max_retries = 2

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Server error"))

    with pytest.raises(httpx.HTTPError):
        await scraper._fetch_locations(mock_client)

    assert mock_client.get.call_count == 2


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that duplicate locations are removed."""
    scraper = SecondHarvestNwNcScraper()

    # Create a duplicate of the first pantry
    duplicate = dict(SAMPLE_PANTRY)
    raw_data = [SAMPLE_PANTRY, SAMPLE_SOUP_KITCHEN, duplicate]

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return raw_data

    monkeypatch.setattr(scraper, "_fetch_locations", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    # 3 raw records, but the duplicate should be removed
    assert summary["total_locations_found"] == 3
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert len(submitted_jobs) == 2


async def test_scrape_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper in test mode limits results."""
    # Create 10 unique locations
    many_locations = [
        {
            "n": f"Food Bank {i}",
            "a": f"{i} Main Street",
            "c": "Winston-Salem",
            "s": "NC",
            "z": "27101",
            "p": f"(336) 555-{i:04d}",
            "t": "PANTRY",
            "h": "Mon-Fri 9am-5pm",
        }
        for i in range(10)
    ]

    scraper = SecondHarvestNwNcScraper(test_mode=True)

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return many_locations

    monkeypatch.setattr(scraper, "_fetch_locations", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Test mode should limit to 5 locations
    assert summary["total_locations_found"] == 5
    assert summary["unique_locations"] == 5
    assert len(submitted_jobs) == 5


async def test_scrape_full_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test complete scrape workflow with metadata."""
    scraper = SecondHarvestNwNcScraper()

    raw_data = [SAMPLE_PANTRY, SAMPLE_SOUP_KITCHEN, SAMPLE_WITH_ID_PREFIX]

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return raw_data

    monkeypatch.setattr(scraper, "_fetch_locations", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "second_harvest_nw_nc"
    assert summary["food_bank"] == (
        "Second Harvest Food Bank of Northwest North Carolina"
    )
    assert summary["total_locations_found"] == 3
    assert summary["unique_locations"] == 3
    assert summary["total_jobs_created"] == 3
    assert summary["source"] == "https://foodfinder.secondharvestnwnc.org/"


async def test_location_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that location metadata is correctly added."""
    scraper = SecondHarvestNwNcScraper()

    raw_data = [SAMPLE_PANTRY]

    submitted_data: list[dict[str, Any]] = []

    def capture_submission(data: str) -> str:
        submitted_data.append(json.loads(data))
        return "job_123"

    monkeypatch.setattr(scraper, "submit_to_queue", capture_submission)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return raw_data

    monkeypatch.setattr(scraper, "_fetch_locations", mock_fetch)

    await scraper.scrape()

    assert len(submitted_data) == 1
    loc = submitted_data[0]
    assert loc["source"] == "second_harvest_nw_nc"
    assert loc["food_bank"] == ("Second Harvest Food Bank of Northwest North Carolina")
    assert loc["name"] == "Grace Community Food Pantry"
    assert loc["full_address"] == "100 Main Street, Winston-Salem, NC, 27101"
    assert loc["phone"] == "(336) 555-1234"
    assert loc["hours"] == "Mon 9am-12pm, Wed 1pm-4pm"
    assert "Food Pantry" in loc["services"]


async def test_scrape_filters_invalid_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that records with empty/missing names are filtered out."""
    scraper = SecondHarvestNwNcScraper()

    raw_data = [SAMPLE_PANTRY, SAMPLE_EMPTY_NAME, SAMPLE_MISSING_NAME]

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return raw_data

    monkeypatch.setattr(scraper, "_fetch_locations", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    # Only the valid pantry should be submitted
    assert summary["total_locations_found"] == 1
    assert summary["unique_locations"] == 1
    assert len(submitted_jobs) == 1


async def test_scrape_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper handles empty API response."""
    scraper = SecondHarvestNwNcScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(scraper, "_fetch_locations", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["total_locations_found"] == 0
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
    assert len(submitted_jobs) == 0
