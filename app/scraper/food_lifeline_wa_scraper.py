"""Scraper for Food Lifeline."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FoodLifelineWAScraper(ScraperJob):
    """Scraper for Food Lifeline."""

    def __init__(
        self, scraper_id: str = "food_lifeline_wa", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'food_lifeline_wa' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'food_lifeline_wa'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # TODO: Update this URL based on the food bank's website
        self.url = "https://foodlifeline.org/need-food/"
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

        # Find all location popups - they contain the data
        location_popups = soup.find_all("div", class_="location-popup")

        logger.info(f"Found {len(location_popups)} location popups in HTML")

        for popup in location_popups:
            try:
                # Extract location ID from data attribute
                location_id = popup.get("data-location", "")

                # Find the heading (location name)
                heading = popup.find("h2", class_="heading")
                name = heading.text.strip() if heading else ""

                # Find the address
                address_div = popup.find("div", class_="address")
                full_address = address_div.text.strip() if address_div else ""

                # Parse address components
                address_parts = full_address.split(",") if full_address else []
                street = address_parts[0].strip() if len(address_parts) > 0 else ""
                city = address_parts[1].strip() if len(address_parts) > 1 else ""
                state_zip = address_parts[2].strip() if len(address_parts) > 2 else "WA"

                # Extract state and zip
                state_zip_parts = state_zip.split()
                state = state_zip_parts[0] if len(state_zip_parts) > 0 else "WA"
                zip_code = state_zip_parts[1] if len(state_zip_parts) > 1 else ""

                # Find service types
                service_types = []
                type_divs = popup.find_all("div", class_="type")
                for type_div in type_divs:
                    service_type = type_div.text.strip()
                    if service_type:
                        service_types.append(service_type)

                # Find email
                email_link = popup.find(
                    "a", href=lambda x: x and x.startswith("mailto:")
                )
                email = email_link["href"].replace("mailto:", "") if email_link else ""

                # Find website
                website_link = popup.find("a", string=lambda x: x and "Visit Site" in x)
                website = (
                    website_link["href"]
                    if website_link and website_link.get("href")
                    else ""
                )

                # Find phone
                phone_link = popup.find("a", href=lambda x: x and x.startswith("tel:"))
                phone = phone_link.text.strip() if phone_link else ""

                # Create location object
                location = {
                    "id": location_id,
                    "name": name,
                    "address": street,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "phone": phone,
                    "email": email,
                    "website": website,
                    "services": service_types,
                    "full_address": full_address,
                }

                # Skip empty items
                if not location["name"]:
                    continue

                locations.append(location)

            except Exception as e:
                logger.warning(f"Error parsing location popup: {e}")
                continue

        logger.info(f"Successfully parsed {len(locations)} locations from HTML")
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
        #         "state": item.get("state", "WA").strip(),
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
        # TODO: Choose the appropriate scraping approach

        # Option 1: HTML Scraping
        # =====================
        # Download and parse HTML
        html = await self.download_html()
        locations = self.parse_html(html)

        # Option 2: API Scraping
        # =====================
        # # Fetch data from API
        # response = await self.fetch_api_data("endpoint/path", params={"key": "value"})
        # locations = self.process_api_response(response)

        # Option 3: Grid-based API Search (for APIs with geographic search)
        # ================================================================
        # from app.models.geographic import GridPoint
        #
        # # Get grid points for the state
        # grid_points = self.utils.get_state_grid_points("wa")
        #
        # # Limit grid points in test mode
        # if self.test_mode:
        #     grid_points = grid_points[:3]
        #
        # locations = []
        # for i, point in enumerate(grid_points):
        #     if i > 0:
        #         await asyncio.sleep(self.request_delay)
        #
        #     # Search around this grid point
        #     response = await self.fetch_api_data(
        #         "search",
        #         params={"lat": point.lat, "lng": point.lng, "radius": 50}
        #     )
        #     locations.extend(self.process_api_response(response))

        # Deduplicate locations if needed
        unique_locations = []
        seen_ids = set()

        for location in locations:
            # Use the location ID from the data, or create one from name/address
            location_id = (
                location.get("id")
                or f"{location.get('name', '')}_{location.get('address', '')}"
            )

            if location_id not in seen_ids and location_id:
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
            "food_bank": "Food Lifeline WA",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "jobs_created": job_count,
            "source": self.url,
        }

        # Print summary to CLI
        print(f"{'='*60}")
        print(f"Food Lifeline WA Scraper Summary")
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
