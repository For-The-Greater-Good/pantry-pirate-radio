"""Scraper for Chester County Food Bank."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class ChesterCountyFoodBankPaScraper(ScraperJob):
    """Scraper for Chester County Food Bank."""

    def __init__(
        self, scraper_id: str = "chester_county_food_bank_pa", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'chester_county_food_bank_pa' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'chester_county_food_bank_pa'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        self.url = "https://chestercountyfoodbank.org/find-help/food-finder/"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "PA": (39.9983793, -75.7033508),  # Chester County center
                "Chester County": (39.9983793, -75.7033508),
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

        # First, find the map_data JavaScript variable that contains location posts
        map_data = {}
        script_tags = soup.find_all("script")

        for script in script_tags:
            if (
                hasattr(script, "string")
                and script.string
                and "var map_data" in script.string
            ):
                # Extract the JSON object from the JavaScript
                match = re.search(r"var map_data = ({.*?});", script.string, re.DOTALL)
                if match:
                    try:
                        map_data = json.loads(match.group(1))
                        logger.info(
                            f"Found map_data with {len(map_data.get('locations', []))} locations"
                        )
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse map_data JSON: {e}")
                        continue
                break

        # Create a mapping of city to coordinates and types
        city_coords = {}
        for loc in map_data.get("locations", []):
            city = loc.get("city", "")
            if city:
                # Store by lowercase city for case-insensitive matching
                city_coords[city.lower()] = {
                    "lat": loc.get("lat"),
                    "lng": loc.get("lng"),
                    "types": loc.get("types", []),
                }

        # Find the location listing area - Chester County uses div.t-row structure
        location_elements = []

        # Look for the results wrapper that contains the location rows
        results_wrapper = soup.find("div", class_="tbody results-wrap")
        if results_wrapper and hasattr(results_wrapper, "find_all"):
            # Each location is in a div with class t-row
            location_elements = results_wrapper.find_all("div", class_="t-row")
        else:
            # Fallback: look for t-row elements anywhere
            location_elements = soup.find_all("div", class_="t-row")

        logger.info(f"Found {len(location_elements)} location elements in HTML")

        # Process each location element
        for element in location_elements:
            try:
                # Get the individual cells within the row
                if hasattr(element, "find_all"):
                    cells = element.find_all("div", class_="td")
                else:
                    cells = []
                if cells and len(cells) >= 3:
                    # Extract text from each cell
                    city = cells[0].get_text(strip=True)
                    location_info = cells[1].get_text(strip=True)
                    phone = cells[2].get_text(strip=True)
                    hours = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                else:
                    # Fallback: parse as full text
                    full_text = element.get_text(separator="|", strip=True)
                    parts = full_text.split("|")
                    if len(parts) < 3:
                        continue
                    city = parts[0].strip()
                    location_info = parts[1].strip()
                    phone = parts[2].strip()
                    hours = parts[3].strip() if len(parts) > 3 else ""

                # Parse the location name and address from location_info
                # Format is typically: "Name — Address City, PA"
                if "—" in location_info:
                    name_parts = location_info.split("—", 1)
                    name = name_parts[0].strip()
                    address_full = name_parts[1].strip()

                    # Clean up address - remove redundant city/state
                    address = address_full
                    if city in address:
                        address = (
                            address.replace(f" {city}, PA", "")
                            .replace(f" {city},PA", "")
                            .replace(f" {city} PA", "")
                            .strip()
                        )
                    address = address.strip(" ,")
                else:
                    # No — separator, try to parse name from beginning
                    name = location_info.split(",")[0].strip()
                    address = ""

                # Extract services from the full text
                services = []
                full_text = f"{city} {location_info} {phone} {hours}".lower()
                service_keywords = [
                    "breakfast",
                    "lunch",
                    "dinner",
                    "pantry",
                    "food box",
                    "hot meal",
                    "grocery",
                    "delivery",
                    "senior",
                    "emergency",
                    "supper",
                    "meal",
                    "cupboard",
                ]
                for keyword in service_keywords:
                    if keyword in full_text:
                        services.append(keyword.title())

                # Create location entry
                location = {
                    "name": name.strip(),
                    "address": address.strip(),
                    "city": city.strip(),
                    "state": "PA",
                    "zip": "",  # Not typically provided
                    "phone": phone,
                    "hours": hours,
                    "services": list(set(services)),  # Remove duplicates
                    "website": "",
                    "notes": "",
                }

                # Match with coordinates from map_data
                city_key = city.lower()
                if city_key in city_coords:
                    location["latitude"] = city_coords[city_key]["lat"]
                    location["longitude"] = city_coords[city_key]["lng"]
                    location["location_types"] = city_coords[city_key]["types"]

                # Skip if no valid name or if name is empty
                if (
                    not location["name"]
                    or location["name"] == city
                    or len(location["name"]) < 3
                ):
                    logger.warning(f"Skipping location with invalid name: {location}")
                    continue

                locations.append(location)

            except Exception as e:
                logger.warning(f"Error parsing location element: {e}")
                logger.warning(f"Element text: {element.get_text(strip=True)[:200]}")
                continue

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

        # Extract locations from API response
        for item in data.get("locations", []):
            location = {
                "name": item.get("name", "").strip(),
                "address": item.get("address", "").strip(),
                "city": item.get("city", "").strip(),
                "state": item.get("state", "PA").strip(),
                "zip": item.get("zip", "").strip(),
                "phone": item.get("phone", "").strip(),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "hours": item.get("hours", ""),
                "services": item.get("services", []),
                "website": "",
                "notes": "",
            }
            locations.append(location)

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
        # grid_points = self.utils.get_state_grid_points("pa")
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
                if location.get("address") and location.get("city"):
                    try:
                        # Build a proper address string for geocoding
                        full_address = f"{location['address']}, {location['city']}, {location.get('state', 'PA')}"
                        if location.get("zip"):
                            full_address += f" {location['zip']}"

                        lat, lon = self.geocoder.geocode_address(
                            address=full_address, state=location.get("state", "PA")
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
            location["source"] = "chester_county_food_bank_pa"
            location["food_bank"] = "Chester County Food Bank"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Chester County Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Chester County Food Bank")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        print(
            f"Geocoding - Success: {geocoding_stats['success']}, Failed: {geocoding_stats['failed']}, Default: {geocoding_stats['default']}"
        )
        if self.test_mode:
            print("TEST MODE: Limited processing")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
