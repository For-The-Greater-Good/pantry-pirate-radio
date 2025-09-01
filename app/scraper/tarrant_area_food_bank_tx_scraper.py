"""Scraper for Tarrant Area Food Bank."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, cast

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class TarrantAreaFoodBankTXScraper(ScraperJob):
    """Scraper for Tarrant Area Food Bank."""

    def __init__(
        self, scraper_id: str = "tarrant_area_food_bank_tx", test_mode: bool = False
    ) -> None:
        """Initialize scraper with ID 'tarrant_area_food_bank_tx' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'tarrant_area_food_bank_tx'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # TODO: Update this URL based on the food bank's website
        self.url = "https://tafb.org/find-food/"
        self.test_mode = test_mode

        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0

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

        # TAFB uses Store Locator Plus which renders locations in results container
        # Look for the results wrapper that contains location entries
        results_wrapper = soup.find("div", class_="results_wrapper")

        if not results_wrapper:
            # Try alternative selectors
            results_wrapper = soup.find("div", {"id": "map_sidebar"})

        if results_wrapper:
            # Find individual result entries - Store Locator Plus uses numbered result divs
            location_divs = cast(Any, results_wrapper).find_all("div", recursive=False)

            for div in location_divs:
                # Skip non-location divs
                div_class = div.get("class", [])
                if isinstance(div_class, list):
                    div_class = " ".join(div_class)
                else:
                    div_class = str(div_class)

                if "result" not in div_class.lower():
                    continue

                # Extract name - usually in a span or div with location name
                name = ""
                name_elem = div.find(
                    ["span", "div"], class_=lambda x: x and "name" in str(x).lower()
                )
                if not name_elem:
                    # Try to find first text that looks like a name
                    for elem in div.find_all(["span", "div", "strong"]):
                        text = elem.get_text(strip=True)
                        if (
                            text
                            and len(text) > 5
                            and not any(char.isdigit() for char in text[:5])
                        ):
                            name = text
                            break
                else:
                    name = name_elem.get_text(strip=True)

                # Extract address - look for element with address class
                address = ""
                address_elem = div.find(
                    ["div", "span"], class_=lambda x: x and "address" in str(x).lower()
                )
                if address_elem:
                    # Get all text including line breaks as spaces
                    address = address_elem.get_text(" ", strip=True)

                # Extract phone number - look for pattern
                phone = ""
                import re

                phone_elem = div.find(
                    ["span", "div"], class_=lambda x: x and "phone" in str(x).lower()
                )
                if phone_elem:
                    phone = phone_elem.get_text(strip=True)
                else:
                    # Try to find phone pattern in full text
                    full_text = div.get_text(" ", strip=True)
                    phone_match = re.search(
                        r"\b(\d{3}[-.]?\d{3}[-.]?\d{4})\b", full_text
                    )
                    if phone_match:
                        phone = phone_match.group(1)

                # Extract description/hours - often in description element
                notes = ""
                desc_elem = div.find(
                    ["div", "span"],
                    class_=lambda x: x and "description" in str(x).lower(),
                )
                if desc_elem:
                    notes = desc_elem.get_text(" ", strip=True)

                location = {
                    "name": name,
                    "address": address,  # Complete address as single field for LLM parsing
                    "phone": phone,
                    "hours": notes,  # Hours often in the description
                    "services": ["Food Pantry"],  # Default service
                    "website": "",
                    "notes": notes,
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
        #         "state": item.get("state", "TX").strip(),
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
        # TAFB uses Store Locator Plus but doesn't expose a clean API endpoint
        # We'll need to search by ZIP codes to get all locations

        # Major ZIP codes in the Tarrant Area Food Bank service area
        # This covers Fort Worth and surrounding areas
        search_zips = [
            # Fort Worth core
            "76102",
            "76104",
            "76105",
            "76106",
            "76107",
            "76109",
            "76110",
            "76111",
            "76112",
            "76114",
            "76115",
            "76116",
            "76117",
            "76118",
            "76119",
            "76120",
            "76123",
            "76126",
            "76127",
            "76129",
            "76131",
            "76132",
            "76133",
            "76134",
            "76135",
            "76137",
            "76140",
            "76147",
            "76148",
            "76164",
            "76177",
            "76179",
            "76180",
            "76182",
            # Denton area (TAFB North)
            "76201",
            "76205",
            "76207",
            "76208",
            "76209",
            "76210",
            # Weatherford area (TAFB West)
            "76086",
            "76087",
            "76088",
            # Additional coverage areas
            "76008",
            "76020",
            "76028",
            "76033",
            "76034",
            "76036",
            "76039",
            "76052",
            "76053",
            "76054",
            "76058",
            "76059",
            "76060",
            "76063",
            "76065",
            "76066",
            "76071",
            "76078",
            "76092",
            "76093",
            "76108",
        ]

        # Limit searches in test mode
        if self.test_mode:
            search_zips = search_zips[:3]

        all_locations = []
        seen_locations = set()

        for i, zip_code in enumerate(search_zips):
            if i > 0:
                await asyncio.sleep(self.request_delay)

            logger.info(f"Searching ZIP {i+1}/{len(search_zips)}: {zip_code}")

            try:
                # Make search request with ZIP code and large radius
                # Store Locator Plus accepts search parameters in the URL
                search_url = f"{self.url}?address={zip_code}&radius=50"

                response = requests.get(
                    search_url, headers=get_scraper_headers(), timeout=self.timeout
                )
                response.raise_for_status()

                # Parse the response HTML
                locations = self.parse_html(response.text)

                # Deduplicate based on name and address
                for location in locations:
                    location_key = (
                        location.get("name", "").lower().strip(),
                        location.get("address", "").lower().strip(),
                    )
                    if (
                        location_key not in seen_locations and location_key[0]
                    ):  # Has name
                        seen_locations.add(location_key)
                        all_locations.append(location)

            except Exception as e:
                logger.error(f"Error searching ZIP {zip_code}: {e}")
                continue

        logger.info(f"Found {len(all_locations)} unique locations across all searches")

        # Deduplicate one more time to be safe
        unique_locations = []
        seen_ids = set()

        for location in all_locations:
            # Create unique ID
            location_id = f"{location.get('name', '')}_{location.get('address', '')}"

            if location_id not in seen_ids:
                seen_ids.add(location_id)
                unique_locations.append(location)

        logger.info(
            f"Found {len(unique_locations)} unique locations (from {len(all_locations)} total)"
        )

        # Process each location
        job_count = 0

        for location in unique_locations:
            # Note: Latitude and longitude will be handled by the validator service
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Tarrant Area Food Bank",
            "total_locations": len(all_locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "search_zips_used": len(search_zips),
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Tarrant Area Food Bank")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"Total locations found: {len(all_locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        if self.test_mode:
            print("TEST MODE: Limited processing")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
