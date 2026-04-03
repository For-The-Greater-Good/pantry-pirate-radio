"""Tests for CAPECO Food Share OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.capeco_food_share_or_scraper import (
    CapecoFoodShareOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>The Dalles Food Pantry</h3>
  <p>201 Federal Street<br>
  The Dalles, OR 97058<br>
  (541) 555-1234<br>
  Hours: Mon-Wed 9am-3pm</p>

  <h3>Hood River Pantry</h3>
  <p>1025 June Street<br>
  Hood River, OR 97031<br>
  (541) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = CapecoFoodShareOrScraper()
    assert scraper.scraper_id == "capeco_food_share_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = CapecoFoodShareOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = CapecoFoodShareOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = CapecoFoodShareOrScraper()

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

    assert summary["scraper_id"] == "capeco_food_share_or"
    assert summary["food_bank"] == "CAPECO Food Share"
    if submitted:
        assert submitted[0]["source"] == "capeco_food_share_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = CapecoFoodShareOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
