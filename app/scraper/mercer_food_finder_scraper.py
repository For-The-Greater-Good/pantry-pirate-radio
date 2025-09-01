"""Scraper for Mercer County Free Food Finder."""

import json
import logging
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

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

    # Note: Geocoding will be handled by the validator service

    async def scrape(self) -> str:
        """Scrape data from Mercer County Free Food Finder.

        Returns:
            Raw scraped content as JSON string
        """
        # Download HTML
        html = await self.download_html()

        # Parse HTML to extract food pantry information
        pantries = self.parse_html(html)

        # Process pantries
        job_count = 0
        failed_pantries = []

        for pantry in pantries:
            # Note: Latitude and longitude will be handled by the validator service

            # Add metadata
            pantry["source"] = "mercer_food_finder"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(pantry))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for pantry: {pantry.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "total_pantries_found": len(pantries),
            "total_jobs_created": job_count,
            "failed_processing": len(failed_pantries),
            "source": self.url,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Mercer Food Finder")
        print(f"{'='*60}")
        print(f"URL: {self.url}")
        print(f"Total pantries found: {len(pantries)}")
        print(f"Jobs created: {job_count}")
        print(f"Failed processing: {len(failed_pantries)}")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
