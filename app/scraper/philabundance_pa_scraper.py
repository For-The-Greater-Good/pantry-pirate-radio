"""Scraper for Philabundance."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class PhilabundancePaScraper(ScraperJob):
    """Scraper for Philabundance."""

    def __init__(
        self, scraper_id: str = "philabundance_pa", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'philabundance_pa' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'philabundance_pa'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        self.url = "https://www.philabundance.org/find-food/"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = (
            1.0 if not test_mode else 0.1
        )  # Be respectful with API calls
        self.timeout = 30.0

        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "PA": (40.590752, -77.209755),  # Pennsylvania center
                # Philadelphia region (where most locations are)
                "Philadelphia": (39.9526, -75.1652),
            }
        )

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

    async def fetch_wpsl_locations(
        self, lat: float, lng: float, radius: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetch locations from WP Store Locator API.

        Args:
            lat: Latitude for search center
            lng: Longitude for search center
            radius: Search radius in miles

        Returns:
            API response data
        """
        # WP Store Locator uses WordPress admin-ajax.php
        url = "https://www.philabundance.org/wp-admin/admin-ajax.php"

        # WP Store Locator expects query parameters for GET request
        params = {
            "action": "store_search",  # WP Store Locator uses 'store_search' action
            "lat": str(lat),
            "lng": str(lng),
            "max_results": "100",  # Get maximum results
            "search_radius": str(radius),
            "autoload": "1",
        }

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(),
                timeout=httpx.Timeout(self.timeout, connect=self.timeout / 3),
            ) as client:
                # WP Store Locator uses GET with query params (based on food_bank_of_western_massachusetts)
                response = await client.get(url, params=params)
                response.raise_for_status()

                # WP Store Locator returns data in a specific format
                # First check if response is JSON
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    result = response.json()

                    # Check if it's wrapped in a success/data structure
                    if isinstance(result, dict) and "success" in result:
                        if result.get("success") and "data" in result:
                            return result["data"]
                        else:
                            logger.error(f"API returned error: {result}")
                            return []

                    # Otherwise assume it's the data directly
                    return result
                else:
                    # Try to parse as text first to debug
                    text_response = response.text
                    logger.debug(f"Non-JSON response: {text_response[:200]}...")

                    # WP Store Locator might return "0" or HTML on error
                    if text_response.strip() == "0" or text_response.strip() == "-1":
                        logger.warning("WP Store Locator returned error code")
                        return []

                    # Try to parse as JSON anyway
                    try:
                        result = response.json()
                        return result if isinstance(result, list) else []
                    except Exception:
                        logger.error("Could not parse response as JSON")
                        return []
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching locations: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching locations: {e}")
            raise

    def process_api_response(self, data: Any) -> List[Dict[str, Any]]:
        """Process API response data.

        Args:
            data: API response data

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        # WP Store Locator returns data as an array directly
        if not isinstance(data, list):
            logger.warning(f"Unexpected response format: {type(data)}")
            return locations

        for item in data:
            # Extract basic information
            location = {
                "id": item.get("id"),
                "name": item.get("store", "").strip(),
                "address": item.get("address", "").strip(),
                "city": item.get("city", "").strip(),
                "state": item.get("state", "PA").strip(),
                "zip": item.get("zip", "").strip(),
                "phone": item.get("phone", "").strip(),
                "latitude": float(item.get("lat")) if item.get("lat") else None,
                "longitude": float(item.get("lng")) if item.get("lng") else None,
                "website": item.get("url", "").strip(),
            }

            # Extract hours (WP Store Locator stores this as separate fields)
            hours_parts = []
            if item.get("hours"):
                hours_parts.append(item.get("hours"))

            # Extract category/service type
            services = []
            if item.get("terms"):
                services.append(item.get("terms"))
            elif item.get("category"):
                services.append(item.get("category"))

            # Extract additional description/notes
            notes_parts = []
            if item.get("description"):
                notes_parts.append(item.get("description"))

            # Combine into fields
            location["hours"] = " ".join(hours_parts).strip()
            location["services"] = services
            location["notes"] = " ".join(notes_parts).strip()

            # Skip if no name
            if not location["name"]:
                continue

            locations.append(location)

        logger.info(f"Processed {len(locations)} locations from API")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # This site uses WP Store Locator plugin
        # We'll search across Pennsylvania using grid points
        from app.models.geographic import GridPoint

        # Get grid points for the state
        grid_points = self.utils.get_state_grid_points("pa")

        # Limit grid points in test mode
        if self.test_mode:
            grid_points = grid_points[:3]

        locations = []
        for i, point in enumerate(grid_points):
            if i > 0:
                await asyncio.sleep(self.request_delay)

            # Search around this grid point using WP Store Locator API
            logger.info(
                f"Searching grid point {i+1}/{len(grid_points)}: ({point.latitude}, {point.longitude})"
            )
            try:
                response = await self.fetch_wpsl_locations(
                    point.latitude, point.longitude
                )
                point_locations = self.process_api_response(response)
                locations.extend(point_locations)
                logger.info(
                    f"Found {len(point_locations)} locations at grid point {i+1}"
                )
            except Exception as e:
                logger.error(f"Error fetching locations for grid point {i+1}: {e}")
                continue

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
            location["source"] = "philabundance_pa"
            location["food_bank"] = "Philabundance"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Philabundance",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Philabundance")
        print("=" * 60)
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
        print("=" * 60 + "\n")

        # Return summary for archiving
        return json.dumps(summary)
