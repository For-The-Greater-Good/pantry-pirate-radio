"""Tests for Food Share of Lincoln County OR scraper."""

import json
from typing import Any

import pytest

from app.scraper.scrapers.food_share_lincoln_county_or_scraper import (
    FoodShareLincolnCountyOrScraper,
)

SAMPLE_HTML = """
<html><body><main>
<div class="sow-accordion">
  <div class="sow-accordion-panel" data-anchor-id="newport-food-pantry">
    <div class="sow-accordion-panel-header-container">
      <div class="sow-accordion-panel-header">
        <div class="sow-accordion-title sow-accordion-title-icon-left">
          Newport Food Pantry
        </div>
      </div>
    </div>
    <div class="sow-accordion-panel-content">
      <div class="sow-accordion-panel-border">
        <p style="text-align: center;">
          541-555-1234<br>210 SE Avery Street, Newport
        </p>
        <p style="text-align: center;">Tuesday 2:30 pm - 4:00 pm</p>
      </div>
    </div>
  </div>
  <div class="sow-accordion-panel" data-anchor-id="lincoln-city-pantry">
    <div class="sow-accordion-panel-header-container">
      <div class="sow-accordion-panel-header">
        <div class="sow-accordion-title sow-accordion-title-icon-left">
          Lincoln City Pantry
        </div>
      </div>
    </div>
    <div class="sow-accordion-panel-content">
      <div class="sow-accordion-panel-border">
        <p style="text-align: center;">
          541-555-5678<br>4555 SE Hwy 101, Lincoln City
        </p>
        <p style="text-align: center;">
          Tuesday 2:00 pm - 6:00 pm<br>Thursday 2:00 pm - 6:00 pm
        </p>
      </div>
    </div>
  </div>
</div>
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
