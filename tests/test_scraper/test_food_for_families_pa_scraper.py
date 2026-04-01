"""Tests for Food for Families PA scraper."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.scraper.scrapers.food_for_families_pa_scraper import (
    FoodForFamiliesPaScraper,
)


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FoodForFamiliesPaScraper()
    assert scraper.scraper_id == "food_for_families_pa"
    assert "svdpcares.org" in scraper.base_url
    assert scraper.test_mode is False


def test_scraper_test_mode() -> None:
    """Test scraper initializes correctly in test mode."""
    scraper = FoodForFamiliesPaScraper(test_mode=True)
    assert scraper.test_mode is True


def test_build_location() -> None:
    """Test _build_location returns correct static location."""
    scraper = FoodForFamiliesPaScraper()
    loc = scraper._build_location()

    assert loc["name"] == "Food for Families"
    assert loc["address"] == "945 Franklin Street"
    assert loc["city"] == "Johnstown"
    assert loc["state"] == "PA"
    assert loc["zip"] == "15905"
    assert loc["source"] == "food_for_families_pa"
    assert loc["food_bank"] == "Food for Families"


@pytest.mark.asyncio
async def test_scrape_submits_location() -> None:
    """Test scrape submits the single known location."""
    scraper = FoodForFamiliesPaScraper(test_mode=True)

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    with patch.object(scraper, "submit_to_queue", side_effect=mock_submit):
        with patch.object(scraper, "_verify_site", return_value=True):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "food_for_families_pa"
    assert summary["food_bank"] == "Food for Families"
    assert summary["total_locations_found"] == 1
    assert summary["total_jobs_created"] == 1
    assert summary["site_verified"] is True

    assert len(submitted) == 1
    loc = json.loads(submitted[0])
    assert loc["name"] == "Food for Families"
    assert loc["city"] == "Johnstown"


@pytest.mark.asyncio
async def test_scrape_site_unreachable() -> None:
    """Test scrape still submits location when site is unreachable."""
    scraper = FoodForFamiliesPaScraper(test_mode=True)

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    with patch.object(scraper, "submit_to_queue", side_effect=mock_submit):
        with patch.object(scraper, "_verify_site", return_value=False):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["site_verified"] is False
    assert summary["total_jobs_created"] == 1
    assert len(submitted) == 1
