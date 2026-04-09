"""Tests for Community Connection of NE Oregon scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.community_connection_ne_oregon_or_scraper import (
    CommunityConnectionNeOregonOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>La Grande Food Pantry</h3>
  <p>1504 N Hall Street<br>
  La Grande, OR 97850<br>
  (541) 555-1234<br>
  Hours: Tue-Thu 10am-3pm</p>

  <h3>Enterprise Community Pantry</h3>
  <p>200 River Street<br>
  Enterprise, OR 97828<br>
  (541) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = CommunityConnectionNeOregonOrScraper()
    assert scraper.scraper_id == "community_connection_ne_oregon_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = CommunityConnectionNeOregonOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = CommunityConnectionNeOregonOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = CommunityConnectionNeOregonOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    submitted: list[dict[str, Any]] = []

    def mock_submit(content: str) -> str:
        submitted.append(json.loads(content))
        return "job-1"

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "community_connection_ne_oregon_or"
    assert summary["food_bank"] == "Community Connection of NE Oregon"
    if submitted:
        assert submitted[0]["source"] == "community_connection_ne_oregon_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = CommunityConnectionNeOregonOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
