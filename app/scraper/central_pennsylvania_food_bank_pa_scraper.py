"""Scraper for Central Pennsylvania Food Bank."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class CentralPennsylvaniaFoodBankPAScraper(ScraperJob):
    """Scraper for Central Pennsylvania Food Bank."""

    def __init__(
        self,
        scraper_id: str = "central_pennsylvania_food_bank_pa",
        test_mode: bool = False,
    ) -> None:
        """Initialize scraper with ID 'central_pennsylvania_food_bank_pa' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'central_pennsylvania_food_bank_pa'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # TODO: Update this URL based on the food bank's website
        self.url = "https://www.centralpafoodbank.org/find-help/"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                # TODO: Add appropriate default coordinates for the region
                "PA": (40.590752, -77.209755),  # Central Pennsylvania Food Bank region
                # Add county-level defaults if needed
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
        # Store Locator Plus API endpoint
        base_url = "https://dashboard.storelocatorplus.com/mstafford_at_centralpafoodbank_dot_org/wp-json/myslp/v2"
        url = f"{base_url}/{endpoint}"

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(),
                timeout=httpx.Timeout(self.timeout, connect=self.timeout / 3),
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()

                # Handle JSONP response
                text = response.text
                if text.startswith("initMySLP(") and text.endswith(");"):
                    # Extract JSON from JSONP wrapper
                    text = text[10:-2]

                return json.loads(text)
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

        # Example: Find location containers
        location_elements = soup.find_all("div", class_="location")  # Update selector

        for element in location_elements:
            # Extract information from each location
            location = {
                "name": "",  # TODO: Extract name
                "address": "",  # TODO: Extract address
                "city": "",  # TODO: Extract city
                "state": "PA",
                "zip": "",  # TODO: Extract zip
                "phone": "",  # TODO: Extract phone
                "hours": "",  # TODO: Extract hours
                "services": [],  # TODO: Extract services
                "website": "",  # TODO: Extract website
                "notes": "",  # TODO: Extract any additional notes
            }

            # Skip empty items
            if not location["name"]:
                continue

            locations.append(location)

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

        # Extract locations from Store Locator Plus API response
        # The response can have locations in different places depending on the endpoint
        raw_locations = []

        if isinstance(data, dict):
            if "response" in data and isinstance(data["response"], list):
                raw_locations = data["response"]
            elif "results" in data and isinstance(data["results"], list):
                raw_locations = data["results"]
            elif "locations" in data and isinstance(data["locations"], list):
                raw_locations = data["locations"]
            elif isinstance(data.get("data"), list):
                raw_locations = data["data"]
        elif isinstance(data, list):
            raw_locations = data

        for item in raw_locations:
            # Skip if no name
            if not item.get("name", "").strip():
                continue

            # Extract address components
            address_parts = []
            if item.get("address"):
                address_parts.append(item["address"])
            if item.get("address2"):
                address_parts.append(item["address2"])

            full_address = " ".join(address_parts).strip()

            # Parse service type from categories or tags
            service_type = "Pantry"  # Default
            categories = item.get("categories", "").lower()
            if "fresh express" in categories:
                service_type = "Fresh Express"
            elif "pantry/soup kitchen" in categories:
                service_type = "Pantry/Soup Kitchen"
            elif "soup kitchen" in categories:
                service_type = "Soup Kitchen"
            elif "multi-service" in categories:
                service_type = "Multi-Service Program"

            location = {
                "id": item.get("id", ""),
                "name": item.get("name", "").strip(),
                "address": full_address,
                "city": item.get("city", "").strip(),
                "state": item.get("state", "PA").strip(),
                "zip": item.get("zip", "").strip(),
                "phone": item.get("phone", "").strip(),
                "latitude": float(item["lat"]) if item.get("lat") else None,
                "longitude": float(item["lng"]) if item.get("lng") else None,
                "hours": item.get("hours", ""),
                "services": [service_type] if service_type else [],
                "website": item.get("url", ""),
                "notes": item.get("description", ""),
            }

            locations.append(location)

        logger.info(f"Processed {len(locations)} locations from API")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        from app.models.geographic import GridPoint

        # Use grid-based API search for Store Locator Plus
        # Get grid points for Pennsylvania
        grid_points = self.utils.get_state_grid_points("pa")

        # Limit grid points in test mode
        if self.test_mode:
            grid_points = grid_points[:3]

        locations = []
        for i, point in enumerate(grid_points):
            if i > 0:
                await asyncio.sleep(self.request_delay)

            logger.info(
                f"Searching grid point {i+1}/{len(grid_points)}: ({point.latitude}, {point.longitude})"
            )

            try:
                # Search around this grid point using Store Locator Plus API
                response = await self.fetch_api_data(
                    "locations-map/search",
                    params={
                        "callback": "initMySLP",
                        "action": "csl_ajax_onload",
                        "lat": point.latitude,
                        "lng": point.longitude,
                        "radius": 50,  # 50 mile radius
                        "options[distance_unit]": "miles",
                        "options[initial_radius]": "50",
                        "api_key": "myslp.bb1f143092daa0074f598393e30194a5ada5c0b6f6b900eb90900daf634669e1",
                        "_jsonp": "initMySLP",
                    },
                )
                locations.extend(self.process_api_response(response))
            except Exception as e:
                logger.error(
                    f"Error searching grid point ({point.latitude}, {point.longitude}): {e}"
                )
                continue

        # Deduplicate locations by ID
        unique_locations = []
        seen_ids = set()

        for location in locations:
            # Use the location ID from the API if available
            location_id = location.get("id")
            if not location_id:
                # Fall back to name + address
                location_id = (
                    f"{location.get('name', '')}_{location.get('address', '')}"
                )

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
                            state=location.get("state", "PA"),
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
                            location="PA", with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["failed"] += 1
                else:
                    # No address, use defaults
                    lat, lon = self.geocoder.get_default_coordinates(
                        location="PA", with_offset=True
                    )
                    location["latitude"] = lat
                    location["longitude"] = lon
                    geocoding_stats["default"] += 1

            # Add metadata
            location["source"] = "central_pennsylvania_food_bank_pa"
            location["food_bank"] = "Central Pennsylvania Food Bank"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Central Pennsylvania Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print(f"SCRAPER SUMMARY: Central Pennsylvania Food Bank")
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
