"""Scraper for Food Bank of Western Massachusetts."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FoodBankOfWesternMassachusettsMaScraper(ScraperJob):
    """Scraper for Food Bank of Western Massachusetts."""

    def __init__(
        self,
        scraper_id: str = "food_bank_of_western_massachusetts_ma",
        test_mode: bool = False,
    ):
        """Initialize scraper with ID 'food_bank_of_western_massachusetts_ma' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'food_bank_of_western_massachusetts_ma'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # Main URL and AJAX endpoint
        self.url = (
            "https://www.foodbankwma.org/get-help/food-pantry-meal-program-schedule/"
        )
        self.base_url = self.url  # For summary compatibility
        self.ajax_url = "https://www.foodbankwma.org/wp-admin/admin-ajax.php"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

    async def fetch_wp_store_locator_data(self) -> List[Dict[str, Any]]:
        """Fetch location data from WP Store Locator AJAX endpoint.

        Returns:
            List of location dictionaries
        """
        params = {
            "action": "store_search",
            "lat": "42.17537",  # Center of Western MA
            "lng": "-72.57372",
            "max_results": "500",  # Get all locations
            "search_radius": "100",  # 100 mile radius to cover entire service area
            "autoload": "1",
        }

        try:
            async with httpx.AsyncClient(
                headers=get_scraper_headers(),
                timeout=httpx.Timeout(self.timeout, connect=self.timeout / 3),
            ) as client:
                response = await client.get(self.ajax_url, params=params)
                response.raise_for_status()
                data = response.json()

                locations = []
                # WP Store Locator returns array of locations
                for item in data:
                    # Parse the description HTML to extract additional info
                    description_soup = BeautifulSoup(
                        item.get("description", ""), "html.parser"
                    )
                    description_text = description_soup.get_text(
                        separator=" ", strip=True
                    )

                    location = {
                        "id": item.get("id"),
                        "name": item.get("store", "").strip(),
                        "address": item.get("address", "").strip(),
                        "address2": item.get("address2", "").strip(),
                        "city": item.get("city", "").strip(),
                        "state": item.get("state", "MA").strip(),
                        "zip": item.get("zip", "").strip(),
                        "phone": item.get("phone", "").strip(),
                        "latitude": float(item.get("lat")) if item.get("lat") else None,
                        "longitude": (
                            float(item.get("lng")) if item.get("lng") else None
                        ),
                        "hours": item.get("hours", ""),
                        "url": item.get("url", ""),
                        "description": description_text,
                        # Extract service type from category or description
                        "services": self._extract_services(item, description_text),
                    }

                    # Build full address
                    address_parts = [location["address"]]
                    if location["address2"]:
                        address_parts.append(location["address2"])
                    location["full_address"] = " ".join(address_parts)

                    locations.append(location)

                logger.info(f"Fetched {len(locations)} locations from WP Store Locator")
                return locations

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching data from {self.ajax_url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching data from {self.ajax_url}: {e}")
            raise

    def _extract_services(self, item: Dict[str, Any], description: str) -> List[str]:
        """Extract service types from location data.

        Args:
            item: Raw location data
            description: Parsed description text

        Returns:
            List of services
        """
        services = []

        # Check category field
        category = item.get("category", "").lower()

        # Common service patterns
        if any(word in category for word in ["pantry", "food pantry"]):
            services.append("Food Pantry")
        if any(word in category for word in ["meal", "kitchen", "dine"]):
            services.append("Meal Site")
        if "mobile" in category:
            services.append("Mobile Food Bank")
        if "brown bag" in category or "elder" in category:
            services.append("Brown Bag: Food for Elders")

        # Also check description for service types
        desc_lower = description.lower()
        if "pantry" in desc_lower and "Food Pantry" not in services:
            services.append("Food Pantry")
        if (
            any(word in desc_lower for word in ["meal", "breakfast", "lunch", "dinner"])
            and "Meal Site" not in services
        ):
            services.append("Meal Site")
        if "mobile" in desc_lower and "Mobile Food Bank" not in services:
            services.append("Mobile Food Bank")

        # Default to Food Pantry if no services identified
        if not services:
            services.append("Food Pantry")

        return services

    def _determine_county(self, location: Dict[str, Any]) -> Optional[str]:
        """Determine county from city name for better default coordinates.

        Args:
            location: Location dictionary

        Returns:
            County name or None
        """
        city = location.get("city", "").lower()

        # Map major cities to counties
        city_to_county = {
            # Berkshire County
            "pittsfield": "Berkshire",
            "north adams": "Berkshire",
            "adams": "Berkshire",
            "williamstown": "Berkshire",
            "lenox": "Berkshire",
            "great barrington": "Berkshire",
            # Franklin County
            "greenfield": "Franklin",
            "turners falls": "Franklin",
            "montague": "Franklin",
            "deerfield": "Franklin",
            "orange": "Franklin",
            # Hampden County
            "springfield": "Hampden",
            "holyoke": "Hampden",
            "chicopee": "Hampden",
            "westfield": "Hampden",
            "agawam": "Hampden",
            "west springfield": "Hampden",
            # Hampshire County
            "northampton": "Hampshire",
            "amherst": "Hampshire",
            "easthampton": "Hampshire",
            "south hadley": "Hampshire",
            "belchertown": "Hampshire",
        }

        for city_name, county in city_to_county.items():
            if city_name in city:
                return county

        return None

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # Use WP Store Locator AJAX endpoint to fetch all locations
        locations = await self.fetch_wp_store_locator_data()

        # Limit locations in test mode
        if self.test_mode and len(locations) > 5:
            locations = locations[:5]
            logger.info(f"Test mode: Limited to {len(locations)} locations")

        # Deduplicate locations if needed
        unique_locations = []
        seen_ids = set()

        for location in locations:
            # Create unique ID based on name and address
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
            # Note: Latitude and longitude will be handled by the validator service

            # Add metadata
            location["source"] = "food_bank_of_western_massachusetts_ma"
            location["food_bank"] = "Food Bank of Western Massachusetts"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Food Bank of Western Massachusetts",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "source": self.base_url,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Food Bank of Western Massachusetts")
        print(f"{'='*60}")
        print(f"Source: {self.base_url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
