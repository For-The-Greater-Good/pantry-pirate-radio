"""Scraper for FIND Food Bank."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FindFoodBankCaScraper(ScraperJob):
    """Scraper for FIND Food Bank."""

    def __init__(
        self, scraper_id: str = "find_food_bank_ca", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'find_food_bank_ca' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'find_food_bank_ca'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # Updated URL to the actual map page
        self.url = "https://findfoodbank.org/map/"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0


    async def download_html(self) -> str:
        """Download HTML content from the website using Playwright for JavaScript rendering.

        Returns:
            str: Raw HTML content with dynamically loaded data

        Raises:
            Exception: If download fails
        """
        logger.info(f"Downloading HTML from {self.url} using Playwright")

        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Navigate to the page
                await page.goto(self.url, wait_until="networkidle")

                # Wait a bit for the page to initialize
                await page.wait_for_timeout(5000)

                # Check if FacetWP is loaded
                has_facetwp = await page.evaluate("typeof FWP !== 'undefined'")
                logger.info(f"FacetWP loaded: {has_facetwp}")

                # Check FWP settings
                if has_facetwp:
                    fwp_settings = await page.evaluate("FWP.settings || {}")
                    logger.info(
                        f"FWP settings keys: {list(fwp_settings.keys()) if isinstance(fwp_settings, dict) else 'none'}"
                    )

                    # Try to trigger FacetWP refresh to load data
                    try:
                        await page.evaluate("FWP.refresh()")
                        logger.info("Triggered FWP refresh")
                        await page.wait_for_timeout(
                            5000
                        )  # Wait for refresh to complete
                    except Exception as e:
                        logger.warning(f"Could not trigger FWP refresh: {e}")

                # Try to wait for locations, but don't fail if they don't appear
                try:
                    await page.wait_for_selector("div.facetwp-location", timeout=10000)
                    location_count = await page.locator("div.facetwp-location").count()
                    logger.info(
                        f"Found {location_count} locations after JavaScript loading"
                    )
                except Exception as e:
                    logger.warning(
                        f"No locations found via selector, checking page content: {e}"
                    )

                # Get the full HTML after JavaScript has loaded
                html_content = await page.content()

                # Log a snippet to debug
                if "facetwp-location" not in html_content:
                    logger.warning("No facetwp-location divs found in page content")
                    # Check if there's a different structure
                    soup = BeautifulSoup(html_content, "html.parser")
                    # Look for any divs that might contain location data
                    potential_locations = soup.find_all(
                        ["div", "article", "section"],
                        class_=re.compile(r"(location|pantry|site|facility)", re.I),
                    )
                    logger.info(
                        f"Found {len(potential_locations)} potential location elements"
                    )

                return html_content

            finally:
                await browser.close()

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

        # Based on MCP Playwright investigation, locations are in a specific container
        # Look for the main content area that contains locations
        main_content = (
            soup.find("div", class_="entry-content")
            or soup.find("div", class_="content")
            or soup.find("main")
            or soup.body
        )

        if not main_content:
            logger.warning("Could not find main content area")
            return locations

        # Look for divs that contain location information
        # The pattern observed is that each location is in a div with two child divs:
        # - First child div contains the name
        # - Second child div contains the details (paragraphs with hours, location, contact)
        potential_location_containers = main_content.find_all("div", recursive=True)

        for container in potential_location_containers:
            # Check if this div has exactly 2 direct child divs
            child_divs = [child for child in container.children if child.name == "div"]

            if len(child_divs) == 2:
                # First div should contain the name
                name_div = child_divs[0]
                details_div = child_divs[1]

                # Get the name text
                name = name_div.get_text(strip=True)

                # Skip if name is empty or too long (probably not a location name)
                if not name or len(name) > 200:
                    continue

                # Check if details div contains paragraphs with location info
                paragraphs = details_div.find_all("p")
                if not paragraphs:
                    continue

                # Look for location markers in the paragraphs
                has_location_info = False
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if any(
                        marker in text
                        for marker in ["Hours of Operation:", "Location:", "Contact:"]
                    ):
                        has_location_info = True
                        break

                if not has_location_info:
                    continue

                # This looks like a location entry, parse it
                location = {
                    "name": name,
                    "address": "",
                    "city": "",
                    "state": "CA",
                    "zip": "",
                    "phone": "",
                    "hours": "",
                    "services": [],
                    "website": self.url,
                    "notes": "",
                }

                # Parse paragraphs for details
                notes_list = []

                for p in paragraphs:
                    text = p.get_text(strip=True)

                    # Parse hours
                    if "Hours of Operation:" in text:
                        hours_text = text.replace("Hours of Operation:", "").strip()
                        location["hours"] = hours_text

                    # Parse location/address
                    elif "Location:" in text:
                        address_text = text.replace("Location:", "").strip()
                        location["address"] = address_text

                        # Extract city and zip from address
                        # Pattern to match "City, CA ZIP" or "City CA ZIP"
                        match = re.search(r"([^,]+),?\s+CA\s+(\d{5})", address_text)
                        if match:
                            # The city is everything before ", CA" or " CA"
                            city_match = re.search(
                                r"([A-Za-z\s\-]+),?\s+CA\s+\d{5}", address_text
                            )
                            if city_match:
                                city_part = city_match.group(1).strip()
                                # Get just the city name (last part after street address)
                                city_parts = city_part.split()
                                # Find where the street address ends (usually has numbers or "St", "Ave", etc)
                                city_start_idx = 0
                                for i, part in enumerate(city_parts):
                                    if any(
                                        street_type in part
                                        for street_type in [
                                            "St",
                                            "St.",
                                            "Ave",
                                            "Ave.",
                                            "Blvd",
                                            "Blvd.",
                                            "Dr",
                                            "Dr.",
                                            "Rd",
                                            "Rd.",
                                            "Way",
                                            "Ln",
                                            "Pkwy",
                                            "Pl",
                                        ]
                                    ):
                                        city_start_idx = i + 1
                                        break
                                if city_start_idx < len(city_parts):
                                    location["city"] = " ".join(
                                        city_parts[city_start_idx:]
                                    )
                                else:
                                    # Fallback: take the last word as city
                                    location["city"] = (
                                        city_parts[-1] if city_parts else ""
                                    )
                            location["zip"] = match.group(2)

                    # Parse contact/phone
                    elif "Contact:" in text:
                        # Extract phone number using regex
                        phone_match = re.search(
                            r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text
                        )
                        if phone_match:
                            location["phone"] = phone_match.group()

                    # Other text becomes notes
                    elif text and not any(
                        x in text
                        for x in ["See Mobile Market Calendar", "FIND Food Bank at"]
                    ):
                        notes_list.append(text)

                # Combine notes
                if notes_list:
                    location["notes"] = " | ".join(notes_list)

                # Skip if no address
                if not location["address"]:
                    continue

                locations.append(location)

        # If we didn't find locations with the above pattern, fall back to looking for facetwp-location divs
        if not locations:
            logger.info(
                "No locations found with generic div pattern, trying facetwp-location pattern"
            )
            location_elements = soup.find_all(
                "div",
                class_=lambda x: x
                and "facetwp-location" in x
                and "facetwp-location-details" not in x,
            )

            for element in location_elements:
                # Extract name from title element
                name_elem = element.find(
                    class_=lambda x: x and "facetwp-location-title" in x
                )
                if not name_elem:
                    continue
                name = name_elem.get_text(strip=True)

                # Get details section
                details_elem = element.find(
                    class_=lambda x: x and "facetwp-location-details" in x
                )
                if not details_elem:
                    continue

                # Initialize location data
                location = {
                    "name": name,
                    "address": "",
                    "city": "",
                    "state": "CA",
                    "zip": "",
                    "phone": "",
                    "hours": "",
                    "services": [],
                    "website": self.url,
                    "notes": "",
                }

                # Parse paragraphs for details
                paragraphs = details_elem.find_all("p")
                notes_list = []

                for p in paragraphs:
                    text = p.get_text(strip=True)

                    # Parse hours
                    if "Hours of Operation:" in text:
                        hours_text = text.replace("Hours of Operation:", "").strip()
                        location["hours"] = hours_text

                    # Parse location/address
                    elif "Location:" in text:
                        address_text = text.replace("Location:", "").strip()
                        location["address"] = address_text

                        # Extract city and zip from address
                        # Pattern to match "City, CA ZIP" or "City CA ZIP"
                        match = re.search(r"([^,]+),?\s+CA\s+(\d{5})", address_text)
                        if match:
                            # The city is everything before ", CA" or " CA"
                            city_match = re.search(
                                r"([A-Za-z\s\-]+),?\s+CA\s+\d{5}", address_text
                            )
                            if city_match:
                                city_part = city_match.group(1).strip()
                                # Get just the city name (last part after street address)
                                city_parts = city_part.split()
                                # Find where the street address ends (usually has numbers or "St", "Ave", etc)
                                city_start_idx = 0
                                for i, part in enumerate(city_parts):
                                    if any(
                                        street_type in part
                                        for street_type in [
                                            "St",
                                            "St.",
                                            "Ave",
                                            "Ave.",
                                            "Blvd",
                                            "Blvd.",
                                            "Dr",
                                            "Dr.",
                                            "Rd",
                                            "Rd.",
                                            "Way",
                                            "Ln",
                                            "Pkwy",
                                            "Pl",
                                        ]
                                    ):
                                        city_start_idx = i + 1
                                        break
                                if city_start_idx < len(city_parts):
                                    location["city"] = " ".join(
                                        city_parts[city_start_idx:]
                                    )
                                else:
                                    # Fallback: take the last word as city
                                    location["city"] = (
                                        city_parts[-1] if city_parts else ""
                                    )
                            location["zip"] = match.group(2)

                    # Parse contact/phone
                    elif "Contact:" in text:
                        # Extract phone number using regex
                        phone_match = re.search(
                            r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text
                        )
                        if phone_match:
                            location["phone"] = phone_match.group()

                    # Other text becomes notes
                    elif text and not any(
                        x in text
                        for x in ["See Mobile Market Calendar", "FIND Food Bank at"]
                    ):
                        notes_list.append(text)

                # Combine notes
                if notes_list:
                    location["notes"] = " | ".join(notes_list)

                # Skip if no address
                if not location["address"]:
                    continue

                locations.append(location)

        logger.info(f"Parsed {len(locations)} locations from HTML")
        return locations

    def process_api_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process API response data.

        Args:
            data: API response data

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        # TODO: Extract locations from API response
        # Common patterns:
        # - data['results'] or data['locations'] or data['items']
        # - May need to handle pagination

        # Example:
        # for item in data.get('locations', []):
        #     location = {
        #         "id": item.get("id"),
        #         "name": item.get("name", "").strip(),
        #         "address": item.get("address", "").strip(),
        #         "city": item.get("city", "").strip(),
        #         "state": item.get("state", "CA").strip(),
        #         "zip": item.get("zip", "").strip(),
        #         "phone": item.get("phone", "").strip(),
        #         "latitude": item.get("latitude"),
        #         "longitude": item.get("longitude"),
        #         "hours": item.get("hours", ""),
        #         "services": item.get("services", []),
        #     }
        #     locations.append(location)

        logger.info(f"Processed {len(locations)} locations from API")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # TODO: Choose the appropriate scraping approach

        # Option 1: HTML Scraping
        # =====================
        # Download and parse HTML
        html = await self.download_html()
        locations = self.parse_html(html)

        # Option 2: API Scraping
        # =====================
        # # Fetch data from API
        # response = await self.fetch_api_data("endpoint/path", params={"key": "value"})
        # locations = self.process_api_response(response)

        # Option 3: Grid-based API Search (for APIs with geographic search)
        # ================================================================
        # from app.models.geographic import GridPoint
        #
        # # Get grid points for the state
        # grid_points = self.utils.get_state_grid_points("ca")
        #
        # # Limit grid points in test mode
        # if self.test_mode:
        #     grid_points = grid_points[:3]
        #
        # locations = []
        # for i, point in enumerate(grid_points):
        #     if i > 0:
        #         await asyncio.sleep(self.request_delay)
        #
        #     # Search around this grid point
        #     response = await self.fetch_api_data(
        #         "search",
        #         params={"lat": point.lat, "lng": point.lng, "radius": 50}
        #     )
        #     locations.extend(self.process_api_response(response))

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
            # Note: Latitude and longitude will be handled by the validator service

            # Add metadata
            location["source"] = "find_food_bank_ca"
            location["food_bank"] = "FIND Food Bank"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "FIND Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: FIND Food Bank")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        if self.test_mode:
            print("TEST MODE: Limited processing")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
