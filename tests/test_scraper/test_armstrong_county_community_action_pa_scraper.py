"""Tests for Armstrong County Community Action Agency PA scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.armstrong_county_community_action_pa_scraper import (
    ArmstrongCountyCommunityActionPaScraper,
)


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = ArmstrongCountyCommunityActionPaScraper()
    assert scraper.scraper_id == "armstrong_county_community_action_pa"
    assert "armstrongcap.com" in scraper.base_url


def test_build_location() -> None:
    """Test _build_location returns correct static location."""
    scraper = ArmstrongCountyCommunityActionPaScraper()
    loc = scraper._build_location()

    assert loc["name"] == "Armstrong County Community Action Agency"
    assert loc["address"] == "705 Butler Road"
    assert loc["city"] == "Kittanning"
    assert loc["state"] == "PA"
    assert loc["zip"] == "16201"
    assert loc["source"] == "armstrong_county_community_action_pa"
    assert loc["food_bank"] == "Armstrong County Community Action Agency"


@pytest.mark.asyncio
async def test_scrape_submits_location() -> None:
    """Test scrape submits the single known location."""
    scraper = ArmstrongCountyCommunityActionPaScraper(test_mode=True)

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    with patch.object(scraper, "submit_to_queue", side_effect=mock_submit):
        with patch.object(scraper, "_verify_site", return_value=True):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 1
    assert summary["site_verified"] is True
    assert len(submitted) == 1

    loc = json.loads(submitted[0])
    assert loc["name"] == "Armstrong County Community Action Agency"
    assert loc["city"] == "Kittanning"


@pytest.mark.asyncio
async def test_scrape_site_unreachable() -> None:
    """Test scrape still submits location when site is unreachable."""
    scraper = ArmstrongCountyCommunityActionPaScraper(test_mode=True)

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
