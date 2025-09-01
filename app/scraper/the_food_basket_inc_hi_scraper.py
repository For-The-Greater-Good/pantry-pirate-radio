"""Scraper for The Food Basket, Inc. in Hawaii."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class The_Food_Basket_Inc_HiScraper(ScraperJob):
    """Scraper for The Food Basket, Inc. in Hawaii."""

    def __init__(
        self, scraper_id: str = "the_food_basket_inc_hi", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'the_food_basket_inc_hi' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'the_food_basket_inc_hi'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # The Food Basket Find Food Now page
        self.url = "https://www.hawaiifoodbasket.org/find-food-now"
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

        # The Food Basket has locations organized by area and day
        # First, check for area tabs (Hilo, Puna, Ka'u, etc.)
        area_sections = soup.find_all("article")

        # Also parse the main content with location listings by day
        for day_section in soup.find_all("div", class_="sqs-block-content"):
            # Look for day headings (Monday, Tuesday, etc.)
            day_heading = day_section.find("h2")
            if not day_heading or day_heading.text.strip() not in [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]:
                continue

            day_of_week = day_heading.text.strip()

            # Find all lists after this heading
            for ul in day_section.find_all("ul"):
                items = ul.find_all("li")
                if len(items) >= 3:  # We expect at least: service type, name, address
                    service_type = items[0].text.strip() if items[0] else ""
                    name = items[1].text.strip() if items[1] else ""

                    # Initialize location data
                    location_data = {
                        "name": name,
                        "services": [service_type] if service_type else [],
                        "state": "HI",
                        "address": "",
                        "city": "",
                        "zip": "",
                        "phone": "",
                        "hours": "",
                        "notes": "",
                        "day_of_week": day_of_week,
                    }

                    # Parse remaining items for address, hours, phone, etc.
                    for item in items[2:]:
                        text = item.text.strip()

                        # Check if it's an address link
                        address_link = item.find("a")
                        if address_link and "tinyurl.com" in address_link.get(
                            "href", ""
                        ):
                            # Extract full address
                            full_address = text
                            location_data["address"] = full_address

                            # Try to parse city and zip
                            parts = full_address.split(",")
                            if len(parts) >= 3:
                                # Address format: "123 Main St, City, HI 96720"
                                city_part = parts[1].strip()
                                state_zip = parts[2].strip()
                                location_data["city"] = city_part

                                # Extract zip from state_zip
                                zip_parts = state_zip.split()
                                if len(zip_parts) >= 2:
                                    location_data["zip"] = zip_parts[-1]
                            elif len(parts) == 2:
                                # Address format: "123 Main St, Hawaii 96720"
                                city_state_zip = parts[-1].strip()
                                # Extract city and zip from "City, HI 96720" format
                                if " HI " in city_state_zip:
                                    city = city_state_zip.split(" HI ")[0].strip()
                                    zip_code = city_state_zip.split(" HI ")[1].strip()
                                    location_data["city"] = city
                                    location_data["zip"] = zip_code
                                elif "Hawaii" in city_state_zip:
                                    # Handle "Hilo, Hawaii 96720" format
                                    city_parts = city_state_zip.split(" Hawaii ")
                                    if len(city_parts) == 2:
                                        location_data["city"] = city_parts[0].strip()
                                        location_data["zip"] = city_parts[1].strip()

                        # Check for phone number
                        elif text.startswith("(") and ")" in text and "-" in text:
                            location_data["phone"] = text

                        # Check for hours/days
                        elif "Days/Hours:" in text or "•" in text:
                            if "•" in text:
                                hours_text = (
                                    text.split("•", 1)[1].strip()
                                    if "•" in text
                                    else text
                                )
                                location_data["hours"] = hours_text

                        # Check for location notes
                        elif "Location Notes:" in text:
                            # Get the next item as the note
                            idx = items.index(item)
                            if idx + 1 < len(items):
                                location_data["notes"] = items[idx + 1].text.strip()

                    # Only add if we have a name and some location info
                    if location_data["name"] and (
                        location_data["address"] or location_data["hours"]
                    ):
                        locations.append(location_data)

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
        #         "state": item.get("state", "HI").strip(),
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
        # Download and parse HTML
        html = await self.download_html()
        locations = self.parse_html(html)

        # In test mode, limit locations
        if self.test_mode and len(locations) > 5:
            locations = locations[:5]
            logger.info(f"Test mode: Limited to {len(locations)} locations")

        # Deduplicate locations by name and address
        unique_locations = []
        seen_ids = set()

        for location in locations:
            # Create unique ID based on name and address
            location_id = f"{location.get('name', '')}_{location.get('address', '')}"

            if location_id not in seen_ids and location.get("name"):
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
            "food_bank": "The Food Basket Inc HI",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "jobs_created": job_count,
            "source": self.url,
        }

        # Print summary to CLI
        print(f"{'='*60}")
        print("The Food Basket Inc HI Scraper Summary")
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
