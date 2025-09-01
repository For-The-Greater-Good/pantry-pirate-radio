"""Scraper for Capital Area Food Bank."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class CapitalAreaFoodBankDcScraper(ScraperJob):
    """Scraper for Capital Area Food Bank."""

    def __init__(
        self, scraper_id: str = "capital_area_food_bank_dc", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'capital_area_food_bank_dc' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'capital_area_food_bank_dc'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # ArcGIS Feature Service URL for Active Agencies
        self.url = "https://www.capitalareafoodbank.org/find-food-assistance/"
        self.feature_service_url = "https://services.arcgis.com/oCjyzxNy34f0pJCV/arcgis/rest/services/Active_Agencies_Last_45_Days/FeatureServer/0"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

    async def query_arcgis_features(
        self, offset: int = 0, limit: int = 1000
    ) -> Dict[str, Any]:
        """Query ArcGIS Feature Service for locations.

        Args:
            offset: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            API response as dictionary

        Raises:
            httpx.HTTPError: If API request fails
        """
        params = {
            "where": "1=1",  # Get all records
            "outFields": "*",  # Get all fields
            "f": "json",  # Return as JSON
            "returnGeometry": "true",
            "resultOffset": offset,
            "resultRecordCount": limit,
            "orderByFields": "name",
        }

        query_url = f"{self.feature_service_url}/query"

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(),
                timeout=httpx.Timeout(self.timeout, connect=self.timeout / 3),
            ) as client:
                response = await client.get(query_url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching data from {query_url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching data from {query_url}: {e}")
            raise

    def process_arcgis_features(
        self, features: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process ArcGIS features into standardized location format.

        Args:
            features: List of ArcGIS feature objects

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        for feature in features:
            attrs = feature.get("attributes", {})
            geometry = feature.get("geometry", {})

            # Extract basic information
            location = {
                "id": attrs.get("OBJECTID"),
                "name": (attrs.get("name") or "").strip(),
                "address": (attrs.get("address1") or "").strip(),
                "address2": (attrs.get("address2") or "").strip(),
                "city": (attrs.get("city") or "").strip(),
                "state": (attrs.get("state") or "DC").strip(),
                "zip": (attrs.get("zip") or "").strip(),
                "county": (attrs.get("county_name") or "").strip(),
                "phone": (attrs.get("phone") or "").strip(),
                "latitude": geometry.get("y"),
                "longitude": geometry.get("x"),
                "website": (attrs.get("website") or "").strip(),
                "email": (attrs.get("email") or "").strip(),
                "tefap": attrs.get("tefap") or "",  # TEFAP status
            }

            # Extract hours information
            hours_parts = []
            days = [
                "Sunday",
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
            ]

            for day in days:
                day_hours = []
                # Check up to 3 time slots per day
                for slot in range(1, 4):
                    start_field = f"start{slot}_{day}"
                    end_field = f"end{slot}_{day}"

                    if attrs.get(start_field) and attrs.get(end_field):
                        day_hours.append(f"{attrs[start_field]}-{attrs[end_field]}")

                if day_hours:
                    hours_parts.append(f"{day}: {', '.join(day_hours)}")

            location["hours"] = (
                "; ".join(hours_parts) if hours_parts else "Call for hours"
            )

            # Extract services
            services = []
            if attrs.get("tefap") == "TEFAP Only":
                services.append("TEFAP Only")
            elif attrs.get("tefap") == "TEFAP Available":
                services.append("TEFAP Available")

            location["services"] = services
            location["notes"] = attrs.get("notes") or ""

            locations.append(location)

        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        locations = []
        offset = 0
        limit = 1000
        has_more = True

        # Query ArcGIS Feature Service with pagination
        while has_more:
            logger.info(
                f"Querying ArcGIS Feature Service with offset={offset}, limit={limit}"
            )

            try:
                response = await self.query_arcgis_features(offset=offset, limit=limit)

                # Check if the query was successful
                if "error" in response:
                    logger.error(f"ArcGIS query error: {response['error']}")
                    break

                # Extract features
                features = response.get("features", [])
                if not features:
                    has_more = False
                    break

                # Process features into locations
                batch_locations = self.process_arcgis_features(features)
                locations.extend(batch_locations)

                logger.info(
                    f"Retrieved {len(features)} features, total so far: {len(locations)}"
                )

                # Check if we need to continue
                if len(features) < limit:
                    has_more = False
                else:
                    offset += limit

                # Respect rate limits
                if has_more:
                    await asyncio.sleep(self.request_delay)

                # In test mode, limit the number of batches
                if self.test_mode and len(locations) >= 10:
                    logger.info("Test mode: Limiting to 10 locations")
                    locations = locations[:10]
                    break

            except Exception as e:
                logger.error(f"Error querying ArcGIS Feature Service: {e}")
                break

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

        for location in unique_locations:
            # Build full address
            if location.get("address2"):
                full_address = f"{location['address']} {location['address2']}"
            else:
                full_address = location["address"]

            # Add metadata
            location["source"] = "capital_area_food_bank_dc"
            location["food_bank"] = "Capital Area Food Bank"
            location["full_address"] = full_address

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Capital Area Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Capital Area Food Bank")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"ArcGIS Feature Service: {self.feature_service_url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        if self.test_mode:
            print("TEST MODE: Limited processing")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
