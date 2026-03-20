"""Tests for Food Oasis LA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.food_oasis_la_scraper import (
    TENANTS,
    FoodOasisLaScraper,
)


SAMPLE_ORG_ACTIVE: dict[str, Any] = {
    "id": 101,
    "name": "LA Regional Food Bank",
    "address1": "1734 E 41st Street",
    "address2": "",
    "city": "Los Angeles",
    "state": "CA",
    "zip": "90058",
    "phone": "(323) 234-3030",
    "email": "info@lafoodbank.org",
    "website": "https://www.lafoodbank.org",
    "description": "Distributes food to pantries throughout LA County",
    "latitude": 34.0012,
    "longitude": -118.2098,
    "hours": [
        {"day_of_week": "Mon", "open": "08:00", "close": "16:00", "week_of_month": 0}
    ],
    "categories": [{"id": 1, "name": "Food Pantry"}],
    "requirements": "Photo ID required",
    "eligibilityNotes": "Open to all LA County residents",
    "languages": "English, Spanish",
    "foodTypes": "Produce, Canned Goods",
    "inactive": False,
    "allowWalkins": True,
}

SAMPLE_ORG_ACTIVE_2: dict[str, Any] = {
    "id": 201,
    "name": "Aloha Harvest",
    "address1": "3599 Waialae Ave",
    "city": "Honolulu",
    "state": "HI",
    "zip": "96816",
    "phone": "(808) 208-1581",
    "latitude": 21.2816,
    "longitude": -157.7991,
    "categories": [{"id": 9, "name": "Meal Program"}],
    "inactive": False,
}

SAMPLE_ORG_INACTIVE: dict[str, Any] = {
    "id": 102,
    "name": "Closed Pantry",
    "address1": "999 Nowhere St",
    "city": "Los Angeles",
    "state": "CA",
    "zip": "90001",
    "inactive": True,
}

SAMPLE_ORG_NO_NAME: dict[str, Any] = {
    "id": 103,
    "address1": "456 Oak Ave",
    "city": "Los Angeles",
    "state": "CA",
    "inactive": False,
}


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FoodOasisLaScraper()
    assert scraper.scraper_id == "food_oasis_la"
    assert "foodoasis.la" in scraper.base_url


def test_is_active_accepts_active_org() -> None:
    """Test _is_active returns True for active orgs with a name."""
    scraper = FoodOasisLaScraper()
    assert scraper._is_active(SAMPLE_ORG_ACTIVE) is True


def test_is_active_filters_inactive() -> None:
    """Test _is_active filters out inactive organizations."""
    scraper = FoodOasisLaScraper()
    assert scraper._is_active(SAMPLE_ORG_INACTIVE) is False


def test_is_active_filters_no_name() -> None:
    """Test _is_active filters out organizations without a name."""
    scraper = FoodOasisLaScraper()
    assert scraper._is_active(SAMPLE_ORG_NO_NAME) is False


def test_is_active_filters_empty_name() -> None:
    """Test _is_active filters out organizations with empty name."""
    scraper = FoodOasisLaScraper()
    org = {**SAMPLE_ORG_ACTIVE, "name": "  "}
    assert scraper._is_active(org) is False


async def test_fetch_tenant_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful tenant data fetch."""
    scraper = FoodOasisLaScraper()
    expected_data = [SAMPLE_ORG_ACTIVE, SAMPLE_ORG_INACTIVE]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = expected_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await scraper._fetch_tenant(mock_client, 1, "Los Angeles")

    assert result == expected_data
    mock_client.get.assert_called_once()
    call_url = mock_client.get.call_args[0][0]
    assert "tenantId=1" in call_url


async def test_fetch_tenant_retry_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test retry logic when first attempt fails."""
    scraper = FoodOasisLaScraper()
    scraper.retry_delay = 0.01  # Speed up test

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [SAMPLE_ORG_ACTIVE]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[httpx.HTTPError("Server error"), mock_response]
    )

    result = await scraper._fetch_tenant(mock_client, 1, "Los Angeles")

    assert result == [SAMPLE_ORG_ACTIVE]
    assert mock_client.get.call_count == 2


async def test_fetch_tenant_all_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that exception is raised when all retries fail."""
    scraper = FoodOasisLaScraper()
    scraper.retry_delay = 0.01
    scraper.max_retries = 2

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Server error"))

    with pytest.raises(httpx.HTTPError):
        await scraper._fetch_tenant(mock_client, 1, "Los Angeles")

    assert mock_client.get.call_count == 2


async def test_scrape_submits_active_orgs_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that scrape submits only active organizations."""
    scraper = FoodOasisLaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(
        client: Any, tenant_id: int, tenant_name: str
    ) -> list[dict[str, Any]]:
        if tenant_id == 1:
            return [SAMPLE_ORG_ACTIVE, SAMPLE_ORG_INACTIVE, SAMPLE_ORG_NO_NAME]
        if tenant_id == 3:
            return [SAMPLE_ORG_ACTIVE_2]
        return []

    monkeypatch.setattr(scraper, "_fetch_tenant", mock_fetch)

    result = await scraper.scrape()

    # Only 2 active orgs should be submitted (1 from LA, 1 from Hawaii)
    assert len(submitted_jobs) == 2

    # Verify submitted data is valid JSON with correct org data
    job_1 = json.loads(submitted_jobs[0])
    assert job_1["name"] == "LA Regional Food Bank"

    job_2 = json.loads(submitted_jobs[1])
    assert job_2["name"] == "Aloha Harvest"

    # Verify summary returned
    assert "2" in result


async def test_scrape_continues_on_tenant_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that scraper continues when one tenant fails."""
    scraper = FoodOasisLaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(
        client: Any, tenant_id: int, tenant_name: str
    ) -> list[dict[str, Any]]:
        if tenant_id == 1:
            raise httpx.HTTPError("Server error")
        if tenant_id == 3:
            return [SAMPLE_ORG_ACTIVE_2]
        return []

    monkeypatch.setattr(scraper, "_fetch_tenant", mock_fetch)

    result = await scraper.scrape()

    # Hawaii org should still be submitted despite LA failure
    assert len(submitted_jobs) == 1
    job = json.loads(submitted_jobs[0])
    assert job["name"] == "Aloha Harvest"


async def test_scrape_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper handles empty tenant responses."""
    scraper = FoodOasisLaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(
        client: Any, tenant_id: int, tenant_name: str
    ) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(scraper, "_fetch_tenant", mock_fetch)

    result = await scraper.scrape()

    assert len(submitted_jobs) == 0
    assert "0" in result


async def test_scrape_all_tenants_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scraper completes gracefully when all tenants fail."""
    scraper = FoodOasisLaScraper()

    submitted_jobs: list[str] = []

    def mock_submit(content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(
        client: Any, tenant_id: int, tenant_name: str
    ) -> list[dict[str, Any]]:
        raise httpx.HTTPError("Server error")

    monkeypatch.setattr(scraper, "_fetch_tenant", mock_fetch)

    result = await scraper.scrape()

    assert len(submitted_jobs) == 0
    assert len(TENANTS) == 4  # Confirm all tenants were attempted
