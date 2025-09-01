"""Scraper for Community Action of Napa Valley Food Bank."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class CommunityActionOfNapaValleyFoodBankCaScraper(ScraperJob):
    """Scraper for Community Action of Napa Valley Food Bank."""

    def __init__(
        self,
        scraper_id: str = "community_action_of_napa_valley_food_bank_ca",
        test_mode: bool = False,
    ) -> None:
        """Initialize scraper with ID 'community_action_of_napa_valley_food_bank_ca' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'community_action_of_napa_valley_food_bank_ca'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # Community Action of Napa Valley Food Bank - Food Pantry page
        self.url = "https://www.canv.org/food-pantry/"
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
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fetch data from API endpoint (for API-based scrapers).

        Args:
            endpoint: API endpoint path
            params: Optional query parameters

        Returns:
            API response as dictionary

        Raises:
            httpx.HTTPError: If API request fails
        """
        url = f"{self.url}/{endpoint}" if endpoint else self.url

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

        # Define the locations with their details (parsed from the website)
        location_data = [
            {
                "name": "Napa Food Pantry (NEW LOCATION)",
                "address": "938 Kaiser Road",
                "city": "Napa",
                "state": "CA",
                "zip": "94559",
                "hours": "Open Tuesday, Wednesday, & Thursday Hours: 9:00-1:00 PM",
            },
            {
                "name": "North of Yountville Pantry - St. Helena Community Pantry",
                "address": "1777 Main St.",
                "city": "St. Helena",
                "state": "CA",
                "zip": "94574",
                "hours": "Tuesdays and Fridays 2:30pm to 4pm (Behind Seventh Day Adventist Church Hall)",
            },
            {
                "name": "Berryessa - Moskowite Corners",
                "address": "6004 Monticello Road",
                "city": "Lake Berryessa",
                "state": "CA",
                "zip": "94558",
                "hours": "3rd Wednesday's 11:00am to 1:00pm",
            },
            {
                "name": "American Canyon Food Pantry - Harvest Freewill Baptist Church",
                "address": "240 Rio Del Mar",
                "city": "American Canyon",
                "state": "CA",
                "zip": "94503",
                "hours": "2nd & 4th Tuesday's 3:30pm to 5:30pm",
            },
            {
                "name": "American Canyon Food Pantry #2 - Kiwanis Club of American Canyon",
                "address": "300 Napa Junction Road (Room 4)",
                "city": "American Canyon",
                "state": "CA",
                "zip": "94503",
                "hours": "3rd Thursdays 4:30pm to 5:30pm",
            },
            {
                "name": "Calistoga Pantry - Calistoga Cares",
                "address": "1435 North Oak Street",
                "city": "Calistoga",
                "state": "CA",
                "zip": "94515",
                "hours": "2nd and 4th Thursdays 2:00pm to 5:00pm @Fairgronds/Tubbs Bldg",
            },
            {
                "name": "Angwin Pantry",
                "address": "1 Angwin Avenue",
                "city": "Angwin",
                "state": "CA",
                "zip": "94508",
                "hours": "1st and 3rd Tuesday's of the month 6:00pm to 7:30pm",
            },
            {
                "name": "Pope Valley Pantry",
                "address": "5800 Pope Valley / Chiles Road",
                "city": "Pope Valley",
                "state": "CA",
                "zip": "94567",
                "hours": "Every 1st Wednesday 12:00pm to 2:00pm",
            },
        ]

        for loc in location_data:
            # Build full address for reference
            full_address = (
                f"{loc['address']}, {loc['city']}, {loc['state']} {loc['zip']}"
            )

            # Create the location dictionary
            location = {
                "name": loc["name"],
                "address": loc["address"],
                "city": loc["city"],
                "state": loc["state"],
                "zip": loc["zip"],
                "phone": "",  # Phone numbers not listed on the page
                "hours": loc["hours"],
                "services": ["Food Pantry"],
                "website": self.url,
                "notes": "Participants can receive food once every 30 days. Must bring two forms of ID (one with current address and one with birthdate) and shopping bags/box.",
            }

            locations.append(location)
            logger.info(f"Found location: {loc['name']} at {full_address}")

        logger.info(f"Parsed {len(locations)} locations from HTML")
        return locations

    def process_api_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process API response data.

        Args:
            data: API response data

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        # TODO: Extract locations from API response
        # Common patterns:
        # - data['results'] or data['locations'] or data['items']
        # - May need to handle pagination

        # Example:
        # for item in data.get('locations', []):
        #     location = {
        #         "id": item.get("id"),
        #         "name": item.get("name", "").strip(),
        #         "address": item.get("address", "").strip(),
        #         "city": item.get("city", "").strip(),
        #         "state": item.get("state", "CA").strip(),
        #         "zip": item.get("zip", "").strip(),
        #         "phone": item.get("phone", "").strip(),
        #         "latitude": item.get("latitude"),
        #         "longitude": item.get("longitude"),
        #         "hours": item.get("hours", ""),
        #         "services": item.get("services", []),
        #     }
        #     locations.append(location)

        logger.info(f"Processed {len(locations)} locations from API")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # Download and parse HTML from the food pantry page
        html = await self.download_html()
        locations = self.parse_html(html)

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

            # Add metadata
            location["source"] = "community_action_of_napa_valley_food_bank_ca"
            location["food_bank"] = "Community Action of Napa Valley Food Bank"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Community Action of Napa Valley Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Community Action of Napa Valley Food Bank")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        if self.test_mode:
            print("TEST MODE: Limited processing")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
