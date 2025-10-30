"""Scraper for FoodFinder.us encrypted API."""

import asyncio
import hashlib
import json
import logging
import time
import zlib
from typing import Any

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.models.geographic import GridPoint
from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Foodfinder_UsScraper(ScraperJob):
    """Scraper for FoodFinder.us encrypted API.

    This scraper:
    1. Uses grid-based search to query the encrypted API
    2. Decrypts API responses using discovered algorithm
    3. Fetches detailed information for each location
    4. Deduplicates and submits to queue

    The API uses AES-256-CBC encryption with MD5(timestamp) as password.
    The decryption algorithm matches the JavaScript implementation:
    - MD5 hash the timestamp -> hex string -> use as password
    - Response is OpenSSL encrypted format: "Salted__" + salt + ciphertext
    - EVP_BytesToKey derives key/IV from password + salt
    - AES-256-CBC decryption
    - Standard zlib decompression
    """

    def __init__(self, scraper_id: str = "foodfinder_us", test_mode: bool = False) -> None:
        """Initialize scraper with ID 'foodfinder_us' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'foodfinder_us'
            test_mode: If True, only process limited data for testing
        """
        super().__init__(scraper_id=scraper_id)
        self.api_url = "https://api-v2-prod-dot-foodfinder-183216.uc.r.appspot.com"
        self.web_url = "https://foodfinder-prod-dot-foodfinder-183216.uc.r.appspot.com"
        self.batch_size = 25
        self.request_delay = 0.2  # 200ms between requests
        self.test_mode = test_mode
        self.total_locations = 0
        self.unique_locations: set[str] = set()
        self.location_data: dict[str, dict[str, Any]] = {}

    def get_api_headers(self) -> dict[str, str]:
        """Get required CORS headers for API requests.

        Returns:
            Dictionary of HTTP headers
        """
        return {
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.web_url}/",
            "Origin": self.web_url,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }

    def evp_bytes_to_key(
        self, password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16
    ) -> tuple[bytes, bytes]:
        """Derive key and IV using OpenSSL's EVP_BytesToKey algorithm.

        This matches CryptoJS's key derivation when you pass a password string.

        Args:
            password: Password bytes
            salt: Salt bytes (8 bytes from "Salted__" header)
            key_len: Desired key length (32 for AES-256)
            iv_len: Desired IV length (16 for AES)

        Returns:
            Tuple of (key, iv)
        """
        derived = b""
        prev = b""

        while len(derived) < key_len + iv_len:
            prev = hashlib.md5(prev + password + salt).digest()
            derived += prev

        return derived[:key_len], derived[key_len : key_len + iv_len]

    def decrypt_response(self, encrypted_data: bytes, timestamp: str) -> str:
        """Decrypt FoodFinder.us API response.

        Algorithm matches the JavaScript N1 function:
        1. MD5 hash the timestamp -> hex string -> use as password
        2. Response is OpenSSL encrypted format: "Salted__" + salt + ciphertext
        3. EVP_BytesToKey derives key/IV from password + salt
        4. AES-256-CBC decryption
        5. Standard zlib decompression

        Args:
            encrypted_data: Raw encrypted response bytes
            timestamp: Timestamp string (same as _time parameter in API call)

        Returns:
            Decrypted JSON string

        Raises:
            ValueError: If encrypted format is invalid
            zlib.error: If decompression fails
        """
        # Handle truly empty response
        if not encrypted_data:
            return "[]"

        # Step 1: Create password from MD5(timestamp) as hex
        password_hash = hashlib.md5(timestamp.encode()).hexdigest()
        password = password_hash.encode("utf-8")

        # Step 2: Check for OpenSSL format
        if not encrypted_data.startswith(b"Salted__"):
            # If it's already JSON, return it as is
            try:
                # Try to decode as UTF-8 and parse as JSON to verify
                decoded = encrypted_data.decode("utf-8")
                json.loads(decoded)  # Verify it's valid JSON
                return decoded
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError(
                    f"Invalid encrypted format. Expected 'Salted__' prefix, got: {encrypted_data[:16]!r}"
                )

        # Step 3: Extract salt and ciphertext
        salt = encrypted_data[8:16]
        ciphertext = encrypted_data[16:]

        # Step 4: Derive key and IV using EVP_BytesToKey (matches CryptoJS)
        key, iv = self.evp_bytes_to_key(password, salt, key_len=32, iv_len=16)

        # Step 5: Decrypt using AES-256-CBC
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()

        # Step 6: Remove PKCS7 padding
        padding_length = decrypted[-1]
        decrypted_no_padding = decrypted[:-padding_length]

        # Step 7: Decompress (API uses different formats for empty vs populated areas)
        try:
            # Try standard zlib first (works for populated areas)
            inflated = zlib.decompress(decrypted_no_padding)
        except zlib.error:
            try:
                # Try gzip format (works for empty areas)
                inflated = zlib.decompress(decrypted_no_padding, zlib.MAX_WBITS | 16)
            except zlib.error:
                try:
                    # Try raw deflate as last resort
                    inflated = zlib.decompress(decrypted_no_padding, -zlib.MAX_WBITS)
                except zlib.error:
                    # If decompression fails, maybe the decrypted data is already uncompressed
                    # Try to use it directly as JSON
                    try:
                        inflated = decrypted_no_padding
                        # Verify it's valid JSON
                        json.loads(inflated.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        # Re-raise the original zlib error if this doesn't work
                        raise

        return inflated.decode("utf-8")

    def create_bbox_around_point(self, point: GridPoint) -> dict[str, Any]:
        """Create bounding box parameters around grid point.

        Args:
            point: Grid point with latitude and longitude

        Returns:
            Dictionary of API parameters for bounding box search
        """
        # Approximately 50 miles radius
        # At 40° latitude: 1° lat ≈ 69 miles, 1° lon ≈ 53 miles
        lat_delta = 0.725  # degrees (~50 miles)
        lon_delta = 0.870  # degrees (~50 miles at 40° latitude)

        timestamp_ms = int(time.time() * 1000)

        return {
            "min_lat": point.latitude - lat_delta,
            "max_lat": point.latitude + lat_delta,
            "min_lon": point.longitude - lon_delta,
            "max_lon": point.longitude + lon_delta,
            "portal": 0,
            "_time": timestamp_ms,
        }

    async def search_bbox(self, bbox: dict[str, Any]) -> list[dict[str, Any]]:
        """Search for locations in bounding box.

        Args:
            bbox: Bounding box parameters

        Returns:
            List of location dictionaries

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_url}/portal/tags", params=bbox, headers=self.get_api_headers()
            )

            if response.status_code == 200:
                # Decrypt response using timestamp from request
                timestamp_str = str(bbox["_time"])
                decrypted_json = self.decrypt_response(response.content, timestamp_str)
                return json.loads(decrypted_json)
            else:
                logger.warning(
                    f"API returned {response.status_code} for bbox {bbox['min_lat']:.2f},{bbox['min_lon']:.2f}"
                )
                return []

    async def fetch_location_details(self, location_id: str) -> dict[str, Any] | None:
        """Fetch detailed information for a location.

        Args:
            location_id: Location ID

        Returns:
            Detailed location data or None if fetch fails
        """
        # The details page is at /details/{location_id}
        # We'll fetch the HTML and extract structured data
        # For now, we'll use the map data as is since it's quite complete

        # Note: The map data already includes most fields:
        # - id, name, latitude, longitude
        # - address1, address2, city, county, state, zip_code
        # - phone_number, email, url
        # - operating_days (JSON), operating_hours
        # - serviceArea, requirements, services1, languages
        # - contact_person, created, updated

        # If we need the details page, we can add that here
        # For now, returning None means we'll use map data only
        return None

    async def process_batch(self, coordinates: list[GridPoint]) -> None:
        """Process a batch of coordinates.

        Args:
            coordinates: List of coordinate points to process
        """
        for coord in coordinates:
            try:
                # Create bounding box around coordinate
                bbox = self.create_bbox_around_point(coord)

                # Search for locations
                locations = await self.search_bbox(bbox)

                if not locations:
                    continue

                logger.info(f"Found {len(locations)} locations at {coord.latitude:.2f},{coord.longitude:.2f}")

                # Process each location
                for location in locations:
                    loc_id = str(location.get("id", ""))

                    if not loc_id:
                        logger.warning("Location missing ID, skipping")
                        continue

                    # Store location data
                    self.location_data[loc_id] = location

                    # Only count if it's a new location
                    if loc_id not in self.unique_locations:
                        self.total_locations += 1
                        self.unique_locations.add(loc_id)
                        logger.info(
                            f"Found location {loc_id}: {location.get('name', 'Unknown')} "
                            f"(total: {self.total_locations}, unique: {len(self.unique_locations)})"
                        )

            except Exception as e:
                logger.error(f"Error processing coordinate {coord}: {e}", exc_info=True)
                continue

            # Delay between coordinates
            await asyncio.sleep(self.request_delay)

    async def scrape(self) -> str:
        """Scrape data from FoodFinder.us API.

        Returns:
            Summary of scraping results as JSON string
        """
        # Reset storage
        self.location_data = {}
        self.unique_locations = set()
        self.total_locations = 0

        # Get grid points for continental US
        coordinates = self.utils.get_us_grid_points(search_radius_miles=50)
        logger.info(f"Starting search with {len(coordinates)} coordinate points...")

        # In test mode, only process first 5 points
        if self.test_mode:
            coordinates = coordinates[:5]
            logger.info(f"TEST MODE: Limiting to {len(coordinates)} points")

        # Process coordinates in batches
        for i in range(0, len(coordinates), self.batch_size):
            batch = coordinates[i : i + self.batch_size]
            await self.process_batch(batch)

            # Log progress
            progress = min(100, round((i + self.batch_size) / len(coordinates) * 100))
            logger.info(f"\nProgress: {progress}% complete")
            logger.info("Current Stats:")
            logger.info(f"- Total locations found: {self.total_locations}")
            logger.info(f"- Unique locations: {len(self.unique_locations)}")

        # Now that we have all unique locations, submit them to the queue
        logger.info(f"\nSubmitting {len(self.unique_locations)} unique locations to queue...")

        for loc_id, location_data in self.location_data.items():
            if loc_id in self.unique_locations:
                job_id = self.submit_to_queue(json.dumps(location_data))
                logger.info(f"Queued job {job_id} for location {loc_id}")

        # Create summary
        summary = {
            "total_coordinates": len(coordinates),
            "total_locations_found": self.total_locations,
            "unique_locations": len(self.unique_locations),
            "source": self.api_url,
        }

        # Print summary to CLI
        print("\nSearch complete!")
        print("Final Stats:")
        print(f"- Coordinates searched: {len(coordinates)}")
        print(f"- Total locations processed: {self.total_locations}")
        print(f"- Unique locations found: {len(self.unique_locations)}")

        return json.dumps(summary)
