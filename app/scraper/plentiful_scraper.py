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

    def get_variable_density_grids(self) -> List[Dict[str, Any]]:
        """Generate grid points with variable density based on Plentiful concentration.

        Returns:
            List of dictionaries with grid point info and search radius
        """
        from app.scraper.utils import ScraperUtils
        from app.models.geographic import BoundingBox, GridPoint

        grids = []

        # Define regions with different densities
        # Format: (bounds, radius_miles, description)
        regions = [
            # NYC Metro - Ultra fine (5-10 mile radius)
            # Manhattan
            (
                {"north": 40.9, "south": 40.7, "east": -73.9, "west": -74.05},
                5,
                "Manhattan",
            ),
            # Brooklyn
            (
                {"north": 40.74, "south": 40.57, "east": -73.83, "west": -74.05},
                7,
                "Brooklyn",
            ),
            # Queens
            (
                {"north": 40.8, "south": 40.55, "east": -73.7, "west": -73.96},
                7,
                "Queens",
            ),
            # Bronx
            (
                {"north": 40.92, "south": 40.78, "east": -73.75, "west": -73.93},
                7,
                "Bronx",
            ),
            # Staten Island
            (
                {"north": 40.65, "south": 40.49, "east": -74.03, "west": -74.26},
                10,
                "Staten Island",
            ),
            # Newark/Jersey City
            (
                {"north": 40.8, "south": 40.66, "east": -74.02, "west": -74.28},
                10,
                "Newark/Jersey City",
            ),
            # Northeast Corridor - Fine (15-20 mile radius)
            # Boston Metro
            (
                {"north": 42.6, "south": 42.0, "east": -70.6, "west": -71.3},
                15,
                "Boston Metro",
            ),
            # Philadelphia Metro
            (
                {"north": 40.14, "south": 39.86, "east": -74.96, "west": -75.28},
                15,
                "Philadelphia Metro",
            ),
            # DC Metro
            (
                {"north": 39.2, "south": 38.6, "east": -76.7, "west": -77.5},
                15,
                "DC Metro",
            ),
            # Connecticut
            (
                {"north": 42.05, "south": 40.95, "east": -71.78, "west": -73.73},
                20,
                "Connecticut",
            ),
            # Rhode Island
            (
                {"north": 42.02, "south": 41.15, "east": -71.12, "west": -71.91},
                20,
                "Rhode Island",
            ),
            # Rest of NJ not covered above
            (
                {"north": 41.36, "south": 40.8, "east": -73.89, "west": -74.7},
                20,
                "Northern NJ",
            ),
            (
                {"north": 40.66, "south": 38.93, "east": -74.0, "west": -75.57},
                20,
                "Southern NJ",
            ),
            # Secondary Markets - Medium (50-100 mile radius)
            # Chicago
            (
                {"north": 42.5, "south": 41.2, "east": -87.0, "west": -88.5},
                75,
                "Chicago Metro",
            ),
            # Los Angeles
            (
                {"north": 34.8, "south": 33.2, "east": -117.0, "west": -119.0},
                75,
                "Los Angeles Metro",
            ),
            # San Francisco Bay Area
            (
                {"north": 38.3, "south": 36.9, "east": -121.2, "west": -123.0},
                75,
                "SF Bay Area",
            ),
            # Seattle
            (
                {"north": 48.3, "south": 46.9, "east": -121.0, "west": -123.0},
                75,
                "Seattle Metro",
            ),
            # Atlanta
            (
                {"north": 34.4, "south": 33.2, "east": -83.5, "west": -85.0},
                75,
                "Atlanta Metro",
            ),
            # Miami
            (
                {"north": 26.7, "south": 25.1, "east": -79.9, "west": -80.9},
                75,
                "Miami Metro",
            ),
            # Denver/Colorado
            (
                {"north": 41.0, "south": 37.0, "east": -102.0, "west": -109.0},
                100,
                "Colorado",
            ),
            # Rest of CA
            (
                {"north": 42.0, "south": 32.5, "east": -114.0, "west": -124.5},
                100,
                "California Rest",
            ),
            # Texas major cities
            (
                {"north": 33.0, "south": 29.2, "east": -94.0, "west": -100.5},
                100,
                "Texas Cities",
            ),
            # Florida rest
            (
                {"north": 31.0, "south": 24.5, "east": -79.9, "west": -87.6},
                100,
                "Florida Rest",
            ),
            # Large Coverage Areas - Coarse (200-500 mile radius)
            # Midwest
            (
                {"north": 49.0, "south": 36.0, "east": -80.5, "west": -104.0},
                300,
                "Midwest",
            ),
            # Mountain West
            (
                {"north": 49.0, "south": 31.0, "east": -104.0, "west": -125.0},
                400,
                "Mountain West",
            ),
            # South (excluding FL and TX)
            (
                {"north": 39.0, "south": 25.0, "east": -75.0, "west": -104.0},
                300,
                "South",
            ),
        ]

        # Track processed areas to avoid overlap
        processed_coords = set()

        for bounds_dict, radius_miles, region_name in regions:
            # Skip if in test mode and not a priority region
            if self.test_mode and region_name not in [
                "Manhattan",
                "Brooklyn",
                "Queens",
            ]:
                continue

            bounds = BoundingBox(
                north=bounds_dict["north"],
                south=bounds_dict["south"],
                east=bounds_dict["east"],
                west=bounds_dict["west"],
            )

            # Generate grid points for this region
            grid_points = ScraperUtils.get_grid_points(
                bounds=bounds,
                search_radius_miles=radius_miles,
                overlap_factor=0.1,  # Small overlap to ensure coverage
            )

            # Add to grids list with deduplication
            for point in grid_points:
                coord_key = (round(point.latitude, 2), round(point.longitude, 2))
                if coord_key not in processed_coords:
                    processed_coords.add(coord_key)
                    grids.append(
                        {
                            "point": point,
                            "radius_miles": radius_miles,
                            "region": region_name,
                        }
                    )

        logger.info(f"Generated {len(grids)} total grid points with variable density")
        return grids

    async def search_grid_with_subdivision(
        self,
        client: httpx.AsyncClient,
        lat: float,
        lon: float,
        radius_miles: float,
        seen_ids: Set[int],
        max_depth: int = 3,
        current_depth: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search a grid cell and subdivide if it hits the API limit.

        Args:
            client: HTTP client
            lat: Center latitude
            lon: Center longitude
            radius_miles: Search radius in miles
            seen_ids: Set of already seen location IDs
            max_depth: Maximum subdivision depth
            current_depth: Current recursion depth

        Returns:
            List of unique locations found
        """
        # Convert radius to degrees (rough approximation)
        radius_deg = radius_miles / 69.0

        # Define bounding box
        lat1 = lat + radius_deg  # North
        lat2 = lat - radius_deg  # South
        lng1 = lon - radius_deg  # West
        lng2 = lon + radius_deg  # East

        # Fetch locations
        locations = await self.fetch_locations_in_bounds(client, lat1, lng1, lat2, lng2)

        # If we hit the limit and can subdivide further
        if len(locations) >= 1000 and current_depth < max_depth:
            logger.warning(
                f"Hit 1000 limit at ({lat:.2f}, {lon:.2f}) radius {radius_miles}mi, subdividing..."
            )

            # Subdivide into 4 quadrants
            half_radius = radius_miles / 2
            offset = half_radius / 69.0  # Convert to degrees

            all_locations = []
            quadrants = [
                (lat + offset, lon - offset, "NW"),  # Northwest
                (lat + offset, lon + offset, "NE"),  # Northeast
                (lat - offset, lon - offset, "SW"),  # Southwest
                (lat - offset, lon + offset, "SE"),  # Southeast
            ]

            for qlat, qlon, quad_name in quadrants:
                logger.debug(f"  Searching {quad_name} quadrant...")
                quad_locations = await self.search_grid_with_subdivision(
                    client,
                    qlat,
                    qlon,
                    half_radius,
                    seen_ids,
                    max_depth,
                    current_depth + 1,
                )
                all_locations.extend(quad_locations)

            return all_locations

        # Filter out duplicates
        unique_locations = []
        for location in locations:
            loc_id = location.get("id")
            if loc_id and loc_id not in seen_ids:
                seen_ids.add(loc_id)
                unique_locations.append(location)

        return unique_locations

    async def scrape(self) -> str:
        """Scrape data from Plentiful API using variable density grid.

        Returns:
            Summary of scraping operation as JSON string
        """
        logger.info("Starting Plentiful scraper with variable density grid")

        # Generate variable density grids
        grids = self.get_variable_density_grids()
        logger.info(f"Using {len(grids)} grid points with variable density")

        total_locations = 0
        total_jobs_created = 0
        failed_details = 0
        seen_ids: Set[int] = set()
        queries_with_max_results = 0
        grids_processed = 0
        regions_summary = {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Process grids by region
            current_region = None
            region_locations = 0

            for grid_info in grids:
                grid_point = grid_info["point"]
                radius_miles = grid_info["radius_miles"]
                region = grid_info["region"]

                # Track region changes
                if region != current_region:
                    if current_region:
                        regions_summary[current_region] = region_locations
                        logger.info(
                            f"  {current_region}: {region_locations} locations found"
                        )
                    current_region = region
                    region_locations = 0
                    logger.info(
                        f"Processing region: {region} (radius: {radius_miles} miles)"
                    )

                try:
                    # Search with automatic subdivision if needed
                    locations = await self.search_grid_with_subdivision(
                        client,
                        grid_point.latitude,
                        grid_point.longitude,
                        radius_miles,
                        seen_ids,
                    )

                    if len(locations) >= 1000:
                        queries_with_max_results += 1

                    # Process each unique location
                    for location in locations:
                        total_locations += 1
                        region_locations += 1

                        location_id = location.get("id")

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
                            if total_jobs_created % 100 == 0:
                                logger.info(
                                    f"  Progress: {total_jobs_created} jobs created"
                                )
                        except Exception as e:
                            logger.error(
                                f"Failed to submit job for location {location_id}: {e}"
                            )

                        # Rate limiting between detail requests
                        await asyncio.sleep(self.detail_request_delay)

                    grids_processed += 1
                    if grids_processed % 10 == 0:
                        logger.info(
                            f"Processed {grids_processed}/{len(grids)} grid points"
                        )

                except Exception as e:
                    logger.error(
                        f"Failed to process grid at ({grid_point.latitude:.2f}, {grid_point.longitude:.2f}): {e}"
                    )
                    continue

                # Rate limiting between grids
                await asyncio.sleep(self.request_delay)

            # Add last region to summary
            if current_region:
                regions_summary[current_region] = region_locations
                logger.info(f"  {current_region}: {region_locations} locations found")

        # Create summary
        summary = {
            "total_locations_found": total_locations,
            "total_jobs_created": total_jobs_created,
            "failed_detail_fetches": failed_details,
            "grids_processed": grids_processed,
            "total_grids": len(grids),
            "queries_with_max_results": queries_with_max_results,
            "regions_summary": regions_summary,
            "source": "plentiful",
            "base_url": self.base_url,
        }

        # Print summary to CLI
        print("\nPlentiful Scraper Summary:")
        print(f"Source: {self.base_url}")
        print(f"Grids processed: {grids_processed}/{len(grids)}")
        print(f"Total locations found: {total_locations}")
        print(f"Successfully processed: {total_jobs_created}")
        print(f"Failed detail fetches: {failed_details}")
        if queries_with_max_results > 0:
            print(f"⚠️  Queries that hit 1k limit: {queries_with_max_results}")
        print("\nLocations by region:")
        for region, count in sorted(
            regions_summary.items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {region}: {count}")
        print("Status: Complete\n")

        return json.dumps(summary)
