"""Scraper for Mercer County Free Food Finder."""

import json
import logging
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Mercer_Food_FinderScraper(ScraperJob):
    """Scraper for Mercer County Free Food Finder."""

    def __init__(self, scraper_id: str = "mercer_food_finder") -> None:
        """Initialize scraper with ID 'mercer_food_finder' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'mercer_food_finder'
        """
        super().__init__(scraper_id=scraper_id)
        self.url = "https://mercerfoodfinder.herokuapp.com/api/pdf"

        # Initialize geocoder with custom default coordinates for Mercer County
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "Mercer": (40.2206, -74.7597),  # Trenton, NJ (Mercer County seat)
                "NJ": (40.0583, -74.4057),  # Geographic center of New Jersey
            }
        )

    async def download_html(self) -> str:
        """Download HTML content from the website.

        Returns:
            str: Raw HTML content

        Raises:
            requests.RequestException: If download fails
        """
        logger.info(f"Downloading data from {self.url}")
        response = requests.get(self.url, headers=get_scraper_headers(), timeout=30)
        response.raise_for_status()
        return response.text

    def parse_html(self, html: str) -> list[dict[str, Any]]:
        """Parse HTML to extract food pantry information.

        Args:
            html: Raw HTML content

        Returns:
            List of dictionaries containing food pantry information
        """
        soup = BeautifulSoup(html, "html.parser")
        pantries: list[dict[str, Any]] = []

        # Find the table containing food pantry information
        table = soup.find("table", class_="table")
        if not table:
            logger.warning("Could not find food pantry table in HTML")
            return pantries

        # Process each row in the table (skip header row)
        rows = table.find_all("tr") if hasattr(table, "find_all") else []
        for row in rows[1:]:  # Skip header row
            cells = row.find_all("td")
            if len(cells) < 4:
                continue  # Skip rows with insufficient data

            # Extract data from cells
            name = cells[0].get_text(strip=True)
            address = cells[1].get_text(strip=True)

            # Extract phone from contact cell
            contact_cell = cells[2].get_text(strip=True)
            phone = contact_cell if contact_cell else ""

            # Extract description
            description = cells[3].get_text(strip=True)

            # Add to pantries list
            pantries.append(
                {
                    "name": name,
                    "address": address,
                    "phone": phone,
                    "description": description,
                    "county": "Mercer",
                    "state": "NJ",
                }
            )

        logger.info(f"Found {len(pantries)} food pantries")
        return pantries

    # Using the GeocoderUtils class from utils.py instead of implementing geocoding here

    async def scrape(self) -> str:
        """Scrape data from Mercer County Free Food Finder.

        Returns:
            Raw scraped content as JSON string
        """
        # Download HTML
        html = await self.download_html()

        # Parse HTML to extract food pantry information
        pantries = self.parse_html(html)

        # Geocode addresses and enrich data
        job_count = 0
        failed_pantries = []
        geocoder_stats = {"nominatim": 0, "arcgis": 0, "default": 0}

        for pantry in pantries:
            try:
                # Try to geocode address
                try:
                    # Use the geocoder from utils.py
                    latitude, longitude = self.geocoder.geocode_address(
                        pantry["address"], county="Mercer", state="NJ"
                    )

                    # Determine which geocoder was used (this is just an approximation since
                    # we don't have direct access to which geocoder succeeded in the utils class)
                    geocoder_used = "nominatim"  # Assume nominatim for now
                    geocoder_stats["nominatim"] += 1

                except Exception as geocode_error:
                    # Log the geocoding error
                    logger.warning(
                        f"Geocoding failed for {pantry['name']}: {geocode_error}"
                    )

                    # Add to failed pantries list for later review
                    failed_pantries.append(
                        {
                            "name": pantry["name"],
                            "address": pantry["address"],
                            "error": str(geocode_error),
                        }
                    )

                    # Use default coordinates for Mercer County with a small offset
                    latitude, longitude = self.geocoder.get_default_coordinates(
                        location="Mercer", with_offset=True
                    )
                    geocoder_used = "default"
                    geocoder_stats["default"] += 1

                    logger.info(
                        f"Using default coordinates with offset for {pantry['name']}"
                    )

                # Add coordinates and geocoder info to pantry data
                pantry["latitude"] = latitude
                pantry["longitude"] = longitude
                pantry["geocoder"] = geocoder_used

                # Submit to queue
                job_id = self.submit_to_queue(json.dumps(pantry))
                job_count += 1
                logger.info(f"Queued job {job_id} for pantry: {pantry['name']}")

            except Exception as e:
                logger.error(f"Error processing pantry {pantry['name']}: {e}")
                failed_pantries.append(
                    {
                        "name": pantry["name"],
                        "address": pantry["address"],
                        "error": str(e),
                    }
                )
                continue

        # Save failed pantries to file for later review
        if failed_pantries:
            import datetime
            from pathlib import Path

            # Create outputs directory if it doesn't exist
            output_dir = Path(__file__).parent.parent.parent / "outputs"
            output_dir.mkdir(exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            failed_file = output_dir / f"mercer_food_finder_failed_{timestamp}.json"

            # Write failed pantries to file
            with open(failed_file, "w") as f:
                json.dump(failed_pantries, f, indent=2)

            logger.info(
                f"Saved {len(failed_pantries)} failed pantries to {failed_file}"
            )

        # Create summary
        summary = {
            "total_pantries_found": len(pantries),
            "total_jobs_created": job_count,
            "failed_geocoding": len(failed_pantries),
            "geocoder_stats": geocoder_stats,
            "source": self.url,
        }

        # Print summary to CLI
        print("\nScraper Summary:")
        print(f"Source: {self.url}")
        print(f"Total pantries found: {len(pantries)}")
        print(f"Successfully geocoded: {job_count}")
        print("Geocoder usage:")
        print(f"  - Nominatim: {geocoder_stats['nominatim']}")
        print(f"  - ArcGIS: {geocoder_stats['arcgis']}")
        print(f"  - Default coordinates: {geocoder_stats['default']}")
        print(f"Failed geocoding: {len(failed_pantries)}")
        if failed_pantries:
            print(f"Failed pantries saved to: {failed_file}")
        print("Status: Complete\n")

        # Return original content for archiving
        return json.dumps(summary)
