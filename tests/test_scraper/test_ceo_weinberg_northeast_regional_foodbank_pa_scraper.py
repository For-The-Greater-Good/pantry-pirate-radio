"""Tests for CEO Weinberg Northeast Regional Foodbank PA scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.ceo_weinberg_northeast_regional_foodbank_pa_scraper import (
    CeoWeinbergNortheastRegionalFoodbankPaScraper,
)


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper()
    assert scraper.scraper_id == "ceo_weinberg_northeast_regional_foodbank_pa"
    assert "ceopeoplehelpingpeople.org" in scraper.find_food_url
    assert scraper.test_mode is False


def test_scraper_test_mode() -> None:
    """Test scraper initializes in test mode."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper(test_mode=True)
    assert scraper.test_mode is True


def test_warehouse_location() -> None:
    """Test warehouse location has correct data."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper()
    loc = scraper._warehouse_location()

    assert loc["name"] == "CEO Weinberg Northeast Regional Foodbank"
    assert loc["address"] == "185 Research Drive"
    assert loc["city"] == "Pittston"
    assert loc["state"] == "PA"
    assert loc["zip"] == "18640"
    assert loc["phone"] == "570-826-0510"
    assert loc["source"] == "ceo_weinberg_northeast_regional_foodbank_pa"


def test_build_location() -> None:
    """Test _build_location builds valid location dict."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper()

    loc = scraper._build_location(
        "Test Pantry",
        "100 Main St, Scranton, PA 18503",
        "570-555-1234",
        "Monday 9am-12pm",
    )
    assert loc is not None
    assert loc["name"] == "Test Pantry"
    assert loc["phone"] == "570-555-1234"
    assert loc["hours"] == "Monday 9am-12pm"
    assert loc["state"] == "PA"
    assert loc["source"] == "ceo_weinberg_northeast_regional_foodbank_pa"


def test_build_location_empty_name() -> None:
    """Test _build_location returns None for empty name."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper()
    loc = scraper._build_location("", "123 Main St", "", "")
    assert loc is None


@pytest.mark.asyncio
async def test_scrape_fallback_to_warehouse() -> None:
    """Test scrape falls back to warehouse when page fetch fails."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper(test_mode=True)

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    with patch.object(scraper, "submit_to_queue", side_effect=mock_submit):
        with patch.object(
            scraper,
            "_fetch_page",
            side_effect=Exception("Network error"),
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "ceo_weinberg_northeast_regional_foodbank_pa"
    assert summary["total_locations_found"] >= 1
    assert summary["total_jobs_created"] >= 1

    # Should include at least the warehouse
    assert len(submitted) >= 1
    warehouse = json.loads(submitted[-1])
    assert warehouse["city"] == "Pittston"


@pytest.mark.asyncio
async def test_scrape_with_parsed_locations() -> None:
    """Test scrape when HTML parsing yields locations."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper(test_mode=True)

    mock_locations = [
        {
            "name": "Test Pantry A",
            "address": "123 Main St, Scranton, PA 18503",
            "state": "PA",
            "source": scraper.scraper_id,
            "food_bank": "CEO Weinberg Northeast Regional Foodbank",
        },
    ]

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    with patch.object(scraper, "submit_to_queue", side_effect=mock_submit):
        with patch.object(scraper, "_fetch_page", return_value="<html></html>"):
            with patch.object(scraper, "_parse_locations", return_value=mock_locations):
                result = await scraper.scrape()

    summary = json.loads(result)
    # Parsed location + warehouse = at least 2
    assert summary["total_jobs_created"] >= 2
    assert len(submitted) >= 2


@pytest.mark.asyncio
async def test_scrape_summary_format() -> None:
    """Test scrape returns valid JSON summary with required fields."""
    scraper = CeoWeinbergNortheastRegionalFoodbankPaScraper(test_mode=True)

    with patch.object(scraper, "submit_to_queue", return_value="job-1"):
        with patch.object(
            scraper,
            "_fetch_page",
            side_effect=Exception("fail"),
        ):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert "scraper_id" in summary
    assert "food_bank" in summary
    assert "total_locations_found" in summary
    assert "total_jobs_created" in summary
    assert "source" in summary
