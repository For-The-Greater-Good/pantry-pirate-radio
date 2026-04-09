"""Tests for South Coast Food Share OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.south_coast_food_share_or_scraper import (
    SouthCoastFoodShareOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>Coos Bay Food Pantry</h3>
  <p>500 Central Avenue<br>
  Coos Bay, OR 97420<br>
  (541) 555-1234<br>
  Hours: Mon-Wed 10am-3pm</p>

  <h3>Brookings Community Pantry</h3>
  <p>200 Pacific Highway<br>
  Brookings, OR 97415<br>
  (541) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = SouthCoastFoodShareOrScraper()
    assert scraper.scraper_id == "south_coast_food_share_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = SouthCoastFoodShareOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = SouthCoastFoodShareOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = SouthCoastFoodShareOrScraper()

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

    assert summary["scraper_id"] == "south_coast_food_share_or"
    assert summary["food_bank"] == "South Coast Food Share"
    if submitted:
        assert submitted[0]["source"] == "south_coast_food_share_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = SouthCoastFoodShareOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
