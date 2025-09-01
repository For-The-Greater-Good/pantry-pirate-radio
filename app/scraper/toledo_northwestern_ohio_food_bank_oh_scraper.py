"""Scraper for Toledo Northwestern Ohio Food Bank."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class ToledoNorthwesternOhioFoodBankOHScraper(ScraperJob):
    """Scraper for Toledo Northwestern Ohio Food Bank."""

    def __init__(
        self,
        scraper_id: str = "toledo_northwestern_ohio_food_bank_oh",
        test_mode: bool = False,
    ) -> None:
        """Initialize scraper with ID 'toledo_northwestern_ohio_food_bank_oh' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'toledo_northwestern_ohio_food_bank_oh'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # StorePoint API endpoint
        self.api_base = "https://api.storepoint.co/v1/1662a5ad8a1488"
        self.url = "https://www.toledofoodbank.org/findfood"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

    async def download_html(self) -> str:
        """Download HTML content from the website.

        Returns:
            str: Raw HTML content

        Raises:
            requests.RequestException: If download fails
        """
        logger.info(f"Downloading HTML from {self.url}")
        response = requests.get(
            self.url, headers=get_scraper_headers(), timeout=self.timeout
        )
        response.raise_for_status()
        return response.text

    async def fetch_api_data(
        self, endpoint: str = "locations", params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fetch data from StorePoint API.

        Args:
            endpoint: API endpoint path (default: "locations")
            params: Optional query parameters

        Returns:
            API response as dictionary

        Raises:
            httpx.HTTPError: If API request fails
        """
        url = f"{self.api_base}/{endpoint}"

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(),
                timeout=httpx.Timeout(self.timeout, connect=self.timeout / 3),
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching data from {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching data from {url}: {e}")
            raise

    def parse_html(self, html: str) -> List[Dict[str, Any]]:
        """Parse HTML to extract food pantry information.

        Args:
            html: Raw HTML content

        Returns:
            List of dictionaries containing food pantry information
        """
        soup = BeautifulSoup(html, "html.parser")
        locations: List[Dict[str, Any]] = []

        # TODO: Update selectors based on actual website structure
        # Common patterns to look for:
        # - Tables with location data
        # - Divs/sections with location cards
        # - Lists of locations

        # This scraper uses API, not HTML parsing
        # Return empty list as we use the StorePoint API instead
        _ = soup  # Mark as used to satisfy linter

        logger.info(f"Parsed {len(locations)} locations from HTML")
        return locations

    def process_api_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process StorePoint API response data.

        Args:
            data: API response data

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        # StorePoint API returns {"success": true, "results": {"locations": [...]}}
        location_list = []
        if isinstance(data, dict):
            if "results" in data and isinstance(data["results"], dict):
                location_list = data["results"].get("locations", [])
            elif "locations" in data:
                location_list = data["locations"]
        elif isinstance(data, list):
            location_list = data

        for item in location_list:
            # Parse address from streetaddress field
            address_parts = (item.get("streetaddress") or "").split(",")
            if len(address_parts) >= 3:
                street_address = address_parts[0].strip()
                city = address_parts[1].strip()
                state_zip = address_parts[2].strip()
                # Extract state and zip
                state_zip_parts = state_zip.split()
                state = state_zip_parts[0] if state_zip_parts else "OH"
                zip_code = state_zip_parts[1] if len(state_zip_parts) > 1 else ""
            else:
                street_address = (item.get("streetaddress") or "").strip()
                city = ""
                state = "OH"
                zip_code = ""

            # Parse hours from description field if available
            hours = (item.get("description") or "").strip()

            # Parse services from tags field
            services = []
            tags = item.get("tags") or ""
            if tags:
                services = [tags] if isinstance(tags, str) else tags

            location = {
                "id": item.get("id"),
                "name": (item.get("name") or "").strip(),
                "address": street_address,
                "city": city,
                "state": state,
                "zip": zip_code,
                "phone": (item.get("phone") or "").strip(),
                "latitude": item.get("loc_lat"),
                "longitude": item.get("loc_long"),
                "hours": hours,
                "services": services,
                "website": (item.get("website") or "").strip(),
                "facebook": (item.get("facebook") or "").strip(),
                "email": (item.get("email") or "").strip(),
                "notes": (item.get("extra") or "").strip(),
            }

            # Only add locations with names
            if location["name"]:
                locations.append(location)

        logger.info(f"Processed {len(locations)} locations from API")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # Use StorePoint API to fetch all locations
        logger.info("Fetching locations from StorePoint API")

        # StorePoint API returns all locations without parameters
        response = await self.fetch_api_data("locations")
        locations = self.process_api_response(response)

        # Deduplicate locations if needed
        unique_locations = []
        seen_ids = set()

        for location in locations:
            # Create unique ID (adjust based on your data)
            location_id = f"{location.get('name', '')}_{location.get('address', '')}"

            if location_id not in seen_ids:
                seen_ids.add(location_id)
                unique_locations.append(location)

        logger.info(
            f"Found {len(unique_locations)} unique locations (from {len(locations)} total)"
        )

        # Process each location
        job_count = 0

        for location in unique_locations:
            # Note: Latitude and longitude will be handled by the validator service
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Toledo Northwestern Ohio Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "jobs_created": job_count,
            "source": self.url,
        }

        # Print summary to CLI
        print(f"{'='*60}")
        print("Toledo Northwestern Ohio Food Bank Scraper Summary")
        print(f"{'='*60}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        if self.test_mode:
            print("TEST MODE: Limited processing")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
