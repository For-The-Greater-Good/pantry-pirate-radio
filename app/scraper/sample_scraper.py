"""Sample scraper that processes GeoJSON data from thefoodpantries.org."""

import json
import logging
from pathlib import Path
from typing import Any, cast

from app.scraper.utils import ScraperJob

logger = logging.getLogger(__name__)


class SampleScraper(ScraperJob):
    """Sample scraper that processes GeoJSON data from thefoodpantries.org."""

    _test_file: Path | None = None

    def __init__(self, scraper_id: str = "sample") -> None:
        """Initialize scraper with ID 'sample' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'sample'
        """
        super().__init__(scraper_id=scraper_id)

    def set_test_file(self, path: Path) -> None:
        """Set test file path for testing.

        Args:
            path: Path to test file
        """
        self._test_file = path

    async def run(self) -> None:
        """Override run to handle feature-level job submission."""
        try:
            # Read GeoJSON file or use sample data
            if self._test_file is not None:
                geojson_path = self._test_file
                if not geojson_path.exists():
                    raise FileNotFoundError(f"GeoJSON file not found: {geojson_path}")
                with open(geojson_path) as f:
                    raw_content = f.read()
                    data = json.loads(raw_content)
            else:
                # Use embedded sample data for production containers
                data = [
                    {
                        "name": "Sample Food Pantries",
                        "category": "Food Assistance",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {
                                    "name": "Sample Food Pantry 1",
                                    "address": "123 Main St, New York, NY 10001",
                                    "phone": "(555) 123-4567",
                                    "hours": "Mon-Fri 9am-5pm",
                                    "description": "A sample food pantry for testing deduplication",
                                },
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [-74.0060, 40.7128],
                                },
                            },
                            {
                                "type": "Feature",
                                "properties": {
                                    "name": "Sample Food Pantry 2",
                                    "address": "456 Broadway, New York, NY 10013",
                                    "phone": "(555) 987-6543",
                                    "hours": "Tue-Sat 10am-6pm",
                                    "description": "Another sample food pantry for testing",
                                },
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [-74.0000, 40.7200],
                                },
                            },
                        ],
                    }
                ]

            # Process features from the collection
            collection = cast(dict[str, Any], data[0])
            if "features" in collection:
                # Submit each feature (food pantry location) as a separate job
                for feature in cast(list[dict[str, Any]], collection["features"]):
                    # Enrich properties with collection metadata
                    properties = cast(dict[str, Any], feature["properties"])
                    properties["collection_name"] = cast(
                        str, collection.get("name", "")
                    )
                    properties["collection_category"] = cast(
                        str, collection.get("category", "")
                    )

                    # Submit feature properties to queue
                    job_id = self.submit_to_queue(json.dumps(properties))
                    logger.info(f"Queued job {job_id}")

        except Exception:
            raise

    async def scrape(self) -> str:
        """Implement required scrape method but defer processing to run().

        Returns:
            Empty string since processing is handled in run()
        """
        return ""
