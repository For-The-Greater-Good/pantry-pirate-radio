"""Scraper for Second Harvest of Silicon Valley."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class SecondHarvestOfSiliconValleyCaScraper(ScraperJob):
    """Scraper for Second Harvest of Silicon Valley."""

    def __init__(
        self,
        scraper_id: str = "second_harvest_of_silicon_valley_ca",
        test_mode: bool = False,
    ) -> None:
        """Initialize scraper with ID 'second_harvest_of_silicon_valley_ca' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'second_harvest_of_silicon_valley_ca'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # API endpoint for the food locator
        self.base_url = "https://www.shfb.org"
        self.api_endpoint = "/wp-admin/admin-ajax.php"
        self.url = f"{self.base_url}{self.api_endpoint}?action=mmfl_get_data&page_slug=get-food"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                # Silicon Valley region coordinates (San Jose area)
                "CA": (37.3541, -121.9552),  # San Jose, CA
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

        # TODO: Update selectors based on actual website structure
        # Common patterns to look for:
        # - Tables with location data
        # - Divs/sections with location cards
        # - Lists of locations

        # Example: Find location containers
        location_elements = soup.find_all("div", class_="location")  # Update selector

        for _ in location_elements:
            # Extract information from each location
            location = {
                "name": "",  # TODO: Extract name
                "address": "",  # TODO: Extract address
                "city": "",  # TODO: Extract city
                "state": "CA",
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
            data: API response data (dict with 'locations' key)

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        # The API returns a dict with 'locations' key containing location objects
        location_data = data.get("locations", {})
        for location_id, item in location_data.items():
            # Extract basic location info
            street = item.get("street", "").strip()
            city = item.get("city", "").strip()
            state = item.get("state", "CA").strip().upper()
            zip_code = item.get("zip", "").strip()

            location = {
                "id": location_id,
                "site_id": item.get("siteId", location_id),
                "name": item.get("name", "").strip(),
                "address": street,
                "city": city,
                "state": state,
                "zip": zip_code,
                "phone": item.get("phone", "").strip(),
                "latitude": item.get("lat"),
                "longitude": item.get("lng"),
                "county": item.get("county", ""),
                "hours": "",  # Will be filled from campaigns if available
                "services": [],  # Will be filled from campaigns
                "website": item.get("website", ""),
                "notes": "",  # Will be filled from campaigns
            }

            # Skip if no name
            if location["name"]:
                locations.append(location)

        # Process campaigns data for schedules and services
        campaigns_data = data.get("campaigns", {})
        site_campaigns = {}  # Map site_id to campaign data

        for _, campaign in campaigns_data.items():
            site_id = campaign.get("siteId")
            if site_id:
                # Store the most recent/active campaign for each site
                if site_id not in site_campaigns or campaign.get("isActive"):
                    site_campaigns[site_id] = campaign

        # Enrich locations with campaign data
        for location in locations:
            site_id = location.get("site_id")
            if site_id and site_id in site_campaigns:
                campaign = site_campaigns[site_id]

                # Extract services
                services = []
                campaign_type = campaign.get("type", "")
                if campaign_type == "Free Groceries":
                    services.append("Free Groceries")
                elif campaign_type == "Prepared Meals":
                    services.append("Ready-To-Eat Meals")

                # Check distribution access
                if campaign.get("driveThru"):
                    services.append("Drive thru")
                dist_access = campaign.get("distributionAccess") or ""
                if dist_access and "Walk Up" in dist_access:
                    services.append("Walk up")

                # Check documentation requirements
                doc_reqs = campaign.get("documentationReqs", "")
                if doc_reqs == "None" or not doc_reqs:
                    services.append("No documents required")

                location["services"] = services

                # Extract notes/eligibility
                notes_parts = []
                if campaign.get("programEligibility"):
                    notes_parts.append(f"Eligibility: {campaign['programEligibility']}")
                if campaign.get("howOftenCanClientsGo"):
                    notes_parts.append(f"Frequency: {campaign['howOftenCanClientsGo']}")
                if campaign.get("specialInstructions"):
                    notes_parts.append(campaign["specialInstructions"])

                location["notes"] = " | ".join(notes_parts)

                # TODO: Parse schedule data from scheduleDetailDates or other fields
                # For now, use distribution site name as additional info
                if campaign.get("distributionSiteName"):
                    location["distribution_site"] = campaign["distributionSiteName"]

        # Process schedules data if available
        schedules_data = data.get("schedules", {})
        for schedule_key, schedule_list in schedules_data.items():
            # Extract site_id from schedule key (format: "siteId_campaignId")
            parts = schedule_key.split("_")
            if len(parts) >= 2:
                site_id = parts[0]

                # Find matching location
                for location in locations:
                    if location.get("site_id") == site_id:
                        # Parse schedule information
                        hours_list = []
                        for sched in schedule_list:
                            day = sched.get("day", "")
                            start_time = sched.get("start_time", "")
                            end_time = sched.get("end_time", "")
                            if day and start_time:
                                time_str = f"{start_time}"
                                if end_time:
                                    time_str += f" - {end_time}"
                                hours_list.append(f"{day}: {time_str}")

                        if hours_list:
                            location["hours"] = "; ".join(hours_list)
                        break

        logger.info(f"Processed {len(locations)} locations from API")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # Fetch data from the API
        logger.info(f"Fetching location data from API: {self.url}")

        try:
            response = requests.get(
                self.url, headers=get_scraper_headers(), timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            # Process the response
            locations = self.process_api_response(data)
        except Exception as e:
            logger.error(f"Error fetching API data: {e}")
            raise

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
                            state=location.get("state", "CA"),
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
                            location="CA", with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["failed"] += 1
                else:
                    # No address, use defaults
                    lat, lon = self.geocoder.get_default_coordinates(
                        location="CA", with_offset=True
                    )
                    location["latitude"] = lat
                    location["longitude"] = lon
                    geocoding_stats["default"] += 1

            # Add metadata
            location["source"] = "second_harvest_of_silicon_valley_ca"
            location["food_bank"] = "Second Harvest of Silicon Valley"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Second Harvest of Silicon Valley",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Second Harvest of Silicon Valley")
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
