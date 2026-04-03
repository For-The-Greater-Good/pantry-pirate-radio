"""Tests for Indiana County Community Action Program PA scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.indiana_county_community_action_pa_scraper import (
    IndianaCountyCommunityActionPaScraper,
)


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = IndianaCountyCommunityActionPaScraper()
    assert scraper.scraper_id == "indiana_county_community_action_pa"
    assert "iccap.net" in scraper.base_url


def test_build_location() -> None:
    """Test _build_location returns correct static location."""
    scraper = IndianaCountyCommunityActionPaScraper()
    loc = scraper._build_location()

    assert loc["name"] == "Indiana County Community Action Program"
    assert loc["address"] == "827 Water Street"
    assert loc["city"] == "Indiana"
    assert loc["state"] == "PA"
    assert loc["zip"] == "15701"
    assert loc["source"] == "indiana_county_community_action_pa"


@pytest.mark.asyncio
async def test_scrape_submits_location() -> None:
    """Test scrape submits the single known location."""
    scraper = IndianaCountyCommunityActionPaScraper(test_mode=True)

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
    assert loc["name"] == "Indiana County Community Action Program"


@pytest.mark.asyncio
async def test_scrape_site_unreachable() -> None:
    """Test scrape still submits when site is unreachable."""
    scraper = IndianaCountyCommunityActionPaScraper(test_mode=True)

    with patch.object(scraper, "submit_to_queue", return_value="job-1"):
        with patch.object(scraper, "_verify_site", return_value=False):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["site_verified"] is False
    assert summary["total_jobs_created"] == 1
