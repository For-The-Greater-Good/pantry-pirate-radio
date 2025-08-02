"""Scraper for Community Food Bank of San Benito County."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class CommunityFoodBankOfSanBenitoCountyCaScraper(ScraperJob):
    """Scraper for Community Food Bank of San Benito County."""

    def __init__(
        self,
        scraper_id: str = "community_food_bank_of_san_benito_county_ca",
        test_mode: bool = False,
    ) -> None:
        """Initialize scraper with ID 'community_food_bank_of_san_benito_county_ca' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'community_food_bank_of_san_benito_county_ca'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # URL for local pick-up locations
        self.url = "https://www.communityfoodbankofsbc.org/local-pick-up-locations/"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "CA": (36.8508, -121.4013),  # San Benito County, CA center
                "San Benito": (36.8508, -121.4013),  # San Benito County center
                "Hollister": (36.8525, -121.4016),  # Hollister, CA
                "San Juan Bautista": (36.8455, -121.5380),  # San Juan Bautista, CA
                "Aromas": (36.8886, -121.6430),  # Aromas, CA
                "Tres Pinos": (36.7905, -121.3212),  # Tres Pinos, CA
            }
        )

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

        # Find the main content area
        main_content = soup.find("main")
        if not main_content:
            logger.warning("Could not find main content area")
            return locations

        # Extract contact phone from the page
        phone = "(831) 637-0340"  # Default from contact info

        # Parse the content text
        content_text = main_content.get_text(separator="\n", strip=True)
        lines = content_text.split("\n")

        current_day = None
        current_city = "Hollister"  # Default for mobile pantry
        i = 0

        # Track if we're in mobile pantry section or static locations section
        in_mobile_section = True

        while i < len(lines):
            line = lines[i].strip()

            # Check if we've reached the static locations section
            if "Pre-packed grocery bags are available" in line:
                in_mobile_section = False
                current_day = None
                i += 1
                continue

            # Mobile pantry section parsing
            if in_mobile_section:
                # Check for mobile pantry days
                if line.endswith(":") and line.rstrip(":") in [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                ]:
                    current_day = line.rstrip(":")
                    i += 1
                    continue

                # Parse mobile pantry locations (format: "Location – Time")
                if (
                    current_day
                    and "–" in line
                    and ("a.m." in line or "p.m." in line)
                    and not line.startswith("Time:")
                ):
                    parts = line.split("–", 1)
                    if len(parts) == 2:
                        location_name = parts[0].strip()
                        hours = parts[1].strip()

                        location = {
                            "name": f"Mobile Pantry - {location_name}",
                            "address": f"{location_name}, {current_city}, CA",
                            "city": current_city,
                            "state": "CA",
                            "zip": "",
                            "phone": phone,
                            "hours": f"{current_day}: {hours}",
                            "services": ["food pantry", "mobile pantry"],
                            "website": self.url,
                            "notes": "Mobile Pantry distribution",
                        }
                        locations.append(location)

            # Static locations section parsing
            else:
                # Parse static locations
                if line in [
                    "Aromas",
                    "Hollister – Marketplace at Community Food Bank (Drive-Thru available)",
                    "San Juan Bautista",
                    "Tres Pinos",
                ]:
                    location_data = {
                        "name": line,
                        "services": ["food pantry", "pre-packed bags"],
                    }

                    # Extract location details from subsequent lines
                    j = i + 1
                    while j < len(lines) and j < i + 5:  # Look ahead up to 5 lines
                        detail_line = lines[j].strip()

                        if detail_line.startswith("Location:"):
                            location_data["address"] = detail_line.replace(
                                "Location:", ""
                            ).strip()
                        elif detail_line.startswith("Time:"):
                            location_data["hours"] = detail_line.replace(
                                "Time:", ""
                            ).strip()
                        elif "Drive-Thru available" in detail_line:
                            location_data["services"].append("drive-thru")
                            location_data["notes"] = detail_line
                        elif any(
                            day in detail_line
                            for day in [
                                "Monday",
                                "Tuesday",
                                "Wednesday",
                                "Thursday",
                                "Friday",
                                "Saturday",
                                "Sunday",
                            ]
                        ) and not detail_line.startswith("Time:"):
                            # Additional hours info
                            if "hours" in location_data:
                                location_data["hours"] += f"; {detail_line}"
                            else:
                                location_data["hours"] = detail_line
                        j += 1

                    # Set city based on location name
                    if "Aromas" in line:
                        location_data["city"] = "Aromas"
                    elif "San Juan Bautista" in line:
                        location_data["city"] = "San Juan Bautista"
                    elif "Tres Pinos" in line:
                        location_data["city"] = "Tres Pinos"
                    else:
                        location_data["city"] = "Hollister"

                    # Add default values
                    location_data["state"] = "CA"
                    location_data["zip"] = ""
                    location_data["phone"] = phone
                    location_data["website"] = self.url

                    if "address" in location_data:  # Only add if we found address info
                        locations.append(location_data)

            i += 1

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
        # grid_points = self.utils.get_state_grid_points("ca")
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
        geocoding_stats = {"success": 0, "failed": 0, "default": 0}

        for location in unique_locations:
            # Geocode address if not already present
            if not (location.get("latitude") and location.get("longitude")):
                if location.get("address"):
                    try:
                        lat, lon = self.geocoder.geocode_address(
                            address=location["address"],
                            state=location.get("state", "CA"),
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["success"] += 1
                    except ValueError as e:
                        logger.warning(
                            f"Geocoding failed for {location['address']}: {e}"
                        )
                        # Use default coordinates
                        lat, lon = self.geocoder.get_default_coordinates(
                            location="CA", with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["failed"] += 1
                else:
                    # No address, use defaults
                    lat, lon = self.geocoder.get_default_coordinates(
                        location="CA", with_offset=True
                    )
                    location["latitude"] = lat
                    location["longitude"] = lon
                    geocoding_stats["default"] += 1

            # Add metadata
            location["source"] = "community_food_bank_of_san_benito_county_ca"
            location["food_bank"] = "Community Food Bank of San Benito County"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Community Food Bank of San Benito County",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print(f"SCRAPER SUMMARY: Community Food Bank of San Benito County")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        print(
            f"Geocoding - Success: {geocoding_stats['success']}, Failed: {geocoding_stats['failed']}, Default: {geocoding_stats['default']}"
        )
        if self.test_mode:
            print(f"TEST MODE: Limited processing")
        print(f"Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
