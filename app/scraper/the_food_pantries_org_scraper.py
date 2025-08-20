"""Scraper for map.thefoodpantries.org data."""

import json
import logging
import re
from typing import Any, cast

import httpx

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class The_Food_Pantries_OrgScraper(ScraperJob):
    """Scraper for map.thefoodpantries.org data."""

    def __init__(self, scraper_id: str = "the_food_pantries_org") -> None:
        """Initialize scraper with ID 'food_pantries_map' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'food_pantries_map'
        """
        super().__init__(scraper_id=scraper_id)
        self.url = "https://map.thefoodpantries.org"

    async def download_html(self) -> str:
        """Download HTML content from the website.

        Returns:
            str: Raw HTML content

        Raises:
            httpx.HTTPError: If download fails
        """
        logger.info(f"Downloading data from {self.url}")
        async with httpx.AsyncClient(headers=get_scraper_headers()) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            return response.text

    def extract_json(self, html: str) -> str:
        """Extract JSON data from HTML content.

        Args:
            html: Raw HTML content

        Returns:
            str: Extracted JSON string

        Raises:
            ValueError: If JSON data cannot be found or is invalid
        """
        # Look for container elements with resource-data attribute
        pattern = r'<container[^>]*resource-data="([^"]*)"'
        matches = re.finditer(pattern, html, re.DOTALL)

        # Combine all matches into a single array
        features: list[dict[str, Any]] = []
        collection_name = "Food Pantries"  # Default name

        for match in matches:
            # Get the value of the resource-data attribute
            json_str = match.group(1)
            # Unescape any HTML entities
            json_str = json_str.replace("&quot;", '"')

            try:
                data = json.loads(json_str)
                if isinstance(data, list):
                    for item in cast(list[dict[str, Any]], data):
                        if item.get("type") == "FeatureCollection":
                            if "features" in item and isinstance(
                                item["features"], list
                            ):
                                features.extend(
                                    cast(list[dict[str, Any]], item["features"])
                                )
                            # Get collection name from first valid item
                            if (
                                not collection_name
                                or collection_name == "Food Pantries"
                            ):
                                collection_name = cast(
                                    str, item.get("name", "Food Pantries")
                                )
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON data in match: {e}")
                continue

        if not features:
            raise ValueError("Could not find GeoJSON data")

        # Create a single FeatureCollection with all features
        json_str = json.dumps(
            [
                {
                    "type": "FeatureCollection",
                    "name": collection_name,
                    "category": "Food Pantry",
                    "features": features,
                }
            ]
        )

        # Validate it's valid JSON and matches expected structure
        try:
            data = json.loads(json_str)
            # Verify it's an array containing a FeatureCollection
            if (
                not isinstance(data, list)
                or not data
                or cast(dict[str, Any], data[0]).get("type") != "FeatureCollection"
            ):
                raise ValueError(
                    "JSON data is not in expected format (array containing FeatureCollection)"
                )
            return json_str
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON data: {e}")

    async def scrape(self) -> str:
        """Download and process data from map.thefoodpantries.org.

        Returns:
            str: Summary of scraping results as JSON

        Raises:
            httpx.HTTPError: If download fails
            ValueError: If data parsing fails
        """
        # Download HTML
        html = await self.download_html()

        # Extract JSON
        raw_content = self.extract_json(html)
        data = json.loads(raw_content)

        # Process features from the collection
        # The data is an array with a single FeatureCollection
        collection = cast(dict[str, Any], data[0])
        job_count = 0
        if "features" in collection:
            # Submit each feature (food pantry location) as a separate job
            for feature in cast(list[dict[str, Any]], collection["features"]):
                # Enrich properties with collection metadata
                properties = cast(dict[str, Any], feature["properties"])
                properties["collection_name"] = cast(str, collection.get("name", ""))
                properties["collection_category"] = cast(
                    str, collection.get("category", "")
                )

                # Submit feature properties to queue
                job_id = self.submit_to_queue(json.dumps(properties))
                job_count += 1
                logger.info(f"Queued job {job_id}")

        # Create summary for return
        summary = {
            "scraper_id": self.scraper_id,
            "source": self.url,
            "total_features": len(collection.get("features", [])),
            "jobs_created": job_count,
            "collection_name": collection.get("name", ""),
            "status": "complete"
        }

        # Print summary to CLI
        print("\nScraper Summary:")
        print(f"Source: {self.url}")
        print(f"Total jobs created: {job_count}")
        print("Status: Complete\n")

        # Return summary instead of raw content to prevent duplicate submission
        return json.dumps(summary)
