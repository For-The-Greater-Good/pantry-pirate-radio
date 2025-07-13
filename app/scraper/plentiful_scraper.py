"""Scraper for Plentiful food pantry and resource data."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

import httpx

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class PlentifulScraper(ScraperJob):
    """Scraper for Plentiful food pantry and resource data."""

    def __init__(self, scraper_id: str = "plentiful", test_mode: bool = False) -> None:
        """Initialize scraper with ID 'plentiful' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'plentiful'
            test_mode: If True, only process a limited number of grid points for testing
        """
        super().__init__(scraper_id=scraper_id)
        self.base_url = "https://pantry.plentifulapp.com/api/3.0"
        self.batch_size = 10 if not test_mode else 3  # Smaller batches for production
        self.request_delay = (
            0.5 if not test_mode else 0.05
        )  # Longer delays for production
        self.detail_request_delay = (
            0.2 if not test_mode else 0.05
        )  # Additional delay for detail requests
        self.batch_delay = 2.0 if not test_mode else 0.2  # Delay between batches
        self.headers = get_scraper_headers()
        self.timeout = 30.0  # Timeout for HTTP requests
        self.test_mode = test_mode
        self.max_requests_per_minute = 60  # Conservative rate limit
        self.request_timestamps = []  # Track request timing

    async def throttle_request(self) -> None:
        """Implement rate limiting to respect API limits."""
        import time

        current_time = time.time()

        # Remove timestamps older than 1 minute
        self.request_timestamps = [
            timestamp
            for timestamp in self.request_timestamps
            if current_time - timestamp < 60
        ]

        # If we're at the rate limit, wait
        if len(self.request_timestamps) >= self.max_requests_per_minute:
            sleep_time = 60 - (current_time - self.request_timestamps[0])
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                # Clean up old timestamps after sleeping
                current_time = time.time()
                self.request_timestamps = [
                    timestamp
                    for timestamp in self.request_timestamps
                    if current_time - timestamp < 60
                ]

        # Record this request
        self.request_timestamps.append(current_time)

    async def fetch_locations_in_bounds(
        self,
        client: httpx.AsyncClient,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float,
    ) -> List[Dict[str, Any]]:
        """Fetch locations within specified bounding box.

        Args:
            client: HTTP client for making requests
            lat1: Northern latitude boundary
            lng1: Western longitude boundary
            lat2: Southern latitude boundary
            lng2: Eastern longitude boundary

        Returns:
            List of location dictionaries
        """
        url = f"{self.base_url}/map/locations"
        params = {
            "lat1": lat1,
            "lng1": lng1,
            "lat2": lat2,
            "lng2": lng2,
            "program_type": "non-food,foodpantry,soupkitchen",
            "status": "opennow,opentoday,openthisweek,other",
            "pantry_type": "plentifulpantry,verifiedpartnerpantry,unverifiedpartnerpantry",
            "service_type": "line,reservation,pre-registration,qr-code",
        }

        try:
            # Apply throttling before making request
            await self.throttle_request()

            response = await client.get(url, params=params, headers=self.headers)
            response.raise_for_status()

            locations = response.json()
            if not isinstance(locations, list):
                logger.warning(f"Unexpected response format: {type(locations)}")
                return []

            logger.info(
                f"Found {len(locations)} locations in bounds ({lat1}, {lng1}) to ({lat2}, {lng2})"
            )
            return locations

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching locations: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching locations: {e}")
            return []

    async def fetch_location_details(
        self, client: httpx.AsyncClient, location_id: int
    ) -> Optional[Dict[str, Any]]:
        """Fetch detailed information for a specific location.

        Args:
            client: HTTP client for making requests
            location_id: ID of the location to fetch

        Returns:
            Location details dictionary or None if fetch fails
        """
        url = f"{self.base_url}/map/location/{location_id}"

        try:
            # Apply throttling before making request
            await self.throttle_request()

            response = await client.get(url, headers=self.headers)
            response.raise_for_status()

            location_details = response.json()
            logger.debug(f"Fetched details for location {location_id}")
            return location_details

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching location {location_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching location {location_id}: {e}")
            return None

    def process_location_data(
        self, basic_data: Dict[str, Any], detailed_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process and combine location data from both API endpoints.

        Args:
            basic_data: Basic location data from locations endpoint
            detailed_data: Detailed location data from location endpoint

        Returns:
            Processed location data ready for HSDS alignment
        """
        # Start with basic data
        processed = {
            "id": basic_data.get("id"),
            "name": basic_data.get("name"),
            "address": basic_data.get("address"),
            "city": basic_data.get("city"),
            "state": basic_data.get("state"),
            "zip_code": basic_data.get("zip_code"),
            "latitude": basic_data.get("latitude"),
            "longitude": basic_data.get("longitude"),
            "phone": basic_data.get("phone"),
            "website": basic_data.get("website"),
            "organization_id": basic_data.get("organization_id"),
            "pantry_id": basic_data.get("pantry_id"),
            "service_type": basic_data.get("service_type"),
            "has_appointments": basic_data.get("has_appointments"),
            "week_days": basic_data.get("week_days", []),
            "source": "plentiful",
            "source_id": str(basic_data.get("id")),
        }

        # Add detailed data if available
        if detailed_data:
            processed.update(
                {
                    "amenities": detailed_data.get("amenities", []),
                    "conditions": detailed_data.get("conditions", []),
                    "service_hours": detailed_data.get("service_hours", []),
                    "description": detailed_data.get("description", ""),
                    "kosher": detailed_data.get("kosher", False),
                    "details_fetched": True,
                }
            )
        else:
            processed["details_fetched"] = False

        return processed

    async def scrape(self) -> str:
        """Scrape data from Plentiful API.

        Returns:
            Summary of scraping operation as JSON string
        """
        logger.info("Starting Plentiful scraper")

        # Get grid points for comprehensive US coverage
        grid_points = self.utils.get_us_grid_points()

        # In test mode, limit to a few grid points for quick verification
        # Test mode is detected by checking scraper_id or explicit test_mode flag
        is_test_mode = self.test_mode or "test" in self.scraper_id.lower()
        if is_test_mode:
            # Use grid points that are likely to have results (major metro areas)
            test_points = [
                point
                for point in grid_points
                if (
                    40.0 <= point.latitude <= 41.0 and -74.5 <= point.longitude <= -73.5
                )  # NYC area
                or (
                    34.0 <= point.latitude <= 35.0
                    and -118.5 <= point.longitude <= -117.5
                )  # LA area
                or (
                    41.8 <= point.latitude <= 42.0 and -87.8 <= point.longitude <= -87.5
                )  # Chicago area
            ][
                :3
            ]  # Limit to 3 points maximum for quick test
            grid_points = test_points
            logger.info(f"Test mode: Using {len(grid_points)} grid points for coverage")
        else:
            logger.info(f"Using {len(grid_points)} grid points for coverage")

        total_locations = 0
        total_jobs_created = 0
        failed_details = 0
        seen_ids: Set[int] = set()
        queries_with_max_results = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Process grid points in batches
            for i in range(0, len(grid_points), self.batch_size):
                batch = grid_points[i : i + self.batch_size]
                logger.info(
                    f"Processing batch {i//self.batch_size + 1}/{(len(grid_points) + self.batch_size - 1)//self.batch_size}"
                )

                # Fetch locations for each grid point
                for point in batch:
                    # Create smaller bounding box around grid point (approximately 25 miles radius)
                    # to ensure we stay under 1k result limit
                    lat_offset = 0.36  # ~25 miles in latitude
                    lng_offset = 0.36  # ~25 miles in longitude (approximate)

                    lat1 = point.latitude + lat_offset
                    lng1 = point.longitude - lng_offset
                    lat2 = point.latitude - lat_offset
                    lng2 = point.longitude + lng_offset

                    locations = await self.fetch_locations_in_bounds(
                        client, lat1, lng1, lat2, lng2
                    )

                    # Check if we hit the potential 1k limit
                    if len(locations) >= 1000:
                        queries_with_max_results += 1
                        logger.warning(
                            f"Query returned {len(locations)} results, may have hit 1k limit"
                        )

                    # Process each location with deduplication
                    new_locations = 0
                    for location in locations:
                        location_id = location.get("id")
                        if not location_id or location_id in seen_ids:
                            continue

                        seen_ids.add(location_id)
                        total_locations += 1
                        new_locations += 1

                        # Fetch detailed information
                        detailed_data = await self.fetch_location_details(
                            client, location_id
                        )
                        if detailed_data is None:
                            failed_details += 1

                        # Process and combine data
                        processed_location = self.process_location_data(
                            location, detailed_data
                        )

                        # Submit to queue for HSDS processing
                        try:
                            job_id = self.submit_to_queue(
                                json.dumps(processed_location)
                            )
                            total_jobs_created += 1
                            logger.info(
                                f"Queued job {job_id} for location: {processed_location['name']}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to submit job for location {location_id}: {e}"
                            )

                        # Rate limiting between detail requests
                        await asyncio.sleep(self.detail_request_delay)

                    logger.info(
                        f"Grid point ({point.latitude:.3f}, {point.longitude:.3f}): {len(locations)} total, {new_locations} new"
                    )

                    # Rate limiting between location fetches
                    await asyncio.sleep(self.request_delay)

                # Longer pause between batches
                await asyncio.sleep(self.batch_delay)

        # Create summary
        summary = {
            "total_locations_found": total_locations,
            "total_jobs_created": total_jobs_created,
            "failed_detail_fetches": failed_details,
            "grid_points_processed": len(grid_points),
            "queries_with_max_results": queries_with_max_results,
            "source": "plentiful",
            "base_url": self.base_url,
        }

        # Print summary to CLI
        print("\nPlentiful Scraper Summary:")
        print(f"Source: {self.base_url}")
        print(f"Grid points processed: {len(grid_points)}")
        print(f"Total locations found: {total_locations}")
        print(f"Successfully processed: {total_jobs_created}")
        print(f"Failed detail fetches: {failed_details}")
        if queries_with_max_results > 0:
            print(f"⚠️  Queries that may have hit 1k limit: {queries_with_max_results}")
        print("Status: Complete\n")

        return json.dumps(summary)
