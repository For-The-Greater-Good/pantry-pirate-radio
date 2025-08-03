"""Scraper for Maryland Food Bank."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class MarylandFoodBankMdScraper(ScraperJob):
    """Scraper for Maryland Food Bank."""

    def __init__(
        self, scraper_id: str = "maryland_food_bank_md", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'maryland_food_bank_md' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'maryland_food_bank_md'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        self.url = "https://mdfoodbank.org/find-food/"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                # TODO: Add appropriate default coordinates for the region
                "MD": (39.063946, -76.802101),  # Maryland Food Bank region
                # Add county-level defaults if needed
            }
        )

    async def download_html(self) -> str:
        """Download HTML content from the website using Playwright for JavaScript rendering.

        Returns:
            str: Raw HTML content with all 25 locations loaded

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

                # Wait for initial page load
                await page.wait_for_timeout(3000)

                # Click on the List view button
                logger.info("Looking for List view button")
                try:
                    # Try different selectors for the List button
                    list_button_selectors = [
                        'button:has-text("List")',
                        'button[aria-label="List"]',
                        "button.list-view",
                        '.view-toggle button:has-text("List")',
                        'text="List"',
                    ]

                    button_found = False
                    for selector in list_button_selectors:
                        try:
                            await page.wait_for_selector(selector, timeout=2000)
                            await page.click(selector)
                            logger.info(f"Clicked List view using selector: {selector}")
                            button_found = True
                            break
                        except Exception as e:
                            # Skip this selector and try the next one
                            logger.debug(f"Selector {selector} failed: {e}")
                            continue

                    if not button_found:
                        logger.info(
                            "List view button not found, checking if already in list view"
                        )
                        # Check if we're already in list view by looking for location elements
                        locations_visible = await page.locator("h3").count()
                        logger.info(
                            f"Found {locations_visible} h3 elements without clicking List"
                        )

                    await page.wait_for_timeout(2000)
                except Exception as e:
                    logger.warning(f"Could not click List view: {e}")

                # Find and click the dropdown to select 25 results
                logger.info("Looking for results per page dropdown")

                # Try to find the dropdown - it might be a select element or a custom dropdown
                try:
                    # Look for the select element by different selectors
                    select_selectors = [
                        'select[name="per_page"]',  # Based on what we saw in the browser
                        'select[name="fwp_per_page"]',
                        "select.per-page-select",
                        "select",  # Any select element
                    ]

                    select_found = False
                    for selector in select_selectors:
                        try:
                            select_element = await page.query_selector(selector)
                            if select_element:
                                # Check if it has the right options
                                options_text = await page.evaluate(
                                    f"""
                                    Array.from(document.querySelector('{selector}').options).map(o => o.text).join(',')
                                """
                                )
                                if "Per page" in options_text:
                                    await page.select_option(
                                        selector, label="25 Per page"
                                    )
                                    logger.info(
                                        f"Selected 25 results from dropdown using selector: {selector}"
                                    )
                                    select_found = True
                                    break
                        except Exception as e:
                            # Skip this selector and try the next one
                            logger.debug(f"Selector {selector} failed: {e}")
                            continue

                    if not select_found:
                        logger.warning("Could not find results dropdown")

                    # Wait for the page to update
                    await page.wait_for_timeout(3000)
                except Exception as e:
                    logger.warning(
                        f"Could not find/select results dropdown, continuing anyway: {e}"
                    )

                # Wait for locations to load
                try:
                    await page.wait_for_selector("h3", timeout=10000)
                    location_count = await page.locator("h3").count()
                    logger.info(f"Found {location_count} h3 elements after loading")
                except Exception as e:
                    logger.warning(f"Timeout waiting for locations: {e}")

                # Get the final HTML
                html_content = await page.content()

                # Log some debugging info
                showing_text = (
                    await page.locator(
                        "text=/Showing \\d+ of \\d+ locations/"
                    ).text_content()
                    if await page.locator(
                        "text=/Showing \\d+ of \\d+ locations/"
                    ).count()
                    > 0
                    else "Not found"
                )
                logger.info(f"Page status: {showing_text}")

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

        # Find all h3 tags directly which contain location names
        # This avoids finding the same h3 multiple times in nested containers
        h3_tags = soup.find_all("h3")
        processed_names = set()  # Track processed location names to avoid duplicates

        for name_tag in h3_tags:
            # Get location name
            name = name_tag.get_text(strip=True)

            # Skip if this is not a location (e.g., other h3 headings on page)
            # Be more inclusive - most h3 tags in the list view should be locations
            # Only skip if it's clearly not a location
            if any(
                skip_word in name.lower()
                for skip_word in [
                    "showing",
                    "results",
                    "page",
                    "feeding maryland",
                    "snap benefits",
                ]
            ):
                continue

            # Skip if we've already processed this location
            if name in processed_names:
                continue
            processed_names.add(name)

            # Find the parent container that has all the location info
            container = name_tag.parent
            while container and container.name != "div":
                container = container.parent

            if not container:
                continue

            # Initialize location data
            location = {
                "name": name,
                "address": "",
                "city": "",
                "state": "MD",
                "zip": "",
                "phone": "",
                "hours": "",
                "services": [],
                "website": "",
                "notes": "",
            }

            # Find address - usually in a link with maps.google.com
            address_link = container.find(
                "a", href=lambda x: x and "maps.google.com/?q=" in x
            )
            if address_link:
                full_address = address_link.get_text(strip=True)
                location["address"] = full_address

                # Parse city, state, zip from address
                # Format is typically: "123 Main St City MD 12345 USA" or "123 Main St, City, MD 12345"
                parts = full_address.replace(",", "").split()
                if len(parts) >= 4:
                    # Find MD in parts
                    md_index = -1
                    for i, part in enumerate(parts):
                        if part == "MD":
                            md_index = i
                            break

                    if md_index > 1 and md_index < len(parts) - 1:
                        # City could be one or two words before MD
                        # Check if the word two positions before MD is a common street suffix
                        street_suffixes = [
                            "St",
                            "Ave",
                            "Rd",
                            "Dr",
                            "Ln",
                            "Ct",
                            "Blvd",
                            "Way",
                            "Pl",
                            "Pkwy",
                        ]
                        if md_index > 2 and parts[md_index - 2] not in street_suffixes:
                            # Two-word city like "Brooklyn Park"
                            location["city"] = (
                                f"{parts[md_index - 2]} {parts[md_index - 1]}"
                            )
                        else:
                            # Single-word city
                            location["city"] = parts[md_index - 1]

                        # Zip is likely the part after MD
                        if parts[md_index + 1].replace("-", "").isdigit():
                            location["zip"] = parts[md_index + 1]

            # Find phone number
            phone_link = container.find("a", href=lambda x: x and x.startswith("tel:"))
            if phone_link:
                location["phone"] = phone_link.get_text(strip=True)

            # Find website
            website_link = None
            for link in container.find_all("a"):
                href = link.get("href", "")
                if href and not href.startswith(
                    ("tel:", "mailto:", "https://maps.google.com")
                ):
                    # Check if this looks like a website (not phone/email/maps)
                    text = link.get_text(strip=True).lower()
                    if any(
                        domain in text
                        for domain in [".org", ".com", ".net", "website", "www"]
                    ):
                        website_link = link
                        break

            if website_link:
                location["website"] = website_link.get("href", "")

            # Find hours - typically in a paragraph after "Hours open:"
            for p in container.find_all("p"):
                text = p.get_text(strip=True)
                if text.lower().startswith("hours open:"):
                    location["hours"] = text[len("hours open:") :].strip()
                    break

            # Determine service type based on name
            if "soup kitchen" in name.lower():
                location["services"] = ["hot meals"]
            elif "pantry" in name.lower() or "food door" in name.lower():
                location["services"] = ["food pantry"]
            elif "emergency" in name.lower():
                location["services"] = ["emergency food"]
            else:
                location["services"] = ["food assistance"]

            # Skip empty items
            if not location["name"]:
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
        #         "state": item.get("state", "MD").strip(),
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
        # grid_points = self.utils.get_state_grid_points("md")
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
        geocoding_stats = {"success": 0, "failed": 0, "default": 0}

        for location in unique_locations:
            # Geocode address if not already present
            if not (location.get("latitude") and location.get("longitude")):
                if location.get("address"):
                    try:
                        lat, lon = self.geocoder.geocode_address(
                            address=location["address"],
                            state=location.get("state", "MD"),
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
                            location="MD", with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["failed"] += 1
                else:
                    # No address, use defaults
                    lat, lon = self.geocoder.get_default_coordinates(
                        location="MD", with_offset=True
                    )
                    location["latitude"] = lat
                    location["longitude"] = lon
                    geocoding_stats["default"] += 1

            # Add metadata
            location["source"] = "maryland_food_bank_md"
            location["food_bank"] = "Maryland Food Bank"

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Maryland Food Bank",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Maryland Food Bank")
        print(f"{'='*60}")
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
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
