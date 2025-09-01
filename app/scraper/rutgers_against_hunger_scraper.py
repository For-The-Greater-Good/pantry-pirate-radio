"""Scraper for Rutgers Against Hunger (RAH) local food pantries."""

import json
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Rutgers_Against_HungerScraper(ScraperJob):
    """Scraper for Rutgers Against Hunger (RAH) local food pantries."""

    def __init__(self, scraper_id: str = "rutgers_against_hunger") -> None:
        """Initialize scraper with ID 'rutgers_against_hunger' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'rutgers_against_hunger'
        """
        super().__init__(scraper_id=scraper_id)
        self.url = "https://rah.rutgers.edu/resources/local-pantries/"

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

    def parse_html(self, html: str) -> list[dict[str, Any]]:
        """Parse HTML to extract food pantry information.

        Args:
            html: Raw HTML content

        Returns:
            List of dictionaries containing food pantry information
        """
        soup = BeautifulSoup(html, "html.parser")
        pantries: list[dict[str, Any]] = []

        # Find all accordion elements which contain county data
        accordions = soup.find_all("div", class_="gb-block-accordion")

        if not accordions:
            logger.warning("No accordion elements found in HTML")
            return pantries

        logger.info(f"Found {len(accordions)} county accordions")

        # Process each accordion (county)
        for accordion in accordions:
            # Extract county name from summary
            county_elem = accordion.find("summary", class_="gb-accordion-title")  # type: ignore
            if not county_elem or not hasattr(county_elem, "get_text"):
                continue

            county_text = county_elem.get_text(strip=True)  # type: ignore
            if not isinstance(county_text, str):
                continue
            county = county_text.replace(" County", "")

            # Find the table in this accordion
            table = accordion.find("table")  # type: ignore
            if not table or not hasattr(table, "find_all"):
                continue

            # Find all rows in the table (skip header row)
            rows = table.find_all("tr")[1:]  # Skip header row

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 3:  # Need at least name, services, city
                    continue

                # Extract data from cells
                name = cells[0].get_text(strip=True)

                # Check if there's a link with more info
                link = cells[0].find("a")
                url = link["href"] if link and "href" in link.attrs else ""

                services = cells[1].get_text(strip=True)
                city = cells[2].get_text(strip=True)

                # Get phone if available (4th column)
                phone = cells[3].get_text(strip=True) if len(cells) > 3 else ""

                # Create address from city and county
                address = f"{city}, {county} County, NJ"

                # Add to pantries list
                pantry = {
                    "name": name,
                    "services": services,
                    "address": address,
                    "city": city,
                    "county": county,
                    "state": "NJ",
                    "phone": phone,
                    "url": url,
                }

                pantries.append(pantry)

        logger.info(f"Extracted {len(pantries)} pantries from HTML")
        return pantries

    def transform_to_hsds(self, pantry: dict[str, Any]) -> dict[str, Any]:
        """Transform pantry data to HSDS format.

        Args:
            pantry: Pantry data from website

        Returns:
            Pantry data in HSDS format
        """
        # Extract basic information
        hsds_data = {
            "name": pantry.get("name", ""),
            "alternate_name": "",
            "description": f"Food pantry in {pantry.get('county', '')} County, NJ. Services: {pantry.get('services', '')}",
            "email": "",
            "url": pantry.get("url", ""),
            "status": "active",
            "address": {
                "address_1": "",  # We don't have street address
                "address_2": "",
                "city": pantry.get("city", ""),
                "state_province": "NJ",
                "postal_code": "",
                "country": "US",
            },
            "phones": [],
        }

        # Add phone if available
        if pantry.get("phone"):
            hsds_data["phones"] = [{"number": pantry["phone"], "type": "voice"}]

        # Add coordinates if available
        if "latitude" in pantry and "longitude" in pantry:
            hsds_data["location"] = {
                "latitude": pantry["latitude"],
                "longitude": pantry["longitude"],
            }

        # Add service attributes
        hsds_data["service_attributes"] = []

        # Add service type
        if pantry.get("services"):
            hsds_data["service_attributes"].append(
                {"attribute_key": "PROGRAM_TYPE", "attribute_value": pantry["services"]}
            )

        # Add county
        if pantry.get("county"):
            hsds_data["service_attributes"].append(
                {"attribute_key": "COUNTY", "attribute_value": pantry["county"]}
            )

        return hsds_data

    async def scrape(self) -> str:
        """Scrape data from Rutgers Against Hunger website.

        Returns:
            Summary of scraping operation as JSON string
        """
        # 1. Download HTML
        html = await self.download_html()

        # 2. Parse HTML to extract food pantry information
        pantries = self.parse_html(html)

        # 3. Process pantries and submit to queue
        job_count = 0
        failed_pantries = []

        for pantry in pantries:
            # Note: Latitude and longitude will be handled by the validator service

            # Add metadata
            pantry["source"] = "rutgers_against_hunger"

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
            "failed_pantries": len(failed_pantries),
            "source": self.url,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Rutgers Against Hunger")
        print(f"{'='*60}")
        print(f"URL: {self.url}")
        print(f"Total pantries found: {len(pantries)}")
        print(f"Jobs created: {job_count}")
        print(f"Failed processing: {len(failed_pantries)}")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
