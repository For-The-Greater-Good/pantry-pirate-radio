"""Tests for NeighborImpact OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.neighborimpact_or_scraper import NeighborimpactOrScraper

SAMPLE_HTML = """
<html><body><main>
  <h3>Bend Food Pantry</h3>
  <p>200 NE Hawthorne Avenue<br>
  Bend, OR 97701<br>
  (541) 555-1234<br>
  Hours: Mon-Fri 10am-4pm</p>

  <h3>Redmond Pantry</h3>
  <p>300 SW Evergreen Avenue<br>
  Redmond, OR 97756<br>
  (541) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = NeighborimpactOrScraper()
    assert scraper.scraper_id == "neighborimpact_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = NeighborimpactOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = NeighborimpactOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = NeighborimpactOrScraper()

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

    assert summary["scraper_id"] == "neighborimpact_or"
    assert summary["food_bank"] == "NeighborImpact"
    if submitted:
        assert submitted[0]["source"] == "neighborimpact_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = NeighborimpactOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
