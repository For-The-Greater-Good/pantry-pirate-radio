"""Tests for ACCESS Food Share OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.access_food_share_or_scraper import (
    AccessFoodShareOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>ACCESS Medford Food Pantry</h3>
  <p>3630 Aviation Way<br>
  Medford, OR 97504<br>
  (541) 555-1234<br>
  Hours: Mon-Fri 9am-4pm</p>

  <h3>Ashland Community Pantry</h3>
  <p>560 Clover Lane<br>
  Ashland, OR 97520<br>
  (541) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = AccessFoodShareOrScraper()
    assert scraper.scraper_id == "access_food_share_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = AccessFoodShareOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = AccessFoodShareOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = AccessFoodShareOrScraper()

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

    assert summary["scraper_id"] == "access_food_share_or"
    assert summary["food_bank"] == "ACCESS Food Share"
    if submitted:
        assert submitted[0]["source"] == "access_food_share_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = AccessFoodShareOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
