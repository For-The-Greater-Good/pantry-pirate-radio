"""Scraper for FreshTrak/PantryTrak API."""

import asyncio
import json
import logging
from typing import Any

import httpx
from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FreshtrakScraper(ScraperJob):
    """Scraper for FreshTrak/PantryTrak API."""

    def __init__(self, scraper_id: str = "freshtrak") -> None:
        """Initialize scraper with ID 'freshtrak' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'freshtrak'
        """
        super().__init__(scraper_id=scraper_id)
        self.base_url = "https://pantry-finder-api.freshtrak.com"
        self.search_radius = 50  # miles
        self.batch_size = 25  # Number of grid points to process at once
        self.request_delay = 0.1  # 100ms between requests
        self.unique_agencies: set[str] = set()
        self.total_agencies = 0

        # Initialize geocoder with US default coordinates
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "US": (39.8283, -98.5795),  # Geographic center of the United States
            }
        )

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
            async with httpx.AsyncClient(headers=get_scraper_headers()) as client:
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
            async with httpx.AsyncClient(headers=get_scraper_headers()) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Error fetching data for coordinates {lat}, {lng}: {e}")
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

        # Get grid points for entire US
        us_grid_points = self.utils.get_us_grid_points()
        logger.info(
            "Starting grid search with %s coordinate points", len(us_grid_points)
        )

        # Process grid points in batches
        for i in range(0, len(us_grid_points), self.batch_size):
            batch = us_grid_points[i : i + self.batch_size]

            for coord in batch:
                try:
                    data = await self.fetch_agencies_by_coordinates(
                        coord.latitude, coord.longitude
                    )

                    if data.get("agencies"):
                        agencies = data["agencies"]
                        logger.debug(
                            f"Found {len(agencies)} agencies for coordinates {coord.latitude}, {coord.longitude}"
                        )

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

                except Exception as e:
                    logger.error(
                        f"Error processing coordinates {coord.latitude}, {coord.longitude}: {e}"
                    )
                    continue

                # Add delay between requests
                await asyncio.sleep(self.request_delay)

            # Log progress
            progress = min(
                100, round((i + self.batch_size) / len(us_grid_points) * 100)
            )
            logger.info(
                "Grid search progress: %s%% complete, unique agencies: %s",
                progress,
                len(self.unique_agencies),
            )

        return all_agencies

    async def scrape(self) -> str:
        """Scrape data from FreshTrak API using multiple approaches.

        Returns:
            Raw scraped content as JSON string
        """
        # Reset tracking variables
        self.unique_agencies = set()
        self.total_agencies = 0
        all_agencies = []

        logger.info("Starting comprehensive FreshTrak scrape")

        # Use grid search approach for comprehensive US coverage
        logger.info("Starting grid search across entire US")
        grid_agencies = await self.process_grid_search()
        all_agencies.extend(grid_agencies)

        logger.info(
            "Grid search complete: Total unique agencies: %s", len(self.unique_agencies)
        )

        # Submit all unique agencies to queue
        logger.info(f"Submitting {len(all_agencies)} agencies to queue")
        job_count = 0
        for agency in all_agencies:
            try:
                job_id = self.submit_to_queue(json.dumps(agency))
                job_count += 1
                logger.info(f"Queued job {job_id} for agency: {agency['name']}")
            except Exception as e:
                logger.error(
                    f"Error submitting agency {agency.get('name', 'Unknown')}: {e}"
                )
                continue

        # Create summary
        summary = {
            "total_grid_points_searched": len(self.utils.get_us_grid_points()),
            "total_unique_agencies": len(self.unique_agencies),
            "total_jobs_created": job_count,
            "source": "freshtrak_api",
            "base_url": self.base_url,
            "search_methods": ["grid_coordinate_search"],
        }

        # Print summary to CLI
        print("\nFreshTrak Scraper Summary:")
        print("Search method: Grid coordinate search across entire US")
        print(f"Grid points searched: {len(self.utils.get_us_grid_points())}")
        print(f"Total unique agencies found: {len(self.unique_agencies)}")
        print(f"Total jobs created: {job_count}")
        print(f"Source: {self.base_url}")
        print("Status: Complete\n")

        # Return summary for archiving
        return json.dumps(summary)
