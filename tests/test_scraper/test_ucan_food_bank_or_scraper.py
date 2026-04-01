"""Tests for UCAN Food Bank OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.ucan_food_bank_or_scraper import UcanFoodBankOrScraper

SAMPLE_HTML = """
<html><body><main>
  <h3>UCAN Food Pantry - Roseburg</h3>
  <p>545 SE Rose Street<br>
  Roseburg, OR 97470<br>
  (541) 555-1234<br>
  Hours: Mon-Fri 8:30am-4:30pm</p>

  <h3>Sutherlin Community Pantry</h3>
  <p>100 Central Avenue<br>
  Sutherlin, OR 97479<br>
  (541) 555-5678</p>
</main></body></html>
"""


def test_scraper_init():
    scraper = UcanFoodBankOrScraper()
    assert scraper.scraper_id == "ucan_food_bank_or"
    assert scraper.test_mode is False


def test_scraper_init_test_mode():
    scraper = UcanFoodBankOrScraper(test_mode=True)
    assert scraper.test_mode is True


def test_parse_locations():
    scraper = UcanFoodBankOrScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    for loc in locations:
        assert loc["state"] == "OR"


@pytest.mark.asyncio
async def test_scrape_workflow(monkeypatch: pytest.MonkeyPatch):
    scraper = UcanFoodBankOrScraper()

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

    assert summary["scraper_id"] == "ucan_food_bank_or"
    assert summary["food_bank"] == "UCAN Food Bank"
    if submitted:
        assert submitted[0]["source"] == "ucan_food_bank_or"


@pytest.mark.asyncio
async def test_scrape_handles_error(monkeypatch: pytest.MonkeyPatch):
    scraper = UcanFoodBankOrScraper()

    async def mock_fetch(client: Any, url: str) -> str:
        raise Exception("Network error")

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)
    monkeypatch.setattr(scraper, "submit_to_queue", lambda c: "job-1")

    result = await scraper.scrape()
    summary = json.loads(result)
    assert summary["total_jobs_created"] == 0
