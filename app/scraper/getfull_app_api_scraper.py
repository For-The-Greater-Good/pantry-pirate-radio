"""Pure API-based scraper for GetFull.app food pantry data."""

import asyncio
import json
import logging
import math
from typing import Any

import httpx

from app.scraper.utils import ScraperJob

logger = logging.getLogger(__name__)


class Getfull_App_ApiScraper(ScraperJob):
    """API-based scraper for GetFull.app food pantry data.

    This scraper uses direct API calls without browser automation,
    making it much faster and more efficient.
    """

    # Configuration constants
    DEFAULT_SEARCH_RADIUS_MILES = 50.0
    DEFAULT_OVERLAP_FACTOR = 0.30
    DEFAULT_REQUEST_DELAY = 0.05  # 50ms between requests
    REQUEST_TIMEOUT = 30  # seconds
    EARTH_RADIUS_MILES = 69.0  # Approximate miles per degree latitude
    JOB_SUBMISSION_DELAY = 0.01  # 10ms between job submissions to prevent overwhelming

    def __init__(self, scraper_id: str = "getfull_app_api") -> None:
        """Initialize scraper with ID 'getfull_app_api' by default."""
        super().__init__(scraper_id=scraper_id)
        self.api_url = "https://api.getfull.app"
        self.unique_pantries: set[str] = set()
        self.total_pantries = 0

    async def get_auth_token(self) -> str | None:
        """Get authentication token from the API.

        Returns:
            Authentication token or None if failed
        """
        try:
            # First, create a session
            async with httpx.AsyncClient() as client:
                # Try to get a session
                session_response = await client.get(
                    f"{self.api_url}/auth-api/session",
                    headers={"Accept": "application/json"},
                )

                if session_response.status_code == 200:
                    logger.info(
                        f"Session response status: {session_response.status_code}"
                    )
                    logger.info(
                        f"Session response headers: {dict(session_response.headers)}"
                    )
                    logger.info(
                        f"Session response text: {session_response.text[:200]}"
                    )  # First 200 chars

                    if session_response.text.strip():
                        try:
                            session_data = session_response.json()
                            # Extract token from session if available
                            if "token" in session_data:
                                return session_data["token"]
                        except json.JSONDecodeError as e:
                            logger.warning(
                                f"Failed to parse session response as JSON: {e}"
                            )

                # Try anonymous auth
                logger.info("Trying anonymous auth endpoint")
                auth_response = await client.post(
                    f"{self.api_url}/auth-api/anonymous",
                    headers={"Accept": "application/json"},
                )

                logger.info(
                    f"Anonymous auth response status: {auth_response.status_code}"
                )
                logger.info(
                    f"Anonymous auth response headers: {dict(auth_response.headers)}"
                )
                logger.info(f"Anonymous auth response text: {auth_response.text[:200]}")

                if auth_response.status_code == 200 and auth_response.text.strip():
                    try:
                        auth_data = auth_response.json()
                        if "token" in auth_data:
                            return auth_data["token"]
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Failed to parse anonymous auth response as JSON: {e}"
                        )

        except Exception as e:
            logger.warning(f"Failed to get auth token: {e}")

        # Return None if authentication fails - let caller decide how to handle
        return None

    async def get_pantry_details(self, slug: str) -> dict[str, Any] | None:
        """Fetch detailed pantry information using the slug.
        
        Args:
            slug: Pantry slug identifier
            
        Returns:
            Detailed pantry data or None if failed
        """
        detail_url = f"{self.api_url}/pantry-api/pantries/{slug}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    detail_url,
                    headers={"Accept": "application/json"},
                    timeout=self.REQUEST_TIMEOUT,
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.debug(f"Failed to get details for {slug}: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.debug(f"Error fetching details for {slug}: {e}")
            return None

    async def search_pantries_by_bbox(
        self,
        top_left: list[float],
        bottom_right: list[float],
        auth_token: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for pantries within a bounding box.

        Args:
            top_left: [lat, lng] of top-left corner
            bottom_right: [lat, lng] of bottom-right corner
            auth_token: Authentication token (optional)

        Returns:
            List of pantry data
        """
        search_url = f"{self.api_url}/es/search/geo/pantries"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # Only add Authorization header if we have a token
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        payload = {
            "top_left": top_left,
            "bottom_right": bottom_right,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    search_url,
                    json=payload,
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT,
                )

                if response.status_code == 401:
                    logger.warning("Authentication failed, trying without auth")
                    headers.pop("Authorization", None)
                    response = await client.post(
                        search_url,
                        json=payload,
                        headers=headers,
                        timeout=self.REQUEST_TIMEOUT,
                    )

                response.raise_for_status()
                data = response.json()

                # Handle both list and dict responses
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "hits" in data:
                    return data["hits"].get("hits", [])
                else:
                    return []

        except Exception as e:
            logger.error(f"Error searching pantries: {e}")
            return []

    def create_search_grid(self) -> list[dict[str, Any]]:
        """Create a grid of search areas covering the continental US using ScraperUtils.

        Returns:
            List of search areas with bounding boxes
        """
        # Use the standard grid generator with optimized settings for API searches
        grid_points = self.utils.get_us_grid_points(
            search_radius_miles=self.DEFAULT_SEARCH_RADIUS_MILES,
            overlap_factor=self.DEFAULT_OVERLAP_FACTOR,
        )

        logger.info(f"Generated {len(grid_points)} grid points for API searches")

        # Convert grid points to search areas with bounding boxes
        search_areas = []
        for point in grid_points:
            # Create bounding box around each grid point
            # Using the search radius to create the box
            radius_miles = self.DEFAULT_SEARCH_RADIUS_MILES
            lat_offset = radius_miles / self.EARTH_RADIUS_MILES
            lng_offset = radius_miles / (
                math.cos(math.radians(point.latitude)) * self.EARTH_RADIUS_MILES
            )

            search_areas.append(
                {
                    "name": point.name,
                    "center": [point.latitude, point.longitude],
                    "top_left": [
                        point.latitude + lat_offset,
                        point.longitude - lng_offset,
                    ],
                    "bottom_right": [
                        point.latitude - lat_offset,
                        point.longitude + lng_offset,
                    ],
                }
            )

        return search_areas

    def transform_to_hsds(self, pantry: dict[str, Any]) -> dict[str, Any]:
        """Pass pantry data through with minimal transformation.
        
        The LLM will handle the actual HSDS alignment - we just ensure
        the data is complete and properly structured.

        Args:
            pantry: Pantry data from API

        Returns:
            Complete pantry data for LLM processing
        """
        # Simply return the complete pantry data
        # The LLM will handle mapping to HSDS format
        return pantry

    async def scrape(self) -> str:
        """Scrape data from GetFull.app using direct API calls.

        Returns:
            Summary of scraping results as JSON string
        """
        logger.info("Starting GetFull.app API scraper")

        # Try to get authentication token
        auth_token = await self.get_auth_token()
        if not auth_token:
            logger.warning("Failed to get authentication token from API")
            # Try environment variable as fallback
            import os

            auth_token = os.getenv("GETFULL_AUTH_TOKEN")
            if auth_token:
                logger.info("Using auth token from environment variable")
            else:
                logger.warning(
                    "No auth token available - will try API without authentication"
                )
        else:
            logger.info("Successfully obtained auth token from API")

        # Create search grid
        search_areas = self.create_search_grid()
        logger.info(f"Created {len(search_areas)} search areas covering the US")

        # Track all unique pantries
        all_pantries = {}

        # Process each search area
        for i, area in enumerate(search_areas):
            # Log progress every 10% or for first/last areas
            if (
                i == 0
                or i == len(search_areas) - 1
                or (i + 1) % max(1, len(search_areas) // 10) == 0
            ):
                logger.info(
                    f"Progress: {i+1}/{len(search_areas)} ({(i+1)/len(search_areas)*100:.1f}%) - "
                    f"Searching area centered at {area['center'][0]:.2f}, {area['center'][1]:.2f}"
                )

            # Search for pantries in this area
            pantries = await self.search_pantries_by_bbox(
                area["top_left"], area["bottom_right"], auth_token
            )

            # Process results
            new_pantries = 0
            for pantry in pantries:
                # Handle different response formats
                if "_source" in pantry:
                    # Elasticsearch format
                    pantry_id = str(pantry.get("_id", ""))
                    pantry_data = pantry["_source"]
                    pantry_data["id"] = pantry_id
                else:
                    # Direct format
                    pantry_id = str(pantry.get("id", ""))
                    pantry_data = pantry

                if pantry_id and pantry_id not in all_pantries:
                    all_pantries[pantry_id] = pantry_data
                    new_pantries += 1

            # Only log if we found pantries
            if len(pantries) > 0:
                logger.debug(
                    f"Found {len(pantries)} pantries at {area['center'][0]:.2f}, {area['center'][1]:.2f}, "
                    f"{new_pantries} were new (total unique: {len(all_pantries)})"
                )

            # Small delay between requests to avoid rate limiting
            await asyncio.sleep(self.DEFAULT_REQUEST_DELAY)

        # Fetch detailed information for each pantry
        logger.info(f"Fetching detailed information for {len(all_pantries)} pantries...")
        pantries_with_details = {}
        detail_fetch_count = 0
        
        for pantry_id, pantry_data in all_pantries.items():
            # Get slug from pantry data
            slug = pantry_data.get("slug")
            
            if slug:
                # Try to get detailed data
                detailed_data = await self.get_pantry_details(slug)
                
                if detailed_data:
                    # Use detailed data which has more complete information
                    pantries_with_details[pantry_id] = detailed_data
                    detail_fetch_count += 1
                else:
                    # Fall back to search data if details fetch fails
                    pantries_with_details[pantry_id] = pantry_data
            else:
                # No slug available, use search data
                pantries_with_details[pantry_id] = pantry_data
            
            # Progress logging
            if len(pantries_with_details) % 100 == 0:
                logger.info(f"Fetched details for {len(pantries_with_details)} pantries...")
            
            # Small delay to avoid rate limiting on detail API
            await asyncio.sleep(0.02)  # 20ms between detail requests
        
        logger.info(f"Successfully fetched detailed data for {detail_fetch_count}/{len(all_pantries)} pantries")
        
        # Submit all pantries to queue
        logger.info(f"Submitting {len(pantries_with_details)} unique pantries to queue")
        jobs_created = 0

        for pantry_id, pantry_data in pantries_with_details.items():
            # Transform to HSDS format
            hsds_data = self.transform_to_hsds(pantry_data)

            # Submit to queue
            try:
                job_id = self.submit_to_queue(json.dumps(hsds_data))
                
                # Debug: Check if we're getting existing job IDs
                if jobs_created == 0:
                    logger.info(f"First job_id returned: {job_id}")
                    import hashlib
                    content_hash = hashlib.sha256(json.dumps(hsds_data).encode()).hexdigest()
                    logger.info(f"First content hash: {content_hash[:16]}...")
                
                jobs_created += 1

                if jobs_created % 100 == 0:
                    logger.info(f"Submitted {jobs_created} jobs to queue...")
                
                # Add throttling to prevent overwhelming the queue
                if self.JOB_SUBMISSION_DELAY > 0:
                    await asyncio.sleep(self.JOB_SUBMISSION_DELAY)
                    
            except Exception as e:
                logger.error(f"Error submitting pantry {pantry_id}: {e}")

        # Create summary
        summary = {
            "total_search_areas": len(search_areas),
            "total_pantries_found": len(all_pantries),
            "unique_pantries": len(pantries_with_details),
            "pantries_with_details": detail_fetch_count,
            "jobs_created": jobs_created,
            "source": "GetFull.app API",
            "method": "direct_api_calls_with_details",
        }

        # Print summary
        print("\nGetFull.app API Scraper Complete!")
        print("=" * 50)
        print(f"Search Areas: {summary['total_search_areas']}")
        print(f"Total Pantries Found: {summary['total_pantries_found']}")
        print(f"Jobs Created: {summary['jobs_created']}")
        print("=" * 50)

        return json.dumps(summary)
