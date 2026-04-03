"""Tests for Fayette County Community Action Food Bank PA scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.fayette_county_community_action_pa_scraper import (
    FayetteCountyCommunityActionPaScraper,
)


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = FayetteCountyCommunityActionPaScraper()
    assert scraper.scraper_id == "fayette_county_community_action_pa"
    assert "fccaa.org" in scraper.base_url


def test_build_location() -> None:
    """Test _build_location returns correct static location."""
    scraper = FayetteCountyCommunityActionPaScraper()
    loc = scraper._build_location()

    assert loc["name"] == "Fayette County Community Action Food Bank"
    assert loc["address"] == "119 North Beeson Avenue"
    assert loc["city"] == "Uniontown"
    assert loc["state"] == "PA"
    assert loc["zip"] == "15401"
    assert loc["source"] == "fayette_county_community_action_pa"


@pytest.mark.asyncio
async def test_scrape_submits_location() -> None:
    """Test scrape submits the single known location."""
    scraper = FayetteCountyCommunityActionPaScraper(test_mode=True)

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    with patch.object(scraper, "submit_to_queue", side_effect=mock_submit):
        with patch.object(scraper, "_verify_site", return_value=True):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["total_jobs_created"] == 1
    assert len(submitted) == 1

    loc = json.loads(submitted[0])
    assert loc["name"] == "Fayette County Community Action Food Bank"


@pytest.mark.asyncio
async def test_scrape_site_unreachable() -> None:
    """Test scrape still submits when site is unreachable."""
    scraper = FayetteCountyCommunityActionPaScraper(test_mode=True)

    with patch.object(scraper, "submit_to_queue", return_value="job-1"):
        with patch.object(scraper, "_verify_site", return_value=False):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["site_verified"] is False
    assert summary["total_jobs_created"] == 1
