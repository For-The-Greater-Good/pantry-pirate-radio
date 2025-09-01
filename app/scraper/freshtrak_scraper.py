"""Scraper for FreshTrak/PantryTrak API."""

import asyncio
import json
import logging
from typing import Any

import httpx

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FreshtrakScraper(ScraperJob):
    """Scraper for FreshTrak/PantryTrak API.

    Note: The API's range/distance filter is broken and returns all agencies
    regardless of the distance parameter. We take advantage of this by making
    a single API call to retrieve all agencies at once.
    """

    def __init__(self, scraper_id: str = "freshtrak") -> None:
        """Initialize scraper with ID 'freshtrak' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'freshtrak'
        """
        super().__init__(scraper_id=scraper_id)
        self.base_url = "https://pantry-finder-api.freshtrak.com"
        self.unique_agencies: set[str] = set()
        self.total_agencies = 0

    async def scrape_with_zip_codes(self) -> list[dict[str, Any]]:
        """Scrape using zip code search - removed since grid search is more comprehensive."""
        # We'll focus on the grid search approach which is more comprehensive
        # than trying to maintain a list of all US zip codes
        return []

    async def fetch_agencies_by_zip(self, zip_code: str) -> dict[str, Any]:
        """Fetch agencies for a specific zip code.

        Args:
            zip_code: The zip code to search

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/api/agencies"
        params = {"zip_code": zip_code}

        logger.info(f"Fetching agencies for zip code: {zip_code}")

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(), timeout=httpx.Timeout(90.0, connect=30.0)
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Error fetching data for zip {zip_code}: {e}")
            return {}

    async def fetch_agencies_by_coordinates(
        self, lat: float, lng: float
    ) -> dict[str, Any]:
        """Fetch agencies for specific coordinates.

        Args:
            lat: Latitude
            lng: Longitude

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/api/agencies"
        params = {"lat": lat, "long": lng, "distance": self.search_radius}

        logger.debug(f"Fetching agencies for coordinates: {lat}, {lng}")

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(), timeout=httpx.Timeout(90.0, connect=30.0)
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(
                f"Error fetching data for coordinates {lat}, {lng}: {type(e).__name__}: {str(e)}"
            )
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text[:500]}")
            return {}
        except Exception as e:
            logger.error(
                f"Unexpected error fetching data for coordinates {lat}, {lng}: {type(e).__name__}: {str(e)}"
            )
            return {}

    def process_agency(self, agency: dict[str, Any]) -> dict[str, Any]:
        """Process a single agency record.

        Args:
            agency: Raw agency data from API

        Returns:
            Processed agency data
        """
        # Extract basic agency info
        processed = {
            "id": agency.get("id"),
            "name": agency.get("name", "").strip(),
            "nickname": agency.get("nickname", "").strip(),
            "address": agency.get("address", "").strip(),
            "city": agency.get("city", "").strip(),
            "state": agency.get("state", "").strip(),
            "zip": agency.get("zip", "").strip(),
            "phone": agency.get("phone", "").strip(),
            "latitude": (
                float(agency.get("latitude", 0)) if agency.get("latitude") else None
            ),
            "longitude": (
                float(agency.get("longitude", 0)) if agency.get("longitude") else None
            ),
            "estimated_distance": agency.get("estimated_distance"),
            "source": "freshtrak_api",
            "events": [],
        }

        # Process events
        for event in agency.get("events", []):
            event_data = {
                "id": event.get("id"),
                "name": event.get("name", "").strip(),
                "address": event.get("address", "").strip(),
                "city": event.get("city", "").strip(),
                "state": event.get("state", "").strip(),
                "zip": event.get("zip", "").strip(),
                "latitude": (
                    float(event.get("latitude", 0)) if event.get("latitude") else None
                ),
                "longitude": (
                    float(event.get("longitude", 0)) if event.get("longitude") else None
                ),
                "event_details": event.get("event_details", "").strip(),
                "estimated_distance": event.get("estimated_distance"),
                "exception_note": event.get("exception_note", "").strip(),
                "event_dates": event.get("event_dates", []),
                "service_category": event.get("service_category", {}),
            }
            processed["events"].append(event_data)

        return processed

    async def process_zip_codes(self, zip_codes: list[str]) -> list[dict[str, Any]]:
        """Process a list of zip codes to find agencies.

        Args:
            zip_codes: List of zip codes to search

        Returns:
            List of processed agency data
        """
        all_agencies = []

        for zip_code in zip_codes:
            try:
                data = await self.fetch_agencies_by_zip(zip_code)

                if data.get("agencies"):
                    agencies = data["agencies"]
                    logger.info(f"Found {len(agencies)} agencies for zip {zip_code}")

                    for agency in agencies:
                        agency_id = str(agency.get("id", ""))

                        # Only process unique agencies
                        if agency_id and agency_id not in self.unique_agencies:
                            processed_agency = self.process_agency(agency)
                            all_agencies.append(processed_agency)
                            self.unique_agencies.add(agency_id)
                            self.total_agencies += 1

                            logger.info(
                                "Found unique agency %s (total: %s)",
                                agency_id,
                                self.total_agencies,
                            )
                else:
                    logger.debug(f"No agencies found for zip code: {zip_code}")

            except Exception as e:
                logger.error(f"Error processing zip code {zip_code}: {e}")
                continue

            # Add delay between requests
            await asyncio.sleep(self.request_delay)

        return all_agencies

    async def process_grid_search(self) -> list[dict[str, Any]]:
        """Process grid search to find agencies by coordinates.

        Returns:
            List of processed agency data
        """
        all_agencies = []

        # Get grid points with optimized settings for FreshTrak
        # Using 150-mile radius with 25% overlap significantly reduces API calls
        us_grid_points = self.utils.get_us_grid_points(
            search_radius_miles=self.search_radius,  # 150 miles
            overlap_factor=0.25,  # 25% overlap
        )
        logger.info(
            "Starting optimized grid search with %s coordinate points (150mi radius, 25%% overlap)",
            len(us_grid_points),
        )

        # Configure concurrent processing
        max_concurrent = 25  # Increased for faster processing with fewer total requests
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_semaphore(coord):
            """Fetch agencies for a coordinate with rate limiting."""
            async with semaphore:
                try:
                    data = await self.fetch_agencies_by_coordinates(
                        coord.latitude, coord.longitude
                    )

                    if data.get("agencies"):
                        agencies = data["agencies"]
                        if len(agencies) > 0:
                            logger.debug(
                                f"Found {len(agencies)} agencies for coordinates {coord.latitude}, {coord.longitude}"
                            )
                        return agencies
                    return []
                except Exception as e:
                    logger.debug(
                        f"Error processing coordinates {coord.latitude}, {coord.longitude}: {e}"
                    )
                    return []

        # Process grid points in batches
        for i in range(0, len(us_grid_points), self.batch_size):
            batch = us_grid_points[i : i + self.batch_size]

            # Create tasks for concurrent processing
            tasks = [fetch_with_semaphore(coord) for coord in batch]

            # Execute batch concurrently
            batch_results = await asyncio.gather(*tasks)

            # Process results
            for agencies in batch_results:
                for agency in agencies:
                    agency_id = str(agency.get("id", ""))

                    # Only process unique agencies
                    if agency_id and agency_id not in self.unique_agencies:
                        processed_agency = self.process_agency(agency)
                        all_agencies.append(processed_agency)
                        self.unique_agencies.add(agency_id)
                        self.total_agencies += 1

                        logger.info(
                            "Found unique agency %s (total: %s)",
                            agency_id,
                            self.total_agencies,
                        )

            # Log progress every 10% or when new agencies are found
            progress = min(
                100, round((i + self.batch_size) / len(us_grid_points) * 100)
            )
            if progress % 10 == 0 or len(self.unique_agencies) > self.total_agencies:
                logger.info(
                    "Grid search progress: %s%% complete, unique agencies: %s",
                    progress,
                    len(self.unique_agencies),
                )

            # Small delay only for large batches to avoid overwhelming the API
            if i % 500 == 0 and i > 0:
                await asyncio.sleep(0.5)

        return all_agencies

    async def fetch_all_agencies(self) -> dict[str, Any]:
        """Fetch all agencies with a single API call.

        Since the range filter is broken and returns all data anyway,
        we can make a single request to get everything.

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/api/agencies"
        # Use center of US with large radius - the API ignores it and returns all anyway
        params = {
            "lat": 39.8283,  # Geographic center of US
            "long": -98.5795,
            "distance": 5000,  # Large radius - API returns all regardless
        }

        logger.info("Fetching all agencies with single API call")

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(),
                timeout=httpx.Timeout(120.0, connect=30.0),
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Error fetching all agencies: {type(e).__name__}: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text[:500]}")
            return {}
        except Exception as e:
            logger.error(
                f"Unexpected error fetching all agencies: {type(e).__name__}: {str(e)}"
            )
            return {}

    async def scrape(self) -> str:
        """Scrape data from FreshTrak API with a single request.

        Since their range filter is broken and returns all data,
        we make just one API call to get everything.

        Returns:
            Raw scraped content as JSON string
        """
        # Reset tracking variables
        self.unique_agencies = set()
        self.total_agencies = 0

        logger.info("Starting FreshTrak scrape with single API call")

        # Make single API call to get all agencies
        data = await self.fetch_all_agencies()

        if not data.get("agencies"):
            logger.error("No agencies found in API response")
            return json.dumps(
                {
                    "error": "No agencies found",
                    "total_unique_agencies": 0,
                    "total_jobs_created": 0,
                    "source": "freshtrak_api",
                    "base_url": self.base_url,
                }
            )

        agencies = data["agencies"]
        logger.info(f"Received {len(agencies)} agencies from API")

        # Process and submit all agencies
        job_count = 0
        for agency in agencies:
            try:
                agency_id = str(agency.get("id", ""))

                # Process each agency (they should all be unique from single call)
                if agency_id:
                    processed_agency = self.process_agency(agency)

                    # Submit to queue
                    job_id = self.submit_to_queue(json.dumps(processed_agency))
                    job_count += 1
                    self.unique_agencies.add(agency_id)
                    self.total_agencies += 1

                    logger.info(
                        f"Queued job {job_id} for agency: {processed_agency['name']}"
                    )

            except Exception as e:
                logger.error(
                    f"Error processing agency {agency.get('name', 'Unknown')}: {e}"
                )
                continue

        # Create summary
        summary = {
            "total_api_calls": 1,
            "total_agencies_received": len(agencies),
            "total_unique_agencies": len(self.unique_agencies),
            "total_jobs_created": job_count,
            "source": "freshtrak_api",
            "base_url": self.base_url,
            "search_method": "single_api_call",
        }

        # Print summary to CLI
        print("\nFreshTrak Scraper Summary:")
        print("Search method: Single API call (range filter broken, returns all)")
        print(f"Total agencies received: {len(agencies)}")
        print(f"Total unique agencies processed: {len(self.unique_agencies)}")
        print(f"Total jobs created: {job_count}")
        print(f"Source: {self.base_url}")
        print("Status: Complete\n")

        # Return summary for archiving
        return json.dumps(summary)
