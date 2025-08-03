"""Scraper for Food Bank For New York City."""

import json
import logging
import re
import xml.etree.ElementTree as ElementTree
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class FoodBankForNewYorkCityNyScraper(ScraperJob):
    """Scraper for Food Bank For New York City.
    
    This scraper extracts food pantry locations from a Google My Maps
    KML export embedded on the Food Bank For New York City website.
    """

    def __init__(self, scraper_id: str = "food_bank_for_new_york_city_ny", test_mode: bool = False) -> None:
        """Initialize scraper with ID 'food_bank_for_new_york_city_ny' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'food_bank_for_new_york_city_ny'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)
        
        # The website embeds a Google My Maps iframe
        self.url = "https://www.foodbanknyc.org/get-help/"
        # Google My Maps ID extracted from the iframe
        self.map_id = "1uVjjVxXfLFU4R6V7qjXXRoxCy-IwfMSP"
        # KML export URL for Google My Maps
        self.kml_url = f"https://www.google.com/maps/d/kml?mid={self.map_id}&forcekml=1"
        self.test_mode = test_mode
        
        # Request settings
        self.timeout = 30.0
        
        # Initialize geocoder with custom default coordinates for NYC region
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "NY": (40.7128, -74.0060),  # New York City
                # Borough-specific defaults
                "Manhattan": (40.7831, -73.9712),
                "Brooklyn": (40.6782, -73.9442),
                "Queens": (40.7282, -73.7949),
                "Bronx": (40.8448, -73.8648),
                "Staten Island": (40.5795, -74.1502),
            }
        )

    async def download_kml(self) -> str:
        """Download KML content from Google My Maps.

        Returns:
            str: Raw KML/XML content

        Raises:
            requests.RequestException: If download fails
        """
        logger.info(f"Downloading KML from {self.kml_url}")
        response = requests.get(self.kml_url, headers=get_scraper_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def parse_kml(self, kml_content: str) -> List[Dict[str, Any]]:
        """Parse KML/XML to extract food pantry information.

        Args:
            kml_content: Raw KML/XML content

        Returns:
            List of dictionaries containing food pantry information
        """
        locations: List[Dict[str, Any]] = []
        
        try:
            # Parse KML/XML
            root = ElementTree.fromstring(kml_content)  # noqa: S314
            
            # Define namespace
            ns = {'kml': 'http://www.opengis.net/kml/2.2'}
            
            # Find all Placemarks (locations)
            placemarks = root.findall('.//kml:Placemark', ns)
            
            for placemark in placemarks:
                location = {}
                
                # Extract name
                name_elem = placemark.find('kml:name', ns)
                location['name'] = name_elem.text.strip() if name_elem is not None else ""
                
                # Extract description (contains additional info)
                desc_elem = placemark.find('kml:description', ns)
                description = desc_elem.text if desc_elem is not None else ""
                
                # Parse description HTML content
                if description:
                    soup = BeautifulSoup(description, 'html.parser')
                    # Get text and handle line breaks properly
                    desc_text = soup.get_text(separator='\n', strip=True)
                    
                    # Try to extract structured data from description
                    # Common patterns in Google My Maps descriptions
                    lines = [line.strip() for line in desc_text.split('\n') if line.strip()]
                    
                    # Initialize fields
                    location['address'] = ""
                    location['city'] = ""
                    location['state'] = "NY"
                    location['zip'] = ""
                    location['phone'] = ""
                    location['hours'] = ""
                    location['notes'] = ""
                    
                    # Extract address components
                    # Look for patterns like addresses, phone numbers, etc.
                    full_address = ""
                    for i, line in enumerate(lines):
                        # Skip CDATA markers
                        if line.startswith('<![CDATA[') or line == ']]>':
                            continue
                            
                        # First line is usually the full address
                        if i == 0 or (not full_address and re.search(r'\b\d{5}\b', line)):
                            full_address = line
                            # Extract ZIP code from address
                            zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', line)
                            if zip_match:
                                location['zip'] = zip_match.group(1)
                            continue
                        
                        # Phone pattern
                        if 'phone:' in line.lower() or re.search(r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})', line):
                            phone_match = re.search(r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})', line)
                            if phone_match:
                                location['phone'] = phone_match.group(1)
                            continue
                        
                        # Check for keywords that indicate hours
                        if 'hours:' in line.lower() or any(keyword in line.lower() for keyword in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'mon-', 'tue-', 'wed-', 'open:']):
                            if location['hours']:
                                location['hours'] += " " + line
                            else:
                                location['hours'] = line
                    
                    # Parse full address
                    if full_address:
                        # Try to extract city from address
                        city_match = re.search(r',\s*([^,]+),\s*NY', full_address)
                        if city_match:
                            location['city'] = city_match.group(1).strip()
                            location['address'] = full_address.split(',')[0].strip()
                        else:
                            location['address'] = full_address
                    
                    # Store remaining description as notes
                    if not location['hours'] and desc_text:
                        location['notes'] = desc_text[:500]  # Limit notes length
                
                # Extract coordinates
                coordinates_elem = placemark.find('.//kml:coordinates', ns)
                if coordinates_elem is not None and coordinates_elem.text:
                    coords = coordinates_elem.text.strip().split(',')
                    if len(coords) >= 2:
                        location['longitude'] = float(coords[0])
                        location['latitude'] = float(coords[1])
                
                # Only add if we have a name
                if location.get('name'):
                    locations.append(location)
        
        except (ElementTree.ParseError, Exception) as e:
            logger.error(f"Failed to parse KML: {e}")
            raise
        
        logger.info(f"Parsed {len(locations)} locations from KML")
        return locations

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # Download and parse KML from Google My Maps
        kml_content = await self.download_kml()
        locations = self.parse_kml(kml_content)
        
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
                            state=location.get("state", "NY")
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["success"] += 1
                    except ValueError as e:
                        logger.warning(f"Geocoding failed for {location['address']}: {e}")
                        # Use default coordinates
                        lat, lon = self.geocoder.get_default_coordinates(
                            location="NY",
                            with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                        geocoding_stats["failed"] += 1
                else:
                    # No address, use defaults
                    lat, lon = self.geocoder.get_default_coordinates(
                        location="NY",
                        with_offset=True
                    )
                    location["latitude"] = lat
                    location["longitude"] = lon
                    geocoding_stats["default"] += 1
            
            # Add metadata
            location["source"] = "food_bank_for_new_york_city_ny"
            location["food_bank"] = "Food Bank For New York City"
            
            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(location))
            job_count += 1
            logger.debug(f"Queued job {job_id} for location: {location.get('name', 'Unknown')}")
        
        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "food_bank": "Food Bank For New York City",
            "total_locations_found": len(locations),
            "unique_locations": len(unique_locations),
            "total_jobs_created": job_count,
            "geocoding_stats": geocoding_stats,
            "source": self.url,
            "test_mode": self.test_mode
        }
        
        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: Food Bank For New York City")
        print(f"{'='*60}")
        print(f"Source: {self.url}")
        print(f"Total locations found: {len(locations)}")
        print(f"Unique locations: {len(unique_locations)}")
        print(f"Jobs created: {job_count}")
        print(f"Geocoding - Success: {geocoding_stats['success']}, Failed: {geocoding_stats['failed']}, Default: {geocoding_stats['default']}")
        if self.test_mode:
            print("TEST MODE: Limited processing")
        print("Status: Complete")
        print(f"{'='*60}\n")
        
        # Return summary for archiving
        return json.dumps(summary)
