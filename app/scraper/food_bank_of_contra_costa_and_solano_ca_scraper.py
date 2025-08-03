"""Scraper for Food Bank of Contra Costa and Solano."""

import asyncio
import csv
import json
import logging
import re
from io import StringIO
from typing import Any, Dict, List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FoodBankOfContraCostaAndSolanoCAScraper(ScraperJob):
    """Scraper for Food Bank of Contra Costa and Solano."""

    def __init__(self, scraper_id: str = "food_bank_of_contra_costa_and_solano_ca", test_mode: bool = False) -> None:
        """Initialize scraper with ID 'food_bank_of_contra_costa_and_solano_ca' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'food_bank_of_contra_costa_and_solano_ca'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)
        
        # TODO: Update this URL based on the food bank's website
        self.url = "https://www.foodbankccs.org/find-food/foodbycity/"
        self.test_mode = test_mode
        
        # For API-based scrapers
        self.batch_size = 10 if not test_mode else 3
        self.request_delay = 0.5 if not test_mode else 0.05
        self.timeout = 30.0
        
        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                # TODO: Add appropriate default coordinates for the region
                "CA": (36.116203, -119.681564),  # Food Bank of Contra Costa and Solano region
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
        response = requests.get(self.url, headers=get_scraper_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.text

    async def fetch_api_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
                timeout=httpx.Timeout(self.timeout, connect=self.timeout/3)
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

    async def fetch_locations_from_export(self) -> List[Dict[str, Any]]:
        """Fetch locations from the export endpoint.

        Returns:
            List of location dictionaries
        """
        try:
            # The export URL pattern from the page
            export_url = "https://www.foodbankccs.org/wp-content/themes/astra-child/includes/map/export.php"
            
            # Get all location IDs first
            main_html = await self.download_html()
            location_ids = self.extract_location_ids(main_html)
            
            if not location_ids:
                logger.warning("No location IDs found in main page")
                return []
            
            # Fetch export data
            params = {
                "locations": ",".join(location_ids),
                "lang": "en-US"
            }
            
            response = requests.get(export_url, params=params, headers=get_scraper_headers(), timeout=self.timeout)
            response.raise_for_status()
            
            # Parse CSV data
            csv_data = StringIO(response.text)
            reader = csv.DictReader(csv_data)
            
            locations = []
            for row in reader:
                location = {
                    "name": row.get("Name", "").strip(),
                    "address": row.get("Address", "").strip(),
                    "city": row.get("City", "").strip(),
                    "state": "CA",
                    "zip": row.get("Zip", "").strip(),
                    "phone": row.get("Phone", "").strip(),
                    "hours": row.get("Hours", "").strip(),
                    "services": row.get("Services", "").strip(),
                    "notes": row.get("Notes", "").strip(),
                    "latitude": row.get("Latitude"),
                    "longitude": row.get("Longitude"),
                }
                
                # Clean up empty strings
                location = {k: v for k, v in location.items() if v}
                
                if location.get("name"):
                    locations.append(location)
            
            logger.info(f"Fetched {len(locations)} locations from export endpoint")
            return locations
            
        except Exception as e:
            logger.error(f"Error fetching from export endpoint: {e}")
            return []
    
    def extract_location_ids(self, html: str) -> List[str]:
        """Extract location IDs from the main page.

        Args:
            html: Raw HTML content

        Returns:
            List of location IDs
        """
        # Look for location IDs in the download/print links
        ids = []
        
        # Pattern to find location IDs in URLs
        pattern = r'locations=([0-9,%2C]+)'
        matches = re.findall(pattern, html)
        
        if matches:
            # Take the first match and split by comma
            ids_string = matches[0].replace('%2C', ',')
            ids = [id_str for id_str in ids_string.split(',') if id_str]
            
        logger.info(f"Found {len(ids)} location IDs")
        return ids
    
    def extract_city_links(self, html: str) -> List[tuple[str, str]]:
        """Extract city links from the main page.

        Args:
            html: Raw HTML content

        Returns:
            List of tuples containing (city_name, city_url)
        """
        soup = BeautifulSoup(html, "html.parser")
        city_links = []
        
        # Find the accordion sections that contain city links
        # Based on the HTML structure, we need to find links under "Contra Costa County" and "Solano County"
        
        # Look for all links that point to /map-city/ pages
        for link in soup.find_all('a', href=lambda x: x and '/map-city/' in x):
            city_name = link.get_text(strip=True)
            city_url = link.get('href')
            
            # Make absolute URL if needed
            if not city_url.startswith('http'):
                city_url = f"https://www.foodbankccs.org{city_url}"
            
            city_links.append((city_name, city_url))
        
        logger.info(f"Found {len(city_links)} city links")
        return city_links
    
    def parse_city_page(self, html: str, city_name: str) -> List[Dict[str, Any]]:
        """Parse a city page to extract location information.

        Args:
            html: Raw HTML content of city page
            city_name: Name of the city being parsed

        Returns:
            List of dictionaries containing location information
        """
        soup = BeautifulSoup(html, "html.parser")
        locations: List[Dict[str, Any]] = []
        
        # Look for location data in tables or divs
        # The site may use tables with location information
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                # Skip header rows
                if row.find('th'):
                    continue
                
                cells = row.find_all('td')
                if len(cells) >= 2:  # Need at least name and some info
                    location = self.parse_location_row(cells, city_name)
                    if location and location.get("name"):
                        locations.append(location)
        
        # Also check for location divs or other structures
        # Look for common patterns like location cards
        location_divs = soup.find_all('div', class_=['location', 'site', 'pantry'])
        
        for div in location_divs:
            location = self.parse_location_div(div, city_name)
            if location and location.get("name"):
                locations.append(location)
        
        logger.info(f"Parsed {len(locations)} locations from {city_name}")
        return locations
    
    def parse_location_row(self, cells: List, city_name: str) -> Dict[str, Any]:
        """Parse a table row to extract location information.

        Args:
            cells: List of table cells
            city_name: Name of the city

        Returns:
            Dictionary containing location information
        """
        location = {
            "city": city_name,
            "state": "CA",
        }
        
        # Common patterns:
        # Cell 0: Name/Organization
        # Cell 1: Address
        # Cell 2: Phone
        # Cell 3: Hours
        # Cell 4: Services/Notes
        
        if len(cells) > 0:
            location["name"] = cells[0].get_text(strip=True)
        
        if len(cells) > 1:
            address_text = cells[1].get_text(strip=True)
            location["address"] = address_text
            
            # Try to extract zip from address
            zip_match = re.search(r'\b(\d{5})\b', address_text)
            if zip_match:
                location["zip"] = zip_match.group(1)
        
        if len(cells) > 2:
            location["phone"] = cells[2].get_text(strip=True)
        
        if len(cells) > 3:
            location["hours"] = cells[3].get_text(strip=True)
        
        if len(cells) > 4:
            location["notes"] = cells[4].get_text(strip=True)
        
        return location
    
    def parse_location_div(self, div, city_name: str) -> Dict[str, Any]:
        """Parse a div element to extract location information.

        Args:
            div: BeautifulSoup div element
            city_name: Name of the city

        Returns:
            Dictionary containing location information
        """
        location = {
            "city": city_name,
            "state": "CA",
        }
        
        # Look for name in headings
        name_elem = div.find(['h2', 'h3', 'h4', 'strong'])
        if name_elem:
            location["name"] = name_elem.get_text(strip=True)
        
        # Look for address
        address_elem = div.find(text=re.compile(r'\d+.*\b(St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Way|Ct|Court)\b', re.I))
        if address_elem:
            location["address"] = address_elem.strip()
        
        # Look for phone
        phone_elem = div.find(text=re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'))
        if phone_elem:
            location["phone"] = phone_elem.strip()
        
        # Extract all text for notes
        location["notes"] = div.get_text(separator=' ', strip=True)
        
        return location

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
        # The site uses a WordPress plugin called MapifyPro that loads locations dynamically
        # We can access the data through the export URL that's exposed in the page
        
        # First approach: Try the export endpoint
        locations = await self.fetch_locations_from_export()
        
        if not locations:
            # Fallback: Scrape city pages
            logger.info("Export endpoint failed, falling back to city page scraping")
            main_html = await self.download_html()
            city_links = self.extract_city_links(main_html)
            
            if self.test_mode:
                # Limit to first 3 cities in test mode
                city_links = city_links[:3]
            
            locations = []
            
            # Visit each city page to get locations
            for i, (city_name, city_url) in enumerate(city_links):
                if i > 0:
                    await asyncio.sleep(self.request_delay)
                
                logger.info(f"Scraping city {i+1}/{len(city_links)}: {city_name}")
                
                try:
                    response = requests.get(city_url, headers=get_scraper_headers(), timeout=self.timeout)
                    response.raise_for_status()
                    city_html = response.text
                    
                    city_locations = self.parse_city_page(city_html, city_name)
                    locations.extend(city_locations)
                    
                except Exception as e:
                    logger.error(f"Error scraping city {city_name}: {e}")
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
        
        logger.info(f"Found {len(unique_locations)} unique locations (from {len(locations)} total)")
        
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
                            state=location.get("state", "CA")
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["success"] += 1
                    except ValueError as e:
                        logger.warning(f"Geocoding failed for {location['address']}: {e}")
                        # Use default coordinates
                        lat, lon = self.geocoder.get_default_coordinates(
                            location="CA",
                            with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["failed"] += 1
                else:
                    # No address, use defaults
                    lat, lon = self.geocoder.get_default_coordinates(
                        location="CA",
                        with_offset=True
                    )
                    location["latitude"] = lat
                    location["longitude"] = lon
                    geocoding_stats["default"] += 1
            
            # Add metadata
            location["source"] = "food_bank_of_contra_costa_and_solano_ca"
            location["food_bank"] = "Food Bank of Contra Costa and Solano"
            
            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(f"Queued job {job_id} for location: {location.get('name', 'Unknown')}")
        
        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Food Bank of Contra Costa and Solano",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode
        }
        
        # Print summary to CLI
        print(f"\n{'='*60}")
        print(f"SCRAPER SUMMARY: Food Bank of Contra Costa and Solano")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        print(f"Geocoding - Success: {geocoding_stats['success']}, Failed: {geocoding_stats['failed']}, Default: {geocoding_stats['default']}")
        if self.test_mode:
            print(f"TEST MODE: Limited processing")
        print(f"Status: Complete")
        print(f"{'='*60}\n")
        
        # Return summary for archiving
        return json.dumps(summary)