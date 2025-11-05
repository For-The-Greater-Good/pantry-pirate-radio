"""Tests for the sample scraper."""

import json
from pathlib import Path
from typing import Any, TypedDict

import pytest

from app.scraper.sample_scraper import SampleScraper


class FeatureProperties(TypedDict):
    """Type definition for feature properties."""

    Name: str
    Address: str


class Feature(TypedDict):
    """Type definition for GeoJSON feature."""

    type: str
    properties: FeatureProperties
    geometry: dict[str, Any]


class FeatureCollection(TypedDict):
    """Type definition for GeoJSON feature collection."""

    type: str
    name: str
    category: str
    features: list[Feature]


@pytest.fixture
def sample_geojson(tmp_path: Path) -> Path:
    """Create a sample GeoJSON file for testing."""
    content: FeatureCollection = {
        "type": "FeatureCollection",
        "name": "Test Collection",
        "category": "Test Category",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "Name": "Test Location",
                    "Address": "123 Test St",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [-73.935242, 40.730610],
                },
            }
        ],
    }

    # Create the expected directory structure
    test_dir = tmp_path / "docs/scraper/examples/thefoodpantries.org"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "output.json"
    # Wrap in list to match real data
    test_file.write_text(json.dumps([content]))
    return test_file


@pytest.mark.asyncio
async def test_sample_scraper_job_submission(
    sample_geojson: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the scraper submits jobs correctly."""
    # Track submitted jobs
    submitted_jobs: list[str] = []

    # Create scraper instance
    scraper = SampleScraper()

    # Mock submit_to_queue to track jobs
    def mock_submit(self: SampleScraper, content: str) -> str:
        submitted_jobs.append(content)
        return f"job-{len(submitted_jobs)}"

    monkeypatch.setattr(SampleScraper, "submit_to_queue", mock_submit)

    # Mock __file__ to point to our test directory
    monkeypatch.setattr(
        "scrapers.sample_scraper.__file__",
        str(
            sample_geojson.parent.parent.parent.parent.parent
            / "app/scraper/sample_scraper.py"
        ),
    )

    # Set test file
    scraper.set_test_file(sample_geojson)

    # Run scraper
    await scraper.run()

    # Verify exactly one job was submitted
    assert len(submitted_jobs) == 1

    # Verify job content
    job = json.loads(submitted_jobs[0])
    assert job["Name"] == "Test Location"
    assert job["Address"] == "123 Test St"
    assert job["collection_name"] == "Test Collection"
    assert job["collection_category"] == "Test Category"


@pytest.mark.asyncio
async def test_sample_scraper_empty_scrape() -> None:
    """Test that scrape() returns empty string as expected."""
    scraper = SampleScraper()
    result = await scraper.scrape()
    assert result == ""
