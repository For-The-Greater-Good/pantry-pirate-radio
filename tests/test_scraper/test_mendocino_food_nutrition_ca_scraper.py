"""Tests for Mendocino Food & Nutrition Program CA scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.scraper.scrapers.mendocino_food_nutrition_ca_scraper import (
    MendocinoFoodNutritionCaScraper,
    FOOD_BANK_NAME,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Fort Bragg Food Bank</h1>
<p>910 N Franklin St, Fort Bragg, CA 95437</p>
<p>Phone: (707) 964-9404</p>
<h2>Distribution Sites</h2>
<ul>
<li>Ukiah Community Food Pantry - 100 N State St, Ukiah, CA 95482. Food distribution on Wednesdays.</li>
<li>Willits Food Bank - 229 E San Francisco Ave, Willits. (707) 459-3333. Open Tue-Thu 10am-4pm</li>
</ul>
</body>
</html>
"""


def test_scraper_init() -> None:
    """Test scraper initializes with correct defaults."""
    scraper = MendocinoFoodNutritionCaScraper()
    assert scraper.scraper_id == "mendocino_food_nutrition_ca"
    assert scraper.test_mode is False
    assert "fortbraggfoodbank.org" in scraper.base_url


def test_parse_locations_main_location() -> None:
    """Test that the main food bank is always included."""
    scraper = MendocinoFoodNutritionCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    assert len(locations) >= 1
    main = locations[0]
    assert "Fort Bragg" in main["name"]
    assert main["city"] == "Fort Bragg"
    assert main["state"] == "CA"


def test_parse_locations_extracts_phone() -> None:
    """Test phone extraction from page content."""
    scraper = MendocinoFoodNutritionCaScraper()
    locations = scraper._parse_locations(SAMPLE_HTML)
    main = locations[0]
    assert main["phone"] == "(707) 964-9404"


async def test_scrape_submits_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test scrape submits locations to queue."""
    scraper = MendocinoFoodNutritionCaScraper()

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return f"job-{len(submitted)}"

    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["scraper_id"] == "mendocino_food_nutrition_ca"
    assert summary["food_bank"] == FOOD_BANK_NAME
    assert summary["total_jobs_created"] >= 1

    first_job = json.loads(submitted[0])
    assert first_job["source"] == "mendocino_food_nutrition_ca"
    assert first_job["food_bank"] == FOOD_BANK_NAME


async def test_scrape_deduplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that duplicate locations are removed."""
    scraper = MendocinoFoodNutritionCaScraper()

    def mock_parse(html: str) -> list[dict[str, Any]]:
        loc = {
            "name": "Test",
            "address": "100 Main St",
            "city": "Fort Bragg",
            "state": "CA",
            "zip": "95437",
            "phone": "",
            "hours": "",
            "description": "",
            "services": ["Food Pantry"],
        }
        return [loc, dict(loc)]

    submitted: list[str] = []

    def mock_submit(content: str) -> str:
        submitted.append(content)
        return "job-1"

    monkeypatch.setattr(scraper, "_parse_locations", mock_parse)
    monkeypatch.setattr(scraper, "submit_to_queue", mock_submit)

    async def mock_fetch(client: Any, url: str) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "_fetch_page", mock_fetch)

    result = await scraper.scrape()
    summary = json.loads(result)

    assert summary["unique_locations"] == 1
    assert len(submitted) == 1
