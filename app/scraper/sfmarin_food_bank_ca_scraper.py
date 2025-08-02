"""Scraper for SF-Marin Food Bank."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class SfmarinFoodBankCAScraper(ScraperJob):
    """Scraper for SF-Marin Food Bank."""

    def __init__(
        self, scraper_id: str = "sfmarin_food_bank_ca", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'sfmarin_food_bank_ca' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'sfmarin_food_bank_ca'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # Food locator API base URL
        self.base_url = "https://foodlocator.sfmfoodbank.org"
        self.api_url = f"{self.base_url}/resource"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "CA": (37.7749, -122.4194),  # San Francisco
                "San Francisco": (37.7749, -122.4194),
                "Marin": (38.0834, -122.7633),  # Marin County
            }
        )

    async def download_html(self) -> str:
        """Download HTML content from the website.

        Returns:
            str: Raw HTML content

        Raises:
            requests.RequestException: If download fails
        """
        logger.info(f"Downloading HTML from {self.base_url}")
        response = requests.get(
            self.base_url, headers=get_scraper_headers(), timeout=self.timeout
        )
        response.raise_for_status()
        return response.text

    async def fetch_api_data(self, county: str = "sf") -> Dict[str, Any]:
        """Fetch location data from the food locator API.

        Args:
            county: County code to fetch data for ("sf" for San Francisco, "marin" for Marin)

        Returns:
            API response as dictionary

        Raises:
            httpx.HTTPError: If API request fails
        """
        headers = get_scraper_headers()

        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=self.timeout / 3),
                follow_redirects=True,
            ) as client:
                # First get the main page to establish session and get CSRF token
                response = await client.get(self.base_url)
                soup = BeautifulSoup(response.text, "html.parser")

                # Extract CSRF token
                token_input = soup.find("input", {"name": "_token"})
                csrf_token = token_input.get("value") if token_input else None

                if not csrf_token:
                    raise ValueError("Could not find CSRF token")

                # Update headers for API request
                api_headers = headers.copy()
                api_headers.update(
                    {
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/plain, */*",
                        "X-Requested-With": "XMLHttpRequest",
                        "X-CSRF-TOKEN": csrf_token,
                        "Referer": f"{self.base_url}/en/{county}/calfresh",
                        "Origin": self.base_url,
                    }
                )

                # Prepare payload with all required fields
                payload = {
                    "type": "pantry",
                    "county": county,
                    "locale": "en",
                    "_token": csrf_token,
                    "visit_lang": "en",
                    "visit_county": county,
                    "visit_senior": "0",
                    "visit_urgent": "0",
                    "visit_disabled": "0",
                    "visit_zip": "unknown",  # Use 'unknown' when zip is not specified
                    "visit_calfresh": "0",
                    "visit_hdg": "0",
                }

                # Make API request
                response = await client.post(
                    self.api_url, json=payload, headers=api_headers
                )
                response.raise_for_status()
                data = response.json()

                # The response has sites data in different arrays
                # Merge all pantry sites from different categories
                all_sites = []

                # Check for sites in various response keys
                for key in ["sites", "ngns", "sfps", "efbs"]:
                    if key in data and isinstance(data[key], list):
                        all_sites.extend(data[key])

                # Return a normalized response
                return {"sites": all_sites}

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching data from {self.api_url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching data from {self.api_url}: {e}")
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

    def _format_hours(self, start_time: Optional[str], end_time: Optional[str]) -> str:
        """Format distribution hours from start and end times.
        
        Args:
            start_time: Start time string
            end_time: End time string
            
        Returns:
            Formatted hours string
        """
        if start_time and end_time:
            return f"{start_time} - {end_time}"
        elif start_time:
            return start_time
        elif end_time:
            return end_time
        return ""

    def process_api_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process API response data.

        Args:
            data: API response data

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        # Extract sites from the response
        sites = data.get("sites", [])

        for site in sites:
            # Extract basic information
            name = site.get("name", "").strip()
            if not name:
                continue

            # Extract address - different field names in actual API
            full_address = site.get("address", "").strip()

            # Extract distribution information
            dist_info = []
            if site.get("distro_day"):
                dist_info.append(f"Distribution Day: {site['distro_day']}")
            if site.get("distro_start") and site.get("distro_end"):
                dist_info.append(
                    f"Distribution Time: {site['distro_start']} - {site['distro_end']}"
                )
            if site.get("enroll_time"):
                dist_info.append(f"Enrollment Time: {site['enroll_time']}")

            # Extract zip codes served
            zip_codes_served = site.get("service_zips", [])

            # Extract additional languages
            languages = site.get("languages", [])
            # Handle languages that might be dicts or strings
            language_names = []
            for lang in languages:
                if isinstance(lang, dict):
                    language_names.append(lang.get("name", str(lang)))
                else:
                    language_names.append(str(lang))

            # Build notes from various fields
            notes_parts = []
            if dist_info:
                notes_parts.extend(dist_info)
            if zip_codes_served:
                notes_parts.append(
                    f"Zip Codes Served: {', '.join(str(z) for z in zip_codes_served)}"
                )
            if language_names:
                notes_parts.append(f"Additional Languages: {', '.join(language_names)}")
            if site.get("agency_info"):
                agency_info = site["agency_info"]
                if isinstance(agency_info, dict):
                    # Extract English version by default
                    notes_parts.append(agency_info.get("en", str(agency_info)))
                else:
                    notes_parts.append(str(agency_info))

            location = {
                "id": site.get("link_id", "") or str(site.get("id", "")),
                "name": name,
                "address": full_address,
                "city": site.get("city", "").strip(),
                "state": "CA",
                "zip": str(site.get("zip", "")).strip() if site.get("zip") else "",
                "phone": (
                    str(site.get("phone", "")).strip() if site.get("phone") else ""
                ),
                "latitude": float(site["lat"]) if site.get("lat") else None,
                "longitude": float(site["lng"]) if site.get("lng") else None,
                "hours": self._format_hours(
                    site.get("distro_start"), site.get("distro_end")
                ),
                "services": ["Food Pantry"],
                "website": (
                    f"{self.base_url}/en/site/{site.get('link_id', '')}"
                    if site.get("link_id")
                    else ""
                ),
                "notes": " | ".join(notes_parts),
                "enrollment_required": site.get("status") == "enroll",
                "availability": str(site.get("available", "")),
            }

            locations.append(location)

        logger.info(f"Processed {len(locations)} locations from API")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        locations = []

        # Fetch data for both San Francisco and Marin counties
        counties = ["sf", "marin"] if not self.test_mode else ["sf"]

        for county in counties:
            logger.info(f"Fetching locations for {county.upper()} county")
            try:
                response = await self.fetch_api_data(county)
                county_locations = self.process_api_response(response)
                locations.extend(county_locations)
                logger.info(
                    f"Found {len(county_locations)} locations in {county.upper()} county"
                )

                # Add delay between requests
                if county != counties[-1]:
                    await asyncio.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error fetching data for {county} county: {e}")
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
            location["source"] = "sfmarin_food_bank_ca"
            location["food_bank"] = "SF-Marin Food Bank"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "SF-Marin Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.base_url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: SF-Marin Food Bank")
        print(f"{'='*60}")
        print(f"Source: {self.base_url}")
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
