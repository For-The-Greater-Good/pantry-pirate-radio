"""Tests for Columbia Pacific Food Bank OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.columbia_pacific_food_bank_or_scraper import (
    ColumbiaPacificFoodBankOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
  <h3>St. Helens Food Pantry</h3>
  <p>255 Strand Street<br>
  St. Helens, OR 97051<br>
  (503) 555-1234<br>
  Hours: Mon-Fri 9am-4pm</p>

  <h3>Rainier Community Pantry</h3>
  <p>100 W B Street<br>
  Rainier, OR 97048<br>
  (503) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = ColumbiaPacificFoodBankOrScraper()
    assert scraper.scraper_id == "columbia_pacific_food_bank_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = ColumbiaPacificFoodBankOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = ColumbiaPacificFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = ColumbiaPacificFoodBankOrScraper()

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

    assert summary["scraper_id"] == "columbia_pacific_food_bank_or"
    assert summary["food_bank"] == "Columbia Pacific Food Bank"
    if submitted:
        assert submitted[0]["source"] == "columbia_pacific_food_bank_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = ColumbiaPacificFoodBankOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
