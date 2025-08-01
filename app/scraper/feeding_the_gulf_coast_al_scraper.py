"""Scraper for Feeding the Gulf Coast in Alabama."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FeedingTheGulfCoastALScraper(ScraperJob):
    """Scraper for Feeding the Gulf Coast in Alabama.
    
    This scraper fetches food pantry locations from the Feeding the Gulf Coast
    website using their search results page. It covers locations in Alabama,
    Florida Panhandle, and Mississippi Gulf Coast regions.
    """

    def __init__(self, scraper_id: str = "feeding_the_gulf_coast_al", test_mode: bool = False) -> None:
        """Initialize scraper with ID 'feeding_the_gulf_coast_al' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'feeding_the_gulf_coast_al'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)
        
        self.base_url = "https://www.feedingthegulfcoast.org"
        self.results_url = "https://www.feedingthegulfcoast.org/find-help/find-a-pantry/results"
        self.test_mode = test_mode
        
        # Request settings
        self.timeout = 30.0
        self.request_delay = 0.5 if not test_mode else 0.05
        
        # Initialize geocoder with custom default coordinates for the region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "AL": (30.696, -88.043),  # Mobile, AL (main branch location)
                "FL": (30.412, -87.217),  # Pensacola, FL (panhandle branch)  
                "MS": (30.367, -89.093),  # Gulfport, MS (MS branch)
            }
        )

    async def fetch_results_html(self, address: str = "", radius: int = 100) -> str:
        """Fetch search results HTML from the website.
        
        Args:
            address: Search address (default "^" for all)
            radius: Search radius in miles
            
        Returns:
            HTML content of results page
        """
        params = {
            "address": address,
            "near": str(radius)
        }
        
        headers = get_scraper_headers()
        # Add specific headers that might be required
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Upgrade-Insecure-Requests': '1',
        })
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                self.results_url,
                params=params,
                headers=headers,
                follow_redirects=True
            )
            response.raise_for_status()
            return response.text

    def parse_results_html(self, html: str) -> List[Dict[str, Any]]:
        """Parse location data from results HTML.
        
        Args:
            html: HTML content from results page
            
        Returns:
            List of location dictionaries
        """
        soup = BeautifulSoup(html, 'html.parser')
        locations = []
        
        # Check for no results
        if "No results found" in html:
            logger.warning("No results found on page")
            return locations
        
        # Look for pantry result divs
        result_containers = soup.find_all('div', class_='pantry-result')
        
        for container in result_containers:
            try:
                location = {}
                
                # Find the article element inside
                article = container.find('article')
                if not article:
                    continue
                
                # Extract name from p class="epsilon" or h3
                name_elem = article.find('p', class_='epsilon') or article.find('h3')
                if name_elem:
                    location['name'] = name_elem.get_text(strip=True)
                
                # Extract address
                address_elem = article.find('p', class_='street')
                if address_elem:
                    address_text = address_elem.get_text(separator=' ', strip=True)
                    # Parse address components
                    self.parse_address_text(address_text, location)
                
                # Extract phone
                phone_elem = article.find('p', class_='phone-number')
                if phone_elem:
                    phone = phone_elem.get_text(strip=True)
                    if phone:
                        location['phone'] = phone
                
                # Extract distance
                distance_elem = article.find('p', class_='mileage')
                if distance_elem:
                    distance_text = distance_elem.get_text(strip=True)
                    match = re.search(r'([\d.]+)\s*miles?', distance_text)
                    if match:
                        location['distance'] = match.group(0)
                
                # Extract directions link for potential website
                directions_link = article.find('a', text='Directions')
                if directions_link:
                    # Could parse the Google Maps link to verify address
                    pass
                
                # Extract any additional info (hours, services, etc.)
                # This would be in the text after the mileage
                if distance_elem:
                    full_text = distance_elem.get_text(separator='\n')
                    lines = full_text.split('\n')
                    if len(lines) > 1:
                        # Everything after the first line (distance) is additional info
                        additional_info = '\n'.join(lines[1:]).strip()
                        if additional_info:
                            location['notes'] = additional_info
                
                # Only add if we have at least a name
                if location.get('name'):
                    locations.append(location)
                    
            except Exception as e:
                logger.warning(f"Error parsing result container: {e}")
                continue
        
        logger.info(f"Parsed {len(locations)} locations from HTML")
        return locations
    
    def parse_table_row(self, cells: List[Any]) -> Optional[Dict[str, Any]]:
        """Parse a table row into location data.
        
        Args:
            cells: List of td elements
            
        Returns:
            Location dictionary or None
        """
        if len(cells) < 2:
            return None
            
        location = {
            "name": "",
            "address": "",
            "city": "",
            "state": "",
            "zip": "",
            "phone": "",
            "distance": "",
            "services": [],
            "hours": "",
            "website": "",
        }
        
        # First cell usually contains name and possibly link
        name_cell = cells[0]
        name_link = name_cell.find('a')
        if name_link:
            location["name"] = name_link.get_text(strip=True)
            href = name_link.get('href', '')
            if href and not href.startswith('http'):
                location["website"] = self.base_url + href
            elif href:
                location["website"] = href
        else:
            location["name"] = name_cell.get_text(strip=True)
        
        # Second cell often contains address info
        if len(cells) > 1:
            address_text = cells[1].get_text(separator=' ', strip=True)
            self.parse_address_text(address_text, location)
        
        # Third cell might contain distance
        if len(cells) > 2:
            distance_text = cells[2].get_text(strip=True)
            if 'mile' in distance_text.lower():
                location["distance"] = distance_text
        
        # Additional cells might contain phone, hours, etc.
        for i in range(3, len(cells)):
            cell_text = cells[i].get_text(strip=True)
            
            # Check for phone
            if re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', cell_text):
                location["phone"] = cell_text
            # Could be hours or services
            elif any(day in cell_text.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                location["hours"] = cell_text
            elif cell_text and len(cell_text) > 5:
                # Might be services or notes
                if "services" not in location or not location["services"]:
                    location["services"] = [cell_text]
        
        return location
    
    def parse_location_container(self, container: Any) -> Optional[Dict[str, Any]]:
        """Parse a div/li container into location data.
        
        Args:
            container: BeautifulSoup element
            
        Returns:
            Location dictionary or None
        """
        text = container.get_text(separator=' ', strip=True)
        if not text or len(text) < 10:
            return None
            
        location = {
            "name": "",
            "address": "",
            "city": "",
            "state": "",
            "zip": "",
            "phone": "",
            "distance": "",
            "services": [],
            "hours": "",
            "website": "",
        }
        
        # Look for name in heading or link
        name_elem = container.find(['h2', 'h3', 'h4', 'a'])
        if name_elem:
            location["name"] = name_elem.get_text(strip=True)
            if name_elem.name == 'a':
                href = name_elem.get('href', '')
                if href and not href.startswith('http'):
                    location["website"] = self.base_url + href
                elif href:
                    location["website"] = href
        
        # Parse the full text for other info
        self.parse_location_text(text, location)
        
        return location
    
    def parse_address_text(self, text: str, location: Dict[str, Any]) -> None:
        """Parse address components from text.
        
        Args:
            text: Address text to parse  
            location: Location dict to update
        """
        # Clean up text
        text = re.sub(r'\s+', ' ', text).strip()
        
        # ZIP pattern
        zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', text)
        if zip_match:
            location["zip"] = zip_match.group(1)
        
        # State pattern
        state_match = re.search(r'\b(AL|FL|MS)\b', text)
        if state_match:
            location["state"] = state_match.group(1)
        
        # Street address pattern
        street_match = re.search(
            r'\d+\s+[A-Za-z0-9\s]+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Blvd|Boulevard|Way|Ln|Lane|Pkwy|Parkway|Highway|Hwy|Circle|Cir|Court|Ct|Place|Pl)\b',
            text, re.IGNORECASE
        )
        if street_match:
            location["address"] = street_match.group(0).strip()
        
        # City extraction (between address and state)
        if location.get("address") and state_match:
            # Find text between address and state
            address_end = text.find(location["address"]) + len(location["address"])
            state_start = text.find(state_match.group(0))
            if address_end < state_start:
                city_text = text[address_end:state_start].strip(' ,')
                if city_text and len(city_text) < 50:  # Reasonable city name length
                    location["city"] = city_text
    
    def parse_location_text(self, text: str, location: Dict[str, Any]) -> None:
        """Parse full location text for all components.
        
        Args:
            text: Full text to parse
            location: Location dict to update
        """
        # Distance pattern
        distance_match = re.search(r'(\d+\.?\d*)\s*miles?', text, re.IGNORECASE)
        if distance_match:
            location["distance"] = distance_match.group(0)
        
        # Phone pattern
        phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', text)
        if phone_match:
            location["phone"] = phone_match.group(0)
        
        # Address components
        self.parse_address_text(text, location)
        
        # If no name yet, try to extract from beginning of text
        if not location["name"]:
            # Remove known patterns to isolate name
            clean_text = text
            for pattern in [distance_match, phone_match]:
                if pattern:
                    clean_text = clean_text.replace(pattern.group(0), '')
            
            # Remove address if found
            if location.get("address"):
                clean_text = clean_text.replace(location["address"], '')
            if location.get("city"):
                clean_text = clean_text.replace(location["city"], '')
            if location.get("state"):
                clean_text = clean_text.replace(location["state"], '')
            if location.get("zip"):
                clean_text = clean_text.replace(location["zip"], '')
            
            # First part is likely the name
            parts = clean_text.strip().split(',')
            if parts and parts[0]:
                location["name"] = parts[0].strip()

    async def scrape(self) -> str:
        """Scrape data from Feeding the Gulf Coast website.

        Returns:
            Raw scraped content as JSON string
        """
        logger.info("Starting Feeding the Gulf Coast AL scraper")
        
        # Fetch HTML from results page with broad search
        try:
            logger.info(f"Fetching results from {self.results_url}")
            html = await self.fetch_results_html(address="", radius=100)
            
            # Parse locations from HTML
            locations = self.parse_results_html(html)
            
            logger.info(f"Found {len(locations)} locations")
            
            # In test mode, limit locations
            if self.test_mode and len(locations) > 5:
                locations = locations[:5]
                logger.info(f"Test mode: Limited to {len(locations)} locations")
            
        except Exception as e:
            logger.error(f"Error fetching or parsing results: {e}")
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
                            state=location.get("state", "AL")
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["success"] += 1
                    except ValueError as e:
                        logger.warning(f"Geocoding failed for {location['address']}: {e}")
                        # Use default coordinates
                        lat, lon = self.geocoder.get_default_coordinates(
                            location="AL",
                            with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["failed"] += 1
                else:
                    # No address, use defaults
                    lat, lon = self.geocoder.get_default_coordinates(
                        location="AL",
                        with_offset=True
                    )
                    location["latitude"] = lat
                    location["longitude"] = lon
                    geocoding_stats["default"] += 1
            
            # Add metadata
            location["source"] = "feeding_the_gulf_coast_al"
            location["food_bank"] = "Feeding the Gulf Coast"
            
            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(f"Queued job {job_id} for location: {location.get('name', 'Unknown')}")
        
        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Feeding the Gulf Coast",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.results_url,
            "test_mode": self.test_mode
        }
        
        # Print summary to CLI
        print(f"\n{'='*60}")
        print(f"SCRAPER SUMMARY: Feeding the Gulf Coast")
        print(f"{'='*60}")
        print(f"Source: {self.results_url}")
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