"""Tests for Yamhill Community Action Partnership OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.yamhill_cap_or_scraper import YamhillCapOrScraper

SAMPLE_HTML = """
<html><body><main>
  <h3>YCAP Food Bank - McMinnville</h3>
  <p>1317 NE Dustin Court<br>
  McMinnville, OR 97128<br>
  (503) 555-1234<br>
  Hours: Mon-Fri 9am-5pm</p>

  <h3>Newberg Food Pantry</h3>
  <p>500 E Hancock Street<br>
  Newberg, OR 97132<br>
  (503) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = YamhillCapOrScraper()
    assert scraper.scraper_id == "yamhill_cap_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = YamhillCapOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = YamhillCapOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = YamhillCapOrScraper()

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

    assert summary["scraper_id"] == "yamhill_cap_or"
    assert summary["food_bank"] == "Yamhill Community Action Partnership"
    if submitted:
        assert submitted[0]["source"] == "yamhill_cap_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = YamhillCapOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
