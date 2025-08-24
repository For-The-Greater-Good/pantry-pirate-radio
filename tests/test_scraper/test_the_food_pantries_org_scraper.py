"""Tests for The_Food_Pantries_OrgScraper."""

import json
from typing import Dict, List

import pytest
import respx
from httpx import Response
from pytest_mock import MockerFixture
from typing_extensions import Any

from app.scraper.the_food_pantries_org_scraper import The_Food_Pantries_OrgScraper

# Test data
SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<container resource-data="[{&quot;type&quot;:&quot;FeatureCollection&quot;,&quot;name&quot;:&quot;Food Pantries Test&quot;,&quot;category&quot;:&quot;Food Pantry&quot;,&quot;features&quot;:[{&quot;type&quot;:&quot;Feature&quot;,&quot;properties&quot;:{&quot;Name&quot;:&quot;Test Pantry&quot;,&quot;Address&quot;:&quot;123 Test St&quot;,&quot;City&quot;:&quot;Testville&quot;,&quot;State&quot;:&quot;NY&quot;},&quot;geometry&quot;:{&quot;type&quot;:&quot;Point&quot;,&quot;coordinates&quot;:[-73.8023108,42.4733363]}}]}]">
</container>
</body>
</html>
"""

SAMPLE_JSON: List[Dict[str, Any]] = [
    {
        "type": "FeatureCollection",
        "name": "Food Pantries Test",
        "category": "Food Pantry",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "Name": "Test Pantry",
                    "Address": "123 Test St",
                    "City": "Testville",
                    "State": "NY",
                },
                "geometry": {"type": "Point", "coordinates": [-73.8023108, 42.4733363]},
            }
        ],
    }
]


@pytest.fixture
def scraper() -> The_Food_Pantries_OrgScraper:
    """Create test scraper instance."""
    return The_Food_Pantries_OrgScraper()


@pytest.mark.asyncio
async def test_download_html(scraper: The_Food_Pantries_OrgScraper) -> None:
    """Test HTML download."""
    with respx.mock:
        # Mock the GET request
        respx.get("https://map.thefoodpantries.org").mock(
            return_value=Response(200, text=SAMPLE_HTML)
        )

        html = await scraper.download_html()
        assert html == SAMPLE_HTML


@pytest.mark.asyncio
async def test_download_html_error(scraper: The_Food_Pantries_OrgScraper) -> None:
    """Test HTML download error handling."""
    with respx.mock:
        # Mock a failed request
        respx.get("https://map.thefoodpantries.org").mock(return_value=Response(500))

        with pytest.raises(Exception):
            await scraper.download_html()


def test_extract_json(scraper: The_Food_Pantries_OrgScraper) -> None:
    """Test JSON extraction from HTML."""
    json_str = scraper.extract_json(SAMPLE_HTML)
    data = json.loads(json_str)
    assert data == SAMPLE_JSON


def test_extract_json_invalid_html(scraper: The_Food_Pantries_OrgScraper) -> None:
    """Test JSON extraction from invalid HTML."""
    with pytest.raises(ValueError, match="Could not find GeoJSON data"):
        scraper.extract_json("<html>No JSON here</html>")


@pytest.mark.asyncio
async def test_scrape(
    scraper: The_Food_Pantries_OrgScraper, mocker: MockerFixture
) -> None:
    """Test full scraping process."""
    # Mock the submit_to_queue method
    mock_submit = mocker.patch.object(scraper, "submit_to_queue")
    mock_submit.return_value = "test_job_id"

    with respx.mock:
        # Mock the GET request
        respx.get("https://map.thefoodpantries.org").mock(
            return_value=Response(200, text=SAMPLE_HTML)
        )

        raw_content = await scraper.scrape()
        data = json.loads(raw_content)

        # Scraper now returns a summary instead of raw content
        assert data["scraper_id"] == "the_food_pantries_org"
        assert data["source"] == "https://map.thefoodpantries.org"
        assert data["total_features"] == 1
        assert data["jobs_created"] == 1
        assert data["status"] == "complete"

        # Verify job was submitted
        assert mock_submit.call_count == 1
