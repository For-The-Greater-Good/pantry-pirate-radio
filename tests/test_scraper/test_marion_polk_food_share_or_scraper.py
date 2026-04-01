"""Tests for Marion Polk Food Share OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.marion_polk_food_share_or_scraper import (
    MarionPolkFoodShareOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>Marion Polk Food Share Warehouse</h3>
  <p>1660 Salem Industrial Drive<br>
  Salem, OR 97302<br>
  (503) 555-1234<br>
  Hours: Mon-Fri 8am-5pm</p>

  <h3>Keizer Community Pantry</h3>
  <p>980 Chemawa Road<br>
  Keizer, OR 97303<br>
  (503) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = MarionPolkFoodShareOrScraper()
    assert scraper.scraper_id == "marion_polk_food_share_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = MarionPolkFoodShareOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = MarionPolkFoodShareOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = MarionPolkFoodShareOrScraper()

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

    assert summary["scraper_id"] == "marion_polk_food_share_or"
    assert summary["food_bank"] == "Marion Polk Food Share"
    if submitted:
        assert submitted[0]["source"] == "marion_polk_food_share_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = MarionPolkFoodShareOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
