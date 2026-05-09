"""Tests for Second Harvest Clark, Champaign & Logan OH scraper."""

import json
from unittest.mock import patch

import pytest

from app.scraper.scrapers.second_harvest_clark_champaign_logan_oh_scraper import (
    SecondHarvestClarkChampaignLoganOhScraper,
)


def _wix_block(suffix: str, name: str, address: str, hours: str, phone: str) -> str:
    """Build a Wix-style repeater block for a single pantry entry."""

    def rt(idx: int, value: str) -> str:
        return (
            f'<div id="comp-mmy04h0q{idx}__{suffix}" '
            f'class="wixui-rich-text" data-testid="richTextElement">'
            f"<p><span>{value}</span></p></div>"
        )

    return rt(1, name) + rt(2, address) + rt(3, hours) + rt(4, phone)


@pytest.fixture
def sample_html() -> str:
    """Minimal HTML mimicking the Wix repeater layout on /pantries-test."""
    blocks = [
        _wix_block(
            "1865979a-0079-4983-a158-2cc3e8a1d8dc",
            "Bethel Churches United Pantry",
            "226 S Pike St, New Carlisle, Oh",
            "Pantry Wednesday 4-5:30pm Friday 12-2PM",
            "937-845-1008",
        ),
        _wix_block(
            "2865979a-0079-4983-a158-2cc3e8a1d8dc",
            "Oasis of Mercy Pantry at St Michael&#39;s",
            "40 Walnut St, Mechanicsburg, Oh",
            "Pantry: first and third Tuesdays, 3:30-5:30pm",
            "614-507-0882",
        ),
    ]
    return f"<html><body>{''.join(blocks)}</body></html>"


@pytest.mark.asyncio
async def test_scraper_initialization():
    """Scraper exposes the Wix pantries URL."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    assert scraper.scraper_id == "second_harvest_clark_champaign_logan_oh"
    assert scraper.base_url == "https://www.theshfb.org"
    assert scraper.pantries_url.endswith("/pantries-test")
    assert scraper.test_mode is False


def test_parse_address_three_parts():
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    assert scraper._parse_address("226 S Pike St, New Carlisle, Oh") == {
        "address": "226 S Pike St",
        "city": "New Carlisle",
        "state": "OH",
    }


def test_parse_address_two_parts_defaults_state():
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    assert scraper._parse_address("123 Main St, Springfield") == {
        "address": "123 Main St",
        "city": "Springfield",
        "state": "OH",
    }


def test_parse_address_with_extra_commas():
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    parsed = scraper._parse_address("100 N Main St, Suite 4, Urbana, OH")
    assert parsed == {
        "address": "100 N Main St, Suite 4",
        "city": "Urbana",
        "state": "OH",
    }


def test_parse_pantries_extracts_all_fields(sample_html):
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    pantries = scraper.parse_pantries(sample_html)
    assert len(pantries) == 2

    bethel = pantries[0]
    assert bethel["name"] == "Bethel Churches United Pantry"
    assert bethel["address"] == "226 S Pike St"
    assert bethel["city"] == "New Carlisle"
    assert bethel["state"] == "OH"
    assert "Wednesday" in bethel["hours"]
    assert "Friday" in bethel["hours"]
    assert bethel["phone"] == "937-845-1008"
    assert bethel["latitude"] is None
    assert bethel["longitude"] is None


def test_parse_pantries_decodes_html_entities(sample_html):
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    pantries = scraper.parse_pantries(sample_html)
    oasis = pantries[1]
    assert oasis["name"] == "Oasis of Mercy Pantry at St Michael's"


def test_parse_pantries_skips_incomplete_blocks():
    """Repeater items missing one of the four rich-text fields are skipped."""
    suffix = "abcdef12-3456-7890-abcd-ef1234567890"
    incomplete = (
        f'<div id="comp-x1__{suffix}" data-testid="richTextElement">'
        f"<p>Only Name</p></div>"
        f'<div id="comp-x2__{suffix}" data-testid="richTextElement">'
        f"<p>Only Address</p></div>"
    )
    scraper = SecondHarvestClarkChampaignLoganOhScraper()
    assert scraper.parse_pantries(f"<html>{incomplete}</html>") == []


@pytest.mark.asyncio
async def test_scrape_submits_jobs_with_metadata(sample_html):
    scraper = SecondHarvestClarkChampaignLoganOhScraper()

    submitted: list[dict] = []

    def capture(payload: str) -> str:
        submitted.append(json.loads(payload))
        return "job_xyz"

    async def fake_fetch(client):
        return sample_html

    with patch.object(scraper, "fetch_html", side_effect=fake_fetch):
        with patch.object(scraper, "submit_to_queue", side_effect=capture):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["scraper_id"] == "second_harvest_clark_champaign_logan_oh"
    assert summary["unique_locations"] == 2
    assert summary["total_jobs_created"] == 2
    assert summary["source"] == "https://www.theshfb.org"

    assert len(submitted) == 2
    assert submitted[0]["source"] == "second_harvest_clark_champaign_logan_oh"
    assert submitted[0]["food_bank"] == (
        "Second Harvest Food Bank of Clark, Champaign & Logan Counties"
    )
    assert submitted[0]["hours"]
    assert submitted[0]["phone"]


@pytest.mark.asyncio
async def test_scrape_test_mode_caps_results(sample_html):
    """test_mode limits to first 3 entries — fewer entries pass through unchanged."""
    scraper = SecondHarvestClarkChampaignLoganOhScraper(test_mode=True)

    async def fake_fetch(client):
        return sample_html

    with patch.object(scraper, "fetch_html", side_effect=fake_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_xyz"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 2


@pytest.mark.asyncio
async def test_scrape_empty_page():
    scraper = SecondHarvestClarkChampaignLoganOhScraper()

    async def fake_fetch(client):
        return "<html><body><p>nothing here</p></body></html>"

    with patch.object(scraper, "fetch_html", side_effect=fake_fetch):
        with patch.object(scraper, "submit_to_queue", return_value="job_xyz"):
            result = await scraper.scrape()

    summary = json.loads(result)
    assert summary["unique_locations"] == 0
    assert summary["total_jobs_created"] == 0
