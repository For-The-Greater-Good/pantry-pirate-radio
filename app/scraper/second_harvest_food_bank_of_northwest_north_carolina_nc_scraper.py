"""Scraper for Second Harvest Food Bank of Northwest North Carolina."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper(ScraperJob):
    """Scraper for Second Harvest Food Bank of Northwest North Carolina."""

    def __init__(
        self,
        scraper_id: str = "second_harvest_food_bank_of_northwest_north_carolina_nc",
        test_mode: bool = False,
    ) -> None:
        """Initialize scraper with ID 'second_harvest_food_bank_of_northwest_north_carolina_nc' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'second_harvest_food_bank_of_northwest_north_carolina_nc'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)

        # URL for Second Harvest Food Bank of Northwest NC
        self.url = "https://www.secondharvestnwnc.org/find-help"
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

        # Second Harvest uses an iframe with location data
        # The iframe is loaded dynamically, so we'll use the known URL
        # This URL was discovered by examining the page with Playwright
        iframe_url = "https://www-secondharvestnwnc-org.filesusr.com/html/d9c29a_c4945f05f2116066190568ecd65d99b4.html"

        logger.info(f"Fetching iframe content from: {iframe_url}")
        try:
            response = requests.get(
                iframe_url, headers=get_scraper_headers(), timeout=self.timeout
            )
            response.raise_for_status()
            iframe_html = response.text
            soup = BeautifulSoup(iframe_html, "html.parser")
        except Exception as e:
            logger.error(f"Failed to fetch iframe content: {e}")
            # Try to find iframe in the page as fallback
            iframe = soup.find("iframe", class_="wuksD5")
            if iframe and iframe.get("src"):
                iframe_url = iframe["src"]
                logger.info(f"Found iframe URL in page: {iframe_url}")
                try:
                    response = requests.get(
                        iframe_url, headers=get_scraper_headers(), timeout=self.timeout
                    )
                    response.raise_for_status()
                    iframe_html = response.text
                    soup = BeautifulSoup(iframe_html, "html.parser")
                except Exception as e2:
                    logger.error(f"Failed to fetch iframe content from page: {e2}")
                    return locations
            else:
                return locations

        # Parse location data from the iframe content
        # The locations are in divs with specific structure
        # We need to find the innermost div that contains the location data
        # to avoid duplicates from nested divs
        location_containers = []

        # Find all links with href="#" which indicate location names
        location_links = soup.find_all("a", href="#")

        for link in location_links:
            # Get the parent container that holds all the location info
            parent = link.find_parent("div")
            if parent and parent not in location_containers:
                # Check if this div has the expected structure
                paragraphs = parent.find_all("p")
                if (
                    len(paragraphs) >= 3
                ):  # Need at least name, hours/description, address
                    location_containers.append(parent)

        for container in location_containers:
            name_elem = container.find("a", href="#")
            if not name_elem or not name_elem.get_text(strip=True):
                continue

            paragraphs = container.find_all("p")

            name = name_elem.get_text(strip=True)

            # Extract information from paragraphs
            hours = ""
            address = ""
            phone = ""

            for i, p in enumerate(paragraphs):
                text = p.get_text(strip=True)

                # First paragraph after name is usually hours or description
                if i == 1:
                    hours = text
                # Second paragraph is usually address
                elif i == 2:
                    address = text
                # Phone number paragraph contains a tel: link
                elif p.find("a", href=lambda x: x and x.startswith("tel:")):
                    phone_link = p.find("a", href=lambda x: x and x.startswith("tel:"))
                    phone = phone_link.get_text(strip=True) if phone_link else ""

            # Parse address to extract city, state, zip
            city = ""
            state = "NC"
            zip_code = ""

            if address:
                # Address format: "street, city, zip" or "street, city state zip"
                parts = [p.strip() for p in address.split(",")]
                if len(parts) >= 3:
                    # Format: "street, city, zip"
                    address = parts[0]
                    city = parts[1]
                    # Check if last part is just zip
                    if re.match(r"^\d{5}$", parts[2]):
                        zip_code = parts[2]
                    else:
                        # Extract zip from "state zip" format
                        zip_match = re.search(r"\b(\d{5})\b", parts[2])
                        if zip_match:
                            zip_code = zip_match.group(1)
                elif len(parts) == 2:
                    # Format: "street, city state zip"
                    address = parts[0]
                    city_state_zip = parts[1]
                    # Extract zip code
                    zip_match = re.search(r"\b(\d{5})\b", city_state_zip)
                    if zip_match:
                        zip_code = zip_match.group(1)
                        city = city_state_zip.replace(zip_code, "").strip()
                    else:
                        city = city_state_zip

            # Determine service type from name or hours
            services = []
            name_lower = name.lower()
            hours_lower = hours.lower() if hours else ""

            if "pantry" in name_lower or "pantry" in hours_lower:
                services.append("Food Pantry")
            if "soup kitchen" in name_lower or "soup kitchen" in hours_lower:
                services.append("Soup Kitchen")
            if "shelter" in name_lower or "shelter" in hours_lower:
                services.append("Shelter")
            if "meals" in name_lower or "meal" in hours_lower:
                services.append("Meals")

            # If no specific services identified, default to Food Pantry
            if not services:
                services = ["Food Pantry"]

            location = {
                "name": name,
                "address": address,
                "city": city,
                "state": state,
                "zip": zip_code,
                "phone": phone,
                "hours": hours,
                "services": services,
                "website": "",
                "notes": "",
            }

            # Skip if no name or address
            if not location["name"] or not location["address"]:
                continue

            locations.append(location)

        logger.info(f"Parsed {len(locations)} locations from HTML")
        return locations

    def download_excel_file(self, url: str) -> List[Dict[str, Any]]:
        """Download and parse Excel file.

        Args:
            url: URL of the Excel file

        Returns:
            List of dictionaries containing location information
        """
        locations: List[Dict[str, Any]] = []

        try:
            logger.info(f"Downloading Excel file from: {url}")
            response = requests.get(
                url, headers=get_scraper_headers(), timeout=self.timeout
            )
            response.raise_for_status()

            # Save to temporary file
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".xls", delete=False) as tmp_file:
                tmp_file.write(response.content)
                tmp_file_path = tmp_file.name

            # Read Excel file with xlrd engine, header is at row 2
            df = pd.read_excel(tmp_file_path, engine="xlrd", header=2)
            logger.info(f"Read {len(df)} rows from Excel file")

            # Clean up temp file
            import os

            os.unlink(tmp_file_path)

            # The columns are: Name, Address, City, ZIP, Phone Number, Program Type, Hours of Operation
            # Parse locations from dataframe
            for _, row in df.iterrows():
                # Skip rows that might be county headers (they have empty address fields)
                if pd.isna(row.iloc[1]) or str(row.iloc[1]).strip() == "":
                    continue

                # Extract data from columns by position
                name = str(row.iloc[0] if pd.notna(row.iloc[0]) else "").strip()
                if not name or name in ["Name", "nan", ""]:
                    continue

                # Address components
                address = str(row.iloc[1] if pd.notna(row.iloc[1]) else "").strip()
                city = str(row.iloc[2] if pd.notna(row.iloc[2]) else "").strip()
                state = "NC"  # All locations are in NC
                # Handle zip code - might be int or float in Excel
                zip_val = row.iloc[3]
                if pd.notna(zip_val):
                    # Convert to string and remove decimal if it's a float
                    zip_code = (
                        str(int(zip_val))
                        if isinstance(zip_val, int | float)
                        else str(zip_val).strip()
                    )
                else:
                    zip_code = ""

                # Contact info
                phone = str(row.iloc[4] if pd.notna(row.iloc[4]) else "").strip()

                # Program type and hours
                service_type = str(row.iloc[5] if pd.notna(row.iloc[5]) else "").strip()
                hours = str(row.iloc[6] if pd.notna(row.iloc[6]) else "").strip()

                # Determine services based on program type
                services = []
                if service_type.upper() == "PANTRY":
                    services.append("Food Pantry")
                elif service_type.upper() == "SOUP KITCHEN":
                    services.append("Soup Kitchen")
                elif service_type.upper() == "SHELTER":
                    services.append("Shelter")
                elif service_type.upper() == "PANTRY/ SOUP KITCHEN":
                    services.append("Food Pantry")
                    services.append("Soup Kitchen")
                elif service_type:
                    services.append(service_type)
                else:
                    # Fallback to name/description analysis
                    if "pantry" in name.lower():
                        services.append("Food Pantry")
                    elif "soup" in name.lower() or "kitchen" in name.lower():
                        services.append("Soup Kitchen")
                    elif "shelter" in name.lower():
                        services.append("Shelter")
                    else:
                        services.append("Food Assistance")

                location = {
                    "name": name,
                    "address": address,
                    "city": city,
                    "state": state,
                    "zip": (
                        zip_code.split("-")[0] if zip_code else ""
                    ),  # Remove +4 from zip
                    "phone": phone if phone != "nan" else "",
                    "hours": hours if hours != "nan" else "",
                    "services": services,
                    "website": "",
                    "notes": "",
                }

                # Skip if no name or address
                if location["name"] and (location["address"] or location["city"]):
                    locations.append(location)

            logger.info(f"Parsed {len(locations)} locations from Excel file")

        except Exception as e:
            logger.error(f"Failed to process Excel file: {e}")

        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # Try to download from Excel file first (more reliable)
        excel_url = "https://www.secondharvestnwnc.org/_files/ugd/d9c29a_d1d5fb74fb13469998d2135b0531fa85.xls"
        locations = self.download_excel_file(excel_url)

        # If Excel fails, try HTML/iframe approach
        if not locations:
            logger.info(
                "Excel file parsing failed or returned no data, trying HTML approach"
            )
            html = await self.download_html()
            locations = self.parse_html(html)

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
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for location: {location.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Second Harvest Food Bank of Northwest North Carolina",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "source": self.url,
            "test_mode": self.test_mode,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Second Harvest Food Bank of Northwest North Carolina")
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
