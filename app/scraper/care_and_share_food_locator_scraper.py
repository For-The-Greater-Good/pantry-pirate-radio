"""Scraper for Care and Share Food Locator."""

import csv
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Care_And_Share_Food_LocatorScraper(ScraperJob):
    """Scraper for Care and Share Food Locator.

    This scraper extracts food pantry information from the Care and Share Food Locator website.
    It uses direct HTTP requests to fetch the data from the website's pagination system.
    """

    def __init__(self, scraper_id: str = "care_and_share_food_locator") -> None:
        """Initialize scraper with ID 'care_and_share_food_locator' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'care_and_share_food_locator'
        """
        super().__init__(scraper_id=scraper_id)
        self.base_url = "https://careandshare.org/findfood/food-locator/"
        self.search_url = "https://careandshare.org/findfood/food-locator/?address%5B0%5D=Denver%2C+CO&post%5B0%5D=locations&distance=500&units=imperial&per_page=100&form=1&action=fs"

        # Initialize geocoder with custom default coordinates for Colorado
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "CO": (39.5501, -105.7821),  # Geographic center of Colorado
                "Denver": (39.7392, -104.9903),  # Denver coordinates
            }
        )

        # Track unique locations to avoid duplicates
        self.unique_locations: set[str] = set()

    async def fetch_page(self, url: str) -> str:
        """Fetch HTML content from the specified URL.

        Args:
            url: URL to fetch

        Returns:
            HTML content as string

        Raises:
            httpx.HTTPError: If request fails
        """
        logger.info(f"Fetching page: {url}")

        async with httpx.AsyncClient(
            headers=get_scraper_headers(), follow_redirects=True
        ) as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            return response.text

    def extract_locations(self, html: str) -> list[dict[str, Any]]:
        """Extract location data from HTML content.

        Args:
            html: HTML content

        Returns:
            List of location data dictionaries
        """
        soup = BeautifulSoup(html, "html.parser")
        locations = []

        # Find all location items
        items = soup.select(".gmw-single-item")
        logger.info(f"Found {len(items)} location items on page")

        for item in items:
            try:
                # Extract basic information
                title_elem = item.select_one(".post-title a")
                name = title_elem.get_text(strip=True) if title_elem else ""
                url = (
                    title_elem["href"]
                    if title_elem and "href" in title_elem.attrs
                    else ""
                )

                address_elem = item.select_one(".address a")
                address = address_elem.get_text(strip=True) if address_elem else ""

                distance_elem = item.select_one(".distance")
                distance = distance_elem.get_text(strip=True) if distance_elem else ""

                phone_elem = item.select_one(".field.phone .info a")
                phone = phone_elem.get_text(strip=True) if phone_elem else ""

                # Extract hours of operation
                hours = []
                hours_items = item.select(".gmw-hours-of-operation li")

                for hours_item in hours_items:
                    day_elem = hours_item.select_one(".days")
                    hours_elem = hours_item.select_one(".hours")

                    day = day_elem.get_text(strip=True) if day_elem else ""
                    hours_text = hours_elem.get_text(strip=True) if hours_elem else ""

                    hours.append({"day": day, "hours": hours_text})

                # Extract any additional information
                service_area_elem = item.select_one(".services-wrap p")
                service_area = (
                    service_area_elem.get_text(strip=True) if service_area_elem else ""
                )

                # Create location data dictionary
                location = {
                    "name": name,
                    "url": url,
                    "address": address,
                    "distance": distance,
                    "phone": phone,
                    "hours": hours,
                    "service_area": service_area,
                }

                # Add to locations list
                locations.append(location)
                logger.info(f"Extracted location: {name}")

            except Exception as e:
                logger.error(f"Error extracting location data: {e}")
                continue

        return locations

    def get_next_page_url(self, html: str, current_url: str) -> str | None:
        """Get URL for the next page of results.

        Args:
            html: HTML content
            current_url: Current page URL

        Returns:
            Next page URL or None if no next page
        """
        soup = BeautifulSoup(html, "html.parser")
        next_link = soup.select_one(".gmw-pagination .next.page-numbers")

        if next_link and "href" in next_link.attrs:
            next_url = next_link["href"]

            # Ensure next_url is a string
            if not isinstance(next_url, str):
                return None

            # Ensure the URL has a protocol
            if not next_url.startswith(("http://", "https://")):
                # If it's a relative URL, join it with the base URL
                if next_url.startswith("/"):
                    # Get the base domain from the current URL
                    parsed_url = urlparse(current_url)
                    base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    next_url = urljoin(base_domain, next_url)
                else:
                    # If it's a relative URL without leading slash, join with current URL
                    next_url = urljoin(current_url, next_url)

            logger.info(f"Next page URL: {next_url}")
            return next_url

        return None

    def parse_address(self, address: str) -> dict[str, str]:
        """Parse address string into components.

        Args:
            address: Full address string

        Returns:
            Dictionary with address components
        """
        # Example address: "235 North Jefferson Street, Monument, CO 80132, USA"
        components = {}

        # Extract zip code
        zip_match = re.search(r"(\d{5}(?:-\d{4})?)", address)
        if zip_match:
            components["zip"] = zip_match.group(1)

        # Extract state
        state_match = re.search(r",\s*([A-Z]{2})\s*\d{5}", address)
        if state_match:
            components["state"] = state_match.group(1)

        # Extract city
        city_match = re.search(r",\s*([^,]+),\s*[A-Z]{2}\s*\d{5}", address)
        if city_match:
            components["city"] = city_match.group(1).strip()

        # Extract street address (everything before the city)
        if "city" in components:
            street_parts = address.split(f", {components['city']}")
            if street_parts:
                components["street"] = street_parts[0].strip()

        return components

    def parse_hours(self, hours_data: list[dict[str, str]]) -> list[dict[str, str]]:
        """Parse hours data into HSDS format.

        Args:
            hours_data: List of day/hours dictionaries

        Returns:
            List of HSDS regular_schedule dictionaries
        """
        regular_schedule = []

        for item in hours_data:
            day = item["day"].replace(":", "").strip()
            hours_text = item["hours"].strip()

            # Skip entries with no hours
            if not hours_text:
                continue

            # Handle special cases like "1st Saturday" or days with notes
            if "(" in day:
                day = day.split("(")[0].strip()

            # Extract standard weekday
            weekday = None
            for std_day in [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]:
                if std_day.lower() in day.lower():
                    weekday = std_day
                    break

            if not weekday:
                continue

            # Parse hours text to get opens_at and closes_at
            # Handle complex patterns like "11 a.m. - 1 p.m. & 4 p.m. - 6 p.m."
            time_ranges = hours_text.split("&")

            for time_range in time_ranges:
                time_match = re.search(
                    r"(\d{1,2}(?::\d{2})?\s*(?:a\.m\.|p\.m\.))(?:\s*-\s*|\s+to\s+)(\d{1,2}(?::\d{2})?\s*(?:a\.m\.|p\.m\.))",
                    time_range.strip(),
                )
                if time_match:
                    opens_at = time_match.group(1).strip()
                    closes_at = time_match.group(2).strip()

                    regular_schedule.append(
                        {
                            "weekday": weekday,
                            "opens_at": opens_at,
                            "closes_at": closes_at,
                        }
                    )

        return regular_schedule

    def transform_to_hsds(self, location_data: dict[str, Any]) -> dict[str, Any]:
        """Transform location data to HSDS format.

        Args:
            location_data: Location data dictionary

        Returns:
            Location data in HSDS format
        """
        # Extract address components
        address_parts = self.parse_address(location_data["address"])

        # Geocode the address
        latitude = None
        longitude = None

        try:
            logger.info(f"Geocoding address: {location_data['address']}")
            latitude, longitude = self.geocoder.geocode_address(
                location_data["address"], state="CO"
            )
            logger.info(f"Successfully geocoded to: {latitude}, {longitude}")
        except Exception as e:
            logger.warning(f"Geocoding failed for {location_data['name']}: {e}")
            # Use default coordinates for Colorado with a small offset
            latitude, longitude = self.geocoder.get_default_coordinates(
                location="CO", with_offset=True
            )
            logger.info(f"Using default coordinates: {latitude}, {longitude}")

        # Create HSDS data structure
        hsds_data = {
            "name": location_data["name"],
            "alternate_name": "",
            "description": f"Food pantry in {location_data.get('service_area', 'Colorado')}",
            "url": location_data["url"],
            "status": "active",
            "address": {
                "address_1": address_parts.get("street", ""),
                "address_2": "",
                "city": address_parts.get("city", ""),
                "state_province": address_parts.get("state", "CO"),
                "postal_code": address_parts.get("zip", ""),
                "country": "US",
            },
            "phones": (
                [{"number": location_data["phone"], "type": "voice"}]
                if location_data["phone"]
                else []
            ),
            "regular_schedule": self.parse_hours(location_data["hours"]),
            "location": {"latitude": latitude, "longitude": longitude},
        }

        logger.info(
            f"Transformed location '{location_data['name']}' with address: {hsds_data['address']}"
        )
        return hsds_data

    def get_location_key(self, location_data: dict[str, Any]) -> str:
        """Generate a unique key for a location to avoid duplicates.

        Args:
            location_data: Location data dictionary

        Returns:
            Unique key for the location
        """
        # Use name and address as the key
        return f"{location_data['name']}|{location_data['address']}"

    def write_to_csv(
        self, locations: dict[str, dict[str, Any]], hsds_data: dict[str, dict[str, Any]]
    ) -> str:
        """Write location data to a CSV file.

        Args:
            locations: Dictionary of location data
            hsds_data: Dictionary of HSDS data

        Returns:
            Path to the CSV file
        """
        # Create outputs directory if it doesn't exist
        output_dir = Path(__file__).parent.parent.parent / "outputs"
        output_dir.mkdir(exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = output_dir / f"care_and_share_locations_{timestamp}.csv"

        # Define CSV columns
        columns = [
            "Name",
            "Address",
            "City",
            "State",
            "Zip",
            "Phone",
            "Hours",
            "URL",
            "Latitude",
            "Longitude",
            "Service Area",
        ]

        # Write to CSV
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()

            for location_key, location in locations.items():
                # Get HSDS data for this location
                hsds = hsds_data.get(location_key, {})

                # Format hours
                hours_text = ""
                if location.get("hours"):
                    hours_list = []
                    for hour in location.get("hours", []):
                        if hour.get("day") and hour.get("hours"):
                            hours_list.append(f"{hour['day']} {hour['hours']}")
                    hours_text = "; ".join(hours_list)

                # Write row
                writer.writerow(
                    {
                        "Name": location.get("name", ""),
                        "Address": hsds.get("address", {}).get("address_1", ""),
                        "City": hsds.get("address", {}).get("city", ""),
                        "State": hsds.get("address", {}).get("state_province", ""),
                        "Zip": hsds.get("address", {}).get("postal_code", ""),
                        "Phone": location.get("phone", ""),
                        "Hours": hours_text,
                        "URL": location.get("url", ""),
                        "Latitude": hsds.get("location", {}).get("latitude", ""),
                        "Longitude": hsds.get("location", {}).get("longitude", ""),
                        "Service Area": location.get("service_area", ""),
                    }
                )

        logger.info(f"Wrote {len(locations)} locations to CSV file: {csv_file}")
        return str(csv_file)

    async def scrape(self) -> str:
        """Scrape data from Care and Share Food Locator.

        Returns:
            Summary of scraping operation as JSON string
        """
        all_locations = []
        current_url = self.search_url
        page_num = 1

        while current_url:
            try:
                # Fetch page content
                html = await self.fetch_page(current_url)

                # Extract locations from page
                locations = self.extract_locations(html)
                logger.info(
                    f"Extracted {len(locations)} locations from page {page_num}"
                )

                # Add to all locations
                all_locations.extend(locations)

                # Get next page URL
                next_url = self.get_next_page_url(html, current_url)

                if next_url and next_url != current_url:
                    current_url = next_url
                    page_num += 1
                else:
                    logger.info("No more pages to process")
                    break

            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
                break

        # Process locations and submit to queue
        job_count = 0
        unique_locations = {}
        hsds_data = {}

        for location in all_locations:
            # Generate a unique key for the location
            location_key = self.get_location_key(location)

            # Skip if we've already processed this location
            if location_key in unique_locations:
                continue

            # Add to unique locations
            unique_locations[location_key] = location

        logger.info(
            f"Found {len(all_locations)} total locations, {len(unique_locations)} unique"
        )

        # Submit unique locations to queue
        for location_key, location in unique_locations.items():
            try:
                # Transform to HSDS format
                hsds_data[location_key] = self.transform_to_hsds(location)

                # Submit to queue
                job_id = self.submit_to_queue(json.dumps(hsds_data[location_key]))
                job_count += 1
                logger.info(f"Queued job {job_id} for location: {location['name']}")

            except Exception as e:
                logger.error(f"Error processing location {location['name']}: {e}")
                continue

        # Write locations to CSV file
        csv_file = self.write_to_csv(unique_locations, hsds_data)

        # Create summary
        summary = {
            "total_locations_found": len(all_locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "csv_file": csv_file,
            "source": self.base_url,
        }

        # Print summary to CLI
        print("\nScraper Summary:")
        print(f"Source: {self.base_url}")
        print(f"Total locations found: {len(all_locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Total jobs created: {job_count}")
        print(f"CSV file: {csv_file}")
        print("Status: Complete\n")

        # Return summary as JSON string
        return json.dumps(summary)
