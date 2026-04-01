"""Tests for Food Share of Lincoln County OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.food_share_lincoln_county_or_scraper import (
    FoodShareLincolnCountyOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>Newport Food Pantry</h3>
  <p>210 SE Avery Street<br>
  Newport, OR 97365<br>
  (541) 555-1234<br>
  Hours: Mon-Fri 9am-4pm</p>

  <h3>Lincoln City Pantry</h3>
  <p>4555 SE Hwy 101<br>
  Lincoln City, OR 97367<br>
  (541) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = FoodShareLincolnCountyOrScraper()
    assert scraper.scraper_id == "food_share_lincoln_county_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = FoodShareLincolnCountyOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = FoodShareLincolnCountyOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = FoodShareLincolnCountyOrScraper()

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

    assert summary["scraper_id"] == "food_share_lincoln_county_or"
    assert summary["food_bank"] == "Food Share of Lincoln County"
    if submitted:
        assert submitted[0]["source"] == "food_share_lincoln_county_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = FoodShareLincolnCountyOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
