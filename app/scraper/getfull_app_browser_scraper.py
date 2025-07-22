"""Scraper for GetFull.app food pantry data using browser manipulation with parallel processing."""

import asyncio
import json
import logging

# ThreadPoolExecutor import removed - not used in current implementation
import math
import re
import threading
import time
from typing import Any

import httpx
from playwright.async_api import Page, async_playwright

# Configure root logger to only show ERROR level and above by default
root_logger = logging.getLogger()
root_logger.setLevel(logging.ERROR)

# Configure httpx logger to only show errors
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.ERROR)


# Custom filter to only allow specific progress messages and errors
class ProgressFilter(logging.Filter):
    def filter(self, record):
        # Always show ERROR and higher
        if record.levelno >= logging.ERROR:
            return True

        # Only show specific progress messages at INFO level
        if record.levelno == logging.INFO:
            msg = record.getMessage()
            # Allow overall progress updates
            if "OVERALL PROGRESS:" in msg or "OVERALL STATS:" in msg:
                return True
            # Allow worker progress percentage updates (only the percentage line)
            if "% complete" in msg and "Worker" in msg:
                return True
            # Allow distribution information
            if "Distributing " in msg and "coordinates from region" in msg:
                return True
            if "Total coordinates to process:" in msg:
                return True
            # Allow initialization and completion messages
            if "Starting parallel scrape" in msg:
                return True
            # Suppress all other INFO messages
            return False

        # Suppress DEBUG and WARNING messages
        return False


from app.models.geographic import GridPoint
from app.scraper.utils import ScraperJob, get_scraper_headers

# Configure our own logger with a custom filter
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # We'll control output with a filter
logger.addFilter(ProgressFilter())


class BrowserWorker:
    """Worker that handles a single browser instance for scraping."""

    def __init__(self, worker_id: int, scraper: "Getfull_App_BrowserScraper") -> None:
        """Initialize a browser worker.

        Args:
            worker_id: Unique identifier for this worker
            scraper: Reference to the parent scraper for accessing shared methods
        """
        self.worker_id = worker_id
        self.scraper = scraper
        self.playwright = None
        self.browser = None
        self.page: Page | None = None
        self.auth_token: str | None = None
        self.pantries_found = 0
        self.unique_pantries: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """Initialize browser and authenticate."""
        logger.info(f"Worker {self.worker_id}: Initializing browser")
        (
            self.playwright,
            self.browser,
            self.page,
        ) = await self.scraper.initialize_browser()
        if self.page is None:
            raise RuntimeError("Failed to initialize browser page")
        await self.scraper.navigate_to_map(self.page)
        self.auth_token = self.scraper.auth_token
        logger.info(f"Worker {self.worker_id}: Initialization complete")

    async def process_coordinates(self, coordinates: list[GridPoint]) -> dict[str, Any]:
        """Process a set of coordinates with this browser instance.

        Args:
            coordinates: List of coordinates to process

        Returns:
            Dictionary with worker results
        """
        logger.info(
            f"Worker {self.worker_id}: Processing {len(coordinates)} coordinates"
        )

        # Process coordinates in batches
        for i in range(0, len(coordinates), self.scraper.batch_size):
            batch = coordinates[i : i + self.scraper.batch_size]
            await self._process_batch(batch)

            # Log progress
            progress = min(
                100, round((i + self.scraper.batch_size) / len(coordinates) * 100)
            )
            logger.info(
                f"Worker {self.worker_id}: {progress}% complete, found {len(self.unique_pantries)} pantries"
            )

        return {
            "worker_id": self.worker_id,
            "total_pantries_found": self.pantries_found,
            "unique_pantries": len(self.unique_pantries),
            "pantry_ids": list(self.unique_pantries.keys()),
        }

    async def _process_batch(self, coordinates: list[GridPoint]) -> None:
        """Process a batch of coordinates.

        Args:
            coordinates: List of coordinate points to process
        """
        # Track pantries found in this batch
        batch_pantries: dict[str, dict[str, Any]] = {}

        for coord in coordinates:
            try:
                # Determine if this is a high-density region coordinate based on its name
                # We'll use the name to identify high-density regions since we can't add attributes to GridPoint
                is_high_density = "high density" in coord.name.lower()

                # Center the map at the coordinates with appropriate zoom level
                zoom_level = (
                    self.scraper.hd_zoom_level
                    if is_high_density
                    else self.scraper.default_zoom_level
                )
                if self.page is None:
                    raise RuntimeError("Browser page is not initialized")
                await self.scraper.center_map_at_coordinates(
                    self.page, coord.latitude, coord.longitude, zoom_level
                )

                # Extract pantries from the list view
                pantries = await self.scraper.extract_pantries_from_list(self.page)

                if not pantries:
                    logger.debug(
                        f"Worker {self.worker_id}: No pantries found at coordinates: {coord.latitude}, {coord.longitude}"
                    )
                    continue

                logger.debug(
                    f"Worker {self.worker_id}: Found {len(pantries)} pantries at coordinates: {coord.latitude}, {coord.longitude}"
                )

                # Process each pantry
                for pantry in pantries:
                    pantry_id = str(pantry.get("id", ""))

                    if not pantry_id:
                        continue

                    # Check if this pantry is already in the current batch
                    if pantry_id in batch_pantries:
                        continue

                    # Get detailed information if available
                    try:
                        if self.page is None:
                            raise RuntimeError("Browser page is not initialized")
                        detailed_pantry = await self.scraper.get_pantry_details(
                            self.page, pantry
                        )
                        if detailed_pantry:
                            pantry = detailed_pantry
                    except Exception as e:
                        logger.warning(
                            f"Worker {self.worker_id}: Could not get detailed information for pantry {pantry_id}: {e}"
                        )

                    # Add to batch_pantries
                    batch_pantries[pantry_id] = pantry
                    self.pantries_found += 1

                    # Check if we've seen this pantry before
                    if pantry_id not in self.unique_pantries:
                        self.unique_pantries[pantry_id] = pantry

                        # Only log every 5th pantry to reduce verbosity
                        if self.pantries_found % 5 == 0:
                            logger.info(
                                f"Worker {self.worker_id}: Found {self.pantries_found} pantries so far, {len(self.unique_pantries)} unique"
                            )

            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id}: Error processing coordinate {coord}: {e}"
                )
                continue

            # Delay between coordinates to avoid rate limiting
            await asyncio.sleep(self.scraper.request_delay)

        # Submit batch of pantries to the queue
        if batch_pantries:
            logger.info(
                f"Worker {self.worker_id}: Submitting pantries from this batch to queue..."
            )
            pantries_to_submit = 0
            pantries_already_processed = 0

            for pantry_id, pantry_data in batch_pantries.items():
                # Check if this pantry has already been processed by another worker
                if self.scraper.is_pantry_processed(pantry_id):
                    logger.debug(
                        f"Worker {self.worker_id}: Pantry {pantry_id} already processed by another worker, skipping"
                    )
                    pantries_already_processed += 1
                    continue

                # Transform to HSDS format
                hsds_data = self.scraper.transform_to_hsds(pantry_data)

                # Submit to queue
                try:
                    job_id = self.scraper.submit_to_queue(json.dumps(hsds_data))
                    # Handle both string and dictionary return types for job_id
                    if isinstance(job_id, dict) and "id" in job_id:
                        job_id_str = job_id["id"]
                    else:
                        job_id_str = str(job_id)
                    logger.info(
                        f"Worker {self.worker_id}: Queued job {job_id_str} for pantry {pantry_id}"
                    )
                    pantries_to_submit += 1
                except Exception as e:
                    logger.error(
                        f"Worker {self.worker_id}: Error submitting pantry {pantry_id} to queue: {e}"
                    )

            logger.info(
                f"Worker {self.worker_id}: Submitted {pantries_to_submit} pantries to queue, skipped {pantries_already_processed} already processed pantries"
            )

    async def cleanup(self) -> None:
        """Clean up browser resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info(f"Worker {self.worker_id}: Resources cleaned up")


class Getfull_App_BrowserScraper(ScraperJob):
    """Scraper for GetFull.app food pantry data using browser manipulation with parallel processing.

    This scraper uses Playwright to interact with the GetFull.app website
    and extract food pantry information by manipulating the map view.
    It centers the map at different coordinates with a high zoom level
    to extract pantry data from the list view.

    The scraper uses multiple browser instances in parallel to speed up the process.
    """

    # Default grid spacing constants
    GRID_LAT_STEP = 0.1  # Approximately 0.5-0.7km north-south
    GRID_LNG_STEP = 0.1  # Approximately 0.5-0.7km east-west (varies by latitude)

    # High-density region grid spacing constants
    HD_GRID_LAT_STEP = (
        0.01  # Finer grid for high-density regions (0.01 degrees ≈ 1.1km)
    )
    HD_GRID_LNG_STEP = 0.01  # Finer grid for high-density regions (varies by latitude)

    def __init__(
        self, scraper_id: str = "getfull_app_browser", num_workers: int = 12
    ) -> None:
        """Initialize scraper with ID 'getfull_app_browser' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'getfull_app_browser'
            num_workers: Number of parallel workers to use, defaults to 20
        """
        super().__init__(scraper_id=scraper_id)
        self.base_url = "https://getfull.app/food-finder"
        self.api_url = "https://api.getfull.app"
        self.default_zoom_level = 12  # Default zoom level for map view
        self.hd_zoom_level = 14  # Higher zoom level for high-density regions
        self.batch_size = 10  # Number of grid points to process in each batch
        self.request_delay = 0.1  # Delay between map movements to avoid rate limiting
        self.total_pantries = 0
        self.unique_pantries: set[str] = set()
        self.pantry_data: dict[str, dict[str, Any]] = {}
        self.auth_token: str | None = None
        self.num_workers = num_workers  # Number of parallel workers

        # Add a shared set for tracking processed pantry IDs across all workers
        self.processed_pantry_ids: set[str] = set()
        # Add a lock for thread-safe access to the shared set
        self.pantry_lock = threading.Lock()

    async def initialize_browser(self) -> tuple[Any, Any, Any]:
        """Initialize Playwright browser for web scraping.

        Returns:
            Tuple of (playwright, browser, page)
        """
        logger.info("Initializing browser...")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=get_scraper_headers()["User-Agent"],
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        return playwright, browser, page

    def is_pantry_processed(self, pantry_id: str) -> bool:
        """Check if a pantry has already been processed and mark it as processed if not.

        Args:
            pantry_id: ID of the pantry to check

        Returns:
            True if the pantry has already been processed, False otherwise
        """
        with self.pantry_lock:
            # Log the current state for debugging
            logger.debug(
                f"Checking if pantry {pantry_id} is already processed. Current processed count: {len(self.processed_pantry_ids)}"
            )

            if pantry_id in self.processed_pantry_ids:
                logger.debug(f"Pantry {pantry_id} is already processed, skipping")
                return True

            # Mark as processed and add to unique pantries set
            self.processed_pantry_ids.add(pantry_id)
            self.unique_pantries.add(pantry_id)
            logger.debug(
                f"Marked pantry {pantry_id} as processed. New processed count: {len(self.processed_pantry_ids)}"
            )
            return False

    async def navigate_to_map(self, page: Page) -> None:
        """Navigate to the food finder map page and extract authentication token.

        Args:
            page: Playwright page object
        """
        logger.info("Navigating to food finder map...")

        # Set up a request interceptor to capture the auth token
        token_holder = {"token": None}
        captured_endpoints = set()  # Track endpoints we've already logged

        async def capture_token(route, request):
            if "api.getfull.app" in request.url:
                headers = request.headers
                auth_header = headers.get("authorization", "")
                if auth_header and auth_header.startswith("Bearer "):
                    token_holder["token"] = auth_header.replace("Bearer ", "")

                    # Extract endpoint for logging purposes
                    endpoint = (
                        request.url.split("/api.getfull.app/")[1].split("?")[0]
                        if "/api.getfull.app/" in request.url
                        else request.url
                    )

                    # Only log the first time we capture a token from each endpoint
                    if endpoint not in captured_endpoints:
                        captured_endpoints.add(endpoint)
                        logger.info(f"Captured token from request to: {endpoint}")
            await route.continue_()

        # Start intercepting requests
        await page.route("**/*", capture_token)

        # Navigate to the main page
        await page.goto(self.base_url)
        await page.wait_for_load_state("networkidle")

        # Check if we're on the list view and navigate to it if not
        list_view_url = f"{self.base_url}/list"
        if not page.url.startswith(list_view_url):
            logger.info("Navigating to list view...")
            # Click on the list view button if available
            list_button = await page.query_selector('a[href*="/food-finder/list"]')
            if list_button:
                await list_button.click()
                await page.wait_for_load_state("networkidle")

        # Try multiple approaches to trigger API requests that might contain the token
        max_attempts = 3
        for attempt in range(max_attempts):
            if token_holder["token"]:
                break

            logger.info(f"Token capture attempt {attempt + 1}/{max_attempts}")

            # Approach 1: Search for locations to trigger API requests
            search_locations = [
                "New York, NY",
                "Los Angeles, CA",
                "Chicago, IL",
                "Houston, TX",
                "San Francisco, CA",
            ]

            # Try a different location each attempt
            location = search_locations[attempt % len(search_locations)]
            logger.info(f"Searching for location: {location}")

            try:
                # Look for the search input
                search_input = await page.query_selector(
                    'input[placeholder="your address"]'
                )
                if search_input:
                    # Clear any existing input
                    await page.evaluate(
                        'document.querySelector("input[placeholder=\'your address\']").value = ""'
                    )

                    # Enter the location and submit
                    await page.fill('input[placeholder="your address"]', location)
                    await page.press('input[placeholder="your address"]', "Enter")

                    # Wait for API requests to complete
                    await page.wait_for_load_state("networkidle")
                    # Longer wait to ensure API requests complete
                    await asyncio.sleep(5)
            except Exception as e:
                logger.warning(f"Error during search: {e}")

            # Approach 2: Interact with the map to trigger API requests
            if not token_holder["token"]:
                logger.info("Interacting with map to trigger API requests...")
                try:
                    # Click on the map to trigger API requests
                    map_element = await page.query_selector('div[role="application"]')
                    if map_element:
                        # Get the bounding box of the map
                        bbox = await map_element.bounding_box()
                        if bbox:
                            # Click at different positions on the map
                            for x_factor, y_factor in [
                                (0.25, 0.25),
                                (0.75, 0.75),
                                (0.5, 0.5),
                            ]:
                                x = bbox["x"] + bbox["width"] * x_factor
                                y = bbox["y"] + bbox["height"] * y_factor
                                await page.mouse.click(x, y)
                                await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"Error interacting with map: {e}")

            # Approach 3: Try to extract token from localStorage or sessionStorage
            if not token_holder["token"]:
                logger.info("Attempting to extract token from storage...")
                try:
                    token = await page.evaluate(
                        """
                        () => {
                            // Try various storage locations and key names
                            const storageKeys = [
                                'auth_token', 'token', 'authToken', 'access_token',
                                'accessToken', 'jwt', 'id_token', 'idToken'
                            ];

                            // Check localStorage
                            for (const key of storageKeys) {
                                const value = localStorage.getItem(key);
                                if (value) return value;
                            }

                            // Check sessionStorage
                            for (const key of storageKeys) {
                                const value = sessionStorage.getItem(key);
                                if (value) return value;
                            }

                            return null;
                        }
                    """
                    )

                    if token:
                        token_holder["token"] = token
                        logger.info("Extracted token from storage")
                except Exception as e:
                    logger.warning(f"Error extracting token from storage: {e}")

            # Approach 4: Use CDP session to monitor network
            if not token_holder["token"]:
                logger.info("Using CDP session to monitor network...")
                try:
                    client = await page.context.new_cdp_session(page)
                    await client.send("Network.enable")

                    # Set up event listener for request will be sent
                    async def on_request_will_be_sent(event):
                        request = event.get("request", {})
                        headers = request.get("headers", {})
                        auth_header = headers.get("Authorization", "")
                        if auth_header and auth_header.startswith("Bearer "):
                            token_holder["token"] = auth_header.replace("Bearer ", "")

                    client.on("Network.requestWillBeSent", on_request_will_be_sent)

                    # Refresh the page to trigger more requests
                    await page.reload()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.warning(f"Error using CDP session: {e}")

        # Store the token if found
        if token_holder["token"]:
            self.auth_token = token_holder["token"]
            logger.info("Successfully captured authentication token")
        else:
            # Use a fallback anonymous token
            self.auth_token = "anonymous_access_token"  # nosec B105
            logger.warning(
                "Could not capture authentication token, using anonymous token instead"
            )

        logger.info("Successfully navigated to food finder map")

    async def center_map_at_coordinates(
        self, page: Page, lat: float, lng: float, zoom_level: int = None
    ) -> None:
        """Center the map at the specified coordinates with the defined zoom level.

        Args:
            page: Playwright page object
            lat: Latitude
            lng: Longitude
            zoom_level: Optional zoom level to use, defaults to self.default_zoom_level
        """
        # Use provided zoom level or default
        if zoom_level is None:
            zoom_level = self.default_zoom_level

        # Construct the URL with the center coordinates and zoom level
        map_url = f"{self.base_url}/list/?center={lat}%2C{lng}&zoom={zoom_level}"

        logger.info(
            f"Centering map at coordinates: {lat}, {lng} with zoom level {zoom_level}"
        )

        # Navigate to the URL
        await page.goto(map_url)
        await page.wait_for_load_state("networkidle")

        # Wait a bit for the map to settle and pantries to load
        await asyncio.sleep(2)

    async def search_pantries_by_location(
        self, lat: float, lng: float, radius_miles: float = 50
    ) -> list[dict[str, Any]]:
        """Search for pantries using the geo search API endpoint.

        Args:
            lat: Latitude of search center
            lng: Longitude of search center
            radius_miles: Search radius in miles

        Returns:
            List of pantry data from API
        """
        if not self.auth_token:
            logger.warning("No auth token available for API search")
            return []

        # Convert radius to lat/lng offsets for bounding box
        # Rough approximation: 1 degree latitude = 69 miles
        # 1 degree longitude = cos(latitude) * 69 miles
        lat_offset = radius_miles / 69.0
        lng_offset = radius_miles / (math.cos(math.radians(lat)) * 69.0)

        # Create bounding box
        top_left = [lat + lat_offset, lng - lng_offset]
        bottom_right = [lat - lat_offset, lng + lng_offset]

        # Prepare the search request
        search_url = f"{self.api_url}/es/search/geo/pantries"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

        # Search payload with bounding box format
        payload = {
            "top_left": top_left,
            "bottom_right": bottom_right,
        }

        try:
            async with httpx.AsyncClient(headers=headers) as client:
                response = await client.post(
                    search_url, json=payload, timeout=60
                )
                response.raise_for_status()
                
                data = response.json()
                
                # The API returns a list directly
                if isinstance(data, list):
                    pantries = data
                else:
                    # Fallback to elasticsearch format if it's a dict
                    pantries = data.get("hits", {}).get("hits", [])
                
                logger.info(
                    f"Found {len(pantries)} pantries via geo search at {lat}, {lng} with radius {radius_miles} miles"
                )
                
                # Extract pantry data - check if it's already in the right format
                extracted_pantries = []
                for pantry in pantries:
                    if isinstance(pantry, dict):
                        # Check if it's in Elasticsearch format
                        if "_source" in pantry:
                            source = pantry.get("_source", {})
                            pantry_data = {
                                "id": pantry.get("_id", ""),
                                "name": source.get("name", ""),
                                "slug": source.get("slug", ""),
                                "description": source.get("description", ""),
                                "address": {
                                    "street": source.get("address", ""),
                                    "city": source.get("city", ""),
                                    "state": source.get("state", ""),
                                    "zip": source.get("zipCode", ""),
                                },
                                "latitude": source.get("location", {}).get("lat"),
                                "longitude": source.get("location", {}).get("lon"),
                                "phone": source.get("phone", ""),
                                "website": source.get("website", ""),
                                "email": source.get("email", ""),
                                "hours": source.get("hours", []),
                                "services": source.get("services", []),
                                "scheduleId": source.get("scheduleId"),
                                "isClosed": source.get("isClosed", False),
                            }
                        else:
                            # Direct format from API
                            pantry_data = {
                                "id": pantry.get("id", ""),
                                "name": pantry.get("name", ""),
                                "slug": pantry.get("slug", ""),
                                "description": pantry.get("description", ""),
                                "address": {
                                    "street": pantry.get("address", {}).get("street", ""),
                                    "city": pantry.get("address", {}).get("city", ""),
                                    "state": pantry.get("address", {}).get("state", ""),
                                    "zip": pantry.get("address", {}).get("zip", ""),
                                },
                                "latitude": pantry.get("latitude"),
                                "longitude": pantry.get("longitude"),
                                "phone": pantry.get("phone", ""),
                                "website": pantry.get("website", ""),
                                "email": pantry.get("email", ""),
                                "hours": pantry.get("hours", []),
                                "services": pantry.get("services", []),
                                "scheduleId": pantry.get("scheduleId"),
                                "isClosed": pantry.get("isClosed", False),
                            }
                        extracted_pantries.append(pantry_data)
                
                return extracted_pantries
                
        except httpx.HTTPError as e:
            logger.error(f"Error searching pantries via API: {e}")
            if hasattr(e, "response") and e.response:
                logger.error(f"Response: {e.response.text[:500]}")
        except Exception as e:
            logger.error(f"Unexpected error in geo search: {e}")
        
        return []

    async def extract_pantries_from_list(self, page: Page) -> list[dict[str, Any]]:
        """Extract pantry information from the list view.

        Args:
            page: Playwright page object

        Returns:
            List of pantry data dictionaries
        """
        logger.debug("Extracting pantries from list view...")

        # Check if any pantry cards exist
        has_pantries = await page.evaluate(
            """
            () => {
                return document.querySelectorAll('li[data-testid="food-finder-pantry-card"]').length > 0;
            }
        """
        )

        if not has_pantries:
            logger.debug("No pantry cards found in the list view")
            return []

        # Wait for pantry cards to be visible
        try:
            await page.wait_for_selector(
                'li[data-testid="food-finder-pantry-card"]',
                timeout=5000,
                state="visible",
            )
        except Exception as e:
            logger.warning(f"Timeout waiting for pantry cards: {e}")
            return []

        # Extract pantry data from the list
        pantries = await page.evaluate(
            """
            () => {
                const pantryCards = Array.from(document.querySelectorAll('li[data-testid="food-finder-pantry-card"]'));
                if (pantryCards.length === 0) return [];

                return pantryCards.map(card => {
                    // Extract pantry ID
                    const id = card.id || '';

                    // Extract pantry name
                    const nameElement = card.querySelector('h2');
                    const name = nameElement ? nameElement.textContent.trim() : '';

                    // Extract slug from "more info" button or any link
                    let slug = '';

                    // Try to find the "more info" button or any link that might contain the slug
                    const moreInfoButton = card.querySelector('a[href*="/food-finder/list/"]');
                    if (moreInfoButton) {
                        const href = moreInfoButton.getAttribute('href');
                        if (href) {
                            // Extract the slug from the URL
                            // URL format is typically: /food-finder/list/[slug]?center=...
                            const match = href.match(/\\/food-finder\\/list\\/([^?]+)/);
                            if (match && match[1]) {
                                slug = match[1];
                            }
                        }
                    }

                    // If we couldn't find a slug from links, try to find any element with data-slug attribute
                    if (!slug) {
                        const slugElement = card.querySelector('[data-slug]');
                        if (slugElement) {
                            slug = slugElement.getAttribute('data-slug');
                        }
                    }

                    // Extract address
                    const addressElements = Array.from(card.querySelectorAll('div')).filter(div =>
                        div.textContent && div.textContent.includes(',') &&
                        (div.textContent.includes('Street') || div.textContent.includes('Ave') ||
                         div.textContent.includes('Road') || div.textContent.includes('Dr') ||
                         div.textContent.includes('Blvd'))
                    );

                    let address = '';
                    let city = '';
                    let state = '';
                    let zip = '';

                    if (addressElements.length > 0) {
                        const addressText = addressElements[0].textContent.trim();
                        const addressParts = addressText.split(',');

                        if (addressParts.length >= 1) {
                            address = addressParts[0].trim();
                        }

                        if (addressParts.length >= 2) {
                            const cityStateZip = addressParts[1].trim().split(' ');
                            if (cityStateZip.length >= 1) {
                                city = cityStateZip[0];
                            }

                            if (cityStateZip.length >= 2) {
                                state = cityStateZip[1];
                            }

                            if (cityStateZip.length >= 3) {
                                zip = cityStateZip[2];
                            }
                        }
                    }

                    // Extract phone number
                    const phoneElements = Array.from(card.querySelectorAll('div')).filter(div =>
                        div.textContent && /\\(\\d{3}\\)\\s\\d{3}-\\d{4}/.test(div.textContent)
                    );

                    let phone = '';
                    if (phoneElements.length > 0) {
                        const phoneMatch = phoneElements[0].textContent.match(/\\(\\d{3}\\)\\s\\d{3}-\\d{4}/);
                        if (phoneMatch) {
                            phone = phoneMatch[0];
                        }
                    }

                    // Extract services
                    const serviceElements = Array.from(card.querySelectorAll('div')).filter(div =>
                        div.textContent && div.textContent.includes('•')
                    );

                    let services = [];
                    if (serviceElements.length > 0) {
                        services = serviceElements[0].textContent.split('•').map(s => s.trim()).filter(s => s);
                    }

                    return {
                        id: id || `getfull-${name.toLowerCase().replace(/\\s+/g, '-')}-${Math.random().toString(36).substring(2, 10)}`,
                        name,
                        slug: slug, // Add the extracted slug to the pantry data
                        address: {
                            street: address,
                            city,
                            state,
                            zip
                        },
                        phone,
                        services
                    };
                });
            }
        """
        )

        logger.debug(f"Found {len(pantries)} pantries in list view")
        return pantries

    async def get_pantry_details_api(self, pantry: dict[str, Any]) -> dict[str, Any]:
        """Get detailed information for a specific pantry using the API.

        Args:
            pantry: Basic pantry data

        Returns:
            Detailed pantry information
        """
        pantry_name = pantry.get("name", "")
        pantry_id = pantry.get("id", "")

        if not pantry_name or not self.auth_token:
            return pantry

        logger.debug(f"Getting API details for pantry: {pantry_name}")

        # Create a slug from the pantry name
        pantry_slug = (
            pantry_name.lower()
            .replace(" ", "-")
            .replace("'", "")
            .replace(".", "")
            .replace(",", "")
        )
        # Remove any special characters

        pantry_slug = re.sub(r"[^a-z0-9-]", "", pantry_slug)

        # Prepare headers
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
        }

        # Try to get pantry details using the slug
        details_url = f"{self.api_url}/pantry-api/pantries/{pantry_slug}"

        try:
            async with httpx.AsyncClient(headers=headers) as client:
                response = await client.get(details_url, timeout=60)

                if response.status_code == 200:
                    pantry_details = response.json()

                    # If we have a schedule ID, get schedule information
                    schedule_id = pantry_details.get("scheduleId")
                    if schedule_id:
                        try:
                            schedule_url = f"{self.api_url}/pantry-api/schedule/{schedule_id}/dropin"
                            schedule_response = await client.get(
                                schedule_url, timeout=30
                            )

                            if schedule_response.status_code == 200:
                                schedule_data = schedule_response.json()
                                # Add schedule data to pantry details
                                pantry_details["schedule"] = schedule_data
                        except Exception as e:
                            logger.warning(
                                f"Error getting schedule for pantry {pantry_id}: {e}"
                            )

                    # Merge the API data with the basic pantry data
                    pantry.update(pantry_details)
                    return pantry
                else:
                    # If slug doesn't work, try with the ID
                    alt_url = f"{self.api_url}/pantry-api/pantries/{pantry_id}"
                    alt_response = await client.get(alt_url, timeout=30)

                    if alt_response.status_code == 200:
                        pantry_details = alt_response.json()

                        # If we have a schedule ID, get schedule information
                        schedule_id = pantry_details.get("scheduleId")
                        if schedule_id:
                            try:
                                schedule_url = f"{self.api_url}/pantry-api/schedule/{schedule_id}/dropin"
                                schedule_response = await client.get(
                                    schedule_url, timeout=30
                                )

                                if schedule_response.status_code == 200:
                                    schedule_data = schedule_response.json()
                                    # Add schedule data to pantry details
                                    pantry_details["schedule"] = schedule_data
                            except Exception as e:
                                logger.warning(
                                    f"Error getting schedule for pantry {pantry_id}: {e}"
                                )

                        # Merge the API data with the basic pantry data
                        pantry.update(pantry_details)
                        return pantry
        except Exception as e:
            logger.warning(f"Error getting API details for pantry {pantry_name}: {e}")

        # If API fails, fall back to browser scraping
        return pantry

    async def get_pantry_details(
        self, page: Page, pantry: dict[str, Any]
    ) -> dict[str, Any]:
        """Get detailed information for a specific pantry using the API.

        Args:
            page: Playwright page object (not used, kept for compatibility)
            pantry: Basic pantry data

        Returns:
            Detailed pantry information
        """
        pantry_id = str(pantry.get("id", ""))

        if not pantry_id or not self.auth_token:
            return pantry

        logger.debug(f"Getting API details for pantry: {pantry.get('name', 'Unknown')}")

        # If we're using anonymous token, we might not be able to get detailed information
        if self.auth_token == "anonymous_access_token":  # nosec B105
            logger.debug(
                f"Using anonymous token, skipping detailed information for pantry {pantry_id}"
            )
            return pantry

        # Prepare headers
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
        }

        # Collect all possible slugs to try
        slugs_to_try = []

        # 1. If we have a slug from the pantry card, use that first
        if "slug" in pantry and pantry.get("slug"):
            slugs_to_try.append(pantry.get("slug"))

        # 2. Generate slugs from the name
        if "name" in pantry:
            name = pantry.get("name", "")

            # Standard slug format
            name_slug = (
                name.lower()
                .replace(" ", "-")
                .replace("'", "")
                .replace(".", "")
                .replace(",", "")
            )
            name_slug = name_slug.replace("&", "")
            import re

            name_slug = re.sub(r"[^a-z0-9-]", "", name_slug)
            while "--" in name_slug:
                name_slug = name_slug.replace("--", "-")
            name_slug = name_slug.strip("-")

            # Add the full name slug
            if name_slug and name_slug not in slugs_to_try:
                slugs_to_try.append(name_slug)

            # Add truncated versions (60 chars)
            if len(name_slug) > 60:
                truncated_slug = name_slug[:60]
                if truncated_slug not in slugs_to_try:
                    slugs_to_try.append(truncated_slug)

            # Add truncated versions at hyphen
            if len(name_slug) > 60:
                last_hyphen_pos = name_slug[:60].rfind("-")
                if last_hyphen_pos > 40:
                    truncated_at_hyphen = name_slug[:last_hyphen_pos]
                    if truncated_at_hyphen not in slugs_to_try:
                        slugs_to_try.append(truncated_at_hyphen)

            # Try "community-fridge" for any pantry with "Community Fridge" in the name
            if "community fridge" in name.lower():
                if "community-fridge" not in slugs_to_try:
                    slugs_to_try.append("community-fridge")

        # 3. Add the ID as a fallback
        if pantry_id not in slugs_to_try:
            slugs_to_try.append(pantry_id)

        logger.debug(f"Trying the following slugs for API request: {slugs_to_try}")

        # Try each slug in order
        pantry_details = {}
        success = False

        async with httpx.AsyncClient(headers=headers) as client:
            for slug in slugs_to_try:
                details_url = f"{self.api_url}/pantry-api/pantries/{slug}"
                try:
                    logger.debug(f"Trying API request with slug: {slug}")
                    response = await client.get(details_url, timeout=30)
                    response.raise_for_status()
                    pantry_details = response.json()
                    logger.debug(
                        f"Successfully retrieved pantry details using slug: {slug}"
                    )
                    success = True
                    break  # Exit the loop if successful
                except httpx.HTTPError as e:
                    if (
                        hasattr(e, "response")
                        and e.response
                        and e.response.status_code == 404
                    ):
                        logger.warning(f"Pantry not found with slug: {slug}")
                    else:
                        logger.warning(
                            f"HTTP error when getting pantry details with slug {slug}: {e}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Error getting pantry details with slug {slug}: {e}"
                    )

        # If none of the slugs worked, return the original pantry data
        if not success:
            logger.warning(
                f"Could not retrieve details for pantry {pantry_id} with any slug"
            )
            return pantry

        # If we have a schedule ID, get schedule information
        schedule_id = pantry_details.get("scheduleId")
        if schedule_id:
            try:
                schedule_url = (
                    f"{self.api_url}/pantry-api/schedule/{schedule_id}/dropin"
                )
                async with httpx.AsyncClient(headers=headers) as client:
                    response = await client.get(schedule_url, timeout=30)
                    if response.status_code == 200:
                        schedule_data = response.json()
                        # Add schedule data to pantry details
                        pantry_details["schedule"] = schedule_data
            except Exception as e:
                logger.warning(f"Error getting schedule for pantry {pantry_id}: {e}")

        # Merge the detailed info with the basic pantry data
        pantry.update(pantry_details)
        return pantry

    def transform_to_hsds(self, pantry: dict[str, Any]) -> dict[str, Any]:
        """Transform pantry data to HSDS format.

        Args:
            pantry: Pantry data from website

        Returns:
            Pantry data in HSDS format
        """
        try:
            # Ensure pantry is a dictionary
            if not isinstance(pantry, dict):
                logger.error(f"Expected pantry to be a dictionary, got {type(pantry)}")
                # Create a minimal valid HSDS record
                return {
                    "id": f"error-{time.time()}",
                    "name": "Error: Invalid pantry data",
                    "status": "inactive",
                    "address": {
                        "address_1": "",
                        "address_2": "",
                        "city": "",
                        "state_province": "",
                        "postal_code": "",
                        "country": "US",
                    },
                }

            # Extract basic information
            pantry_id = str(pantry.get("id", ""))
            name = pantry.get("name", "")
            description = pantry.get("description", "")

            # Extract address components
            address = pantry.get("address", {})
            # Ensure address is a dictionary
            if not isinstance(address, dict):
                logger.warning(
                    f"Address is not a dictionary for pantry {pantry_id}, using empty address"
                )
                address = {}

            address1 = address.get("street", "")
            city = address.get("city", "")
            state = address.get("state", "")
            postal_code = address.get("zip", "")

            # Extract contact information
            phone = pantry.get("phone", "")
            website = pantry.get("website", "")
            email = pantry.get("email", "")

            # Extract coordinates
            location = {}
            lat = pantry.get("latitude")
            lng = pantry.get("longitude")

            if lat is not None and lng is not None:
                location = {"latitude": lat, "longitude": lng}

            # Extract hours of operation
            regular_schedule = []

            # Check for schedule data in different formats
            hours = pantry.get("hours")
            if hours is not None:
                # Case 1: hours is a list (most common)
                if isinstance(hours, list):
                    for hour in hours:
                        if isinstance(hour, dict):
                            day = hour.get("day", "")
                            open_time = hour.get("open", "")
                            close_time = hour.get("close", "")

                            if day and open_time and close_time:
                                regular_schedule.append(
                                    {
                                        "weekday": day,
                                        "opens_at": open_time,
                                        "closes_at": close_time,
                                    }
                                )
                # Case 2: hours is a dictionary (common in API responses)
                elif isinstance(hours, dict):
                    logger.debug(
                        f"Hours for pantry {pantry_id} is in dictionary format"
                    )
                    # Try to extract days of the week from the dictionary
                    for day_key in [
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                    ]:
                        day_data = hours.get(day_key)
                        if day_data and isinstance(day_data, dict):
                            is_open = day_data.get("isOpen", False)
                            if is_open:
                                open_time = day_data.get("open", "")
                                close_time = day_data.get("close", "")

                                if open_time and close_time:
                                    # Capitalize first letter of day
                                    day_name = day_key.capitalize()
                                    regular_schedule.append(
                                        {
                                            "weekday": day_name,
                                            "opens_at": open_time,
                                            "closes_at": close_time,
                                        }
                                    )
                # Case 3: hours might be in a different format (e.g., string or other object)
                else:
                    logger.debug(
                        f"Hours for pantry {pantry_id} is not in the expected format: {type(hours)}"
                    )
                    # Try to extract schedule from the "schedule" field if available
                    schedule_data = pantry.get("schedule")
                    if schedule_data:
                        logger.debug(
                            f"Found schedule data for pantry {pantry_id}, attempting to extract hours"
                        )
                        # The schedule data structure might vary, so we need to handle different formats
                        if isinstance(schedule_data, dict):
                            # Try to extract dropin schedule
                            dropin = schedule_data.get("dropin")
                            if isinstance(dropin, list):
                                for slot in dropin:
                                    if isinstance(slot, dict):
                                        day = slot.get("day", "")
                                        start_time = slot.get("startTime", "")
                                        end_time = slot.get("endTime", "")

                                        if day and start_time and end_time:
                                            regular_schedule.append(
                                                {
                                                    "weekday": day,
                                                    "opens_at": start_time,
                                                    "closes_at": end_time,
                                                }
                                            )

            # If we couldn't extract any schedule information, check if the pantry is marked as closed
            if not regular_schedule:
                is_closed = pantry.get("isClosed", False)
                if is_closed:
                    logger.debug(
                        f"Pantry {pantry_id} is marked as closed, no schedule available"
                    )
                else:
                    logger.warning(
                        f"Could not extract schedule information for pantry {pantry_id}"
                    )

            # Extract services with better error handling
            service_attributes = []

            # Try different service fields that might be present
            services = pantry.get("services")
            if services is not None:
                # Case 1: services is a list (most common)
                if isinstance(services, list):
                    for service in services:
                        if service:
                            service_attributes.append(
                                {
                                    "attribute_key": "service_type",
                                    "attribute_value": str(
                                        service
                                    ),  # Ensure service is a string
                                }
                            )
                # Case 2: services might be in a different format
                else:
                    logger.debug(
                        f"Services for pantry {pantry_id} is not in the expected list format: {type(services)}"
                    )

                    # If it's a string, try to split it
                    if isinstance(services, str):
                        service_list = [
                            s.strip() for s in services.split(",") if s.strip()
                        ]
                        for service in service_list:
                            service_attributes.append(
                                {
                                    "attribute_key": "service_type",
                                    "attribute_value": service,
                                }
                            )
                    # If it's a dictionary, try to extract values
                    elif isinstance(services, dict):
                        for key, value in services.items():
                            if value:
                                service_attributes.append(
                                    {
                                        "attribute_key": key,
                                        "attribute_value": str(value),
                                    }
                                )

            # Check for additional service information in other fields
            service_types = pantry.get("serviceTypes")
            if isinstance(service_types, list):
                for service_type in service_types:
                    if service_type:
                        service_attributes.append(
                            {
                                "attribute_key": "service_type",
                                "attribute_value": str(service_type),
                            }
                        )

            # Construct HSDS data
            hsds_data = {
                "id": pantry_id,
                "name": name,
                "alternate_name": "",
                "description": description,
                "email": email,
                "url": website,
                "status": "active",
                "address": {
                    "address_1": address1,
                    "address_2": "",
                    "city": city,
                    "state_province": state,
                    "postal_code": postal_code,
                    "country": "US",
                },
                "phones": [{"number": phone, "type": "voice"}] if phone else [],
                "location": location,
                "regular_schedule": regular_schedule,
            }

            if service_attributes:
                hsds_data["service_attributes"] = service_attributes

            return hsds_data

        except Exception as e:
            logger.error(f"Error transforming pantry to HSDS format: {e}")
            # Return a minimal valid HSDS record in case of error
            return {
                "id": f"error-{time.time()}",
                "name": f"Error: {e!s}",
                "status": "inactive",
                "address": {
                    "address_1": "",
                    "address_2": "",
                    "city": "",
                    "state_province": "",
                    "postal_code": "",
                    "country": "US",
                },
            }

    async def process_batch(self, page: Page, coordinates: list[GridPoint]) -> None:
        """Process a batch of coordinates.

        Args:
            page: Playwright page object
            coordinates: List of coordinate points to process
        """
        # Track pantries found in this batch (to avoid duplicates within the batch)
        batch_pantries: dict[str, dict[str, Any]] = {}
        # Track pantries already seen in previous batches (for logging purposes only)
        previously_seen_pantries: set[str] = set()

        for coord in coordinates:
            try:
                # Center the map at the coordinates
                await self.center_map_at_coordinates(
                    page, coord.latitude, coord.longitude
                )

                # Extract pantries from the list view
                pantries = await self.extract_pantries_from_list(page)

                if not pantries:
                    logger.debug(
                        f"No pantries found at coordinates: {coord.latitude}, {coord.longitude}"
                    )
                    continue

                logger.debug(
                    f"Found {len(pantries)} pantries at coordinates: {coord.latitude}, {coord.longitude}"
                )

                # Process each pantry
                for pantry in pantries:
                    pantry_id = str(pantry.get("id", ""))

                    if not pantry_id:
                        continue

                    # Check if this pantry is already in the current batch
                    if pantry_id in batch_pantries:
                        logger.debug(
                            f"Pantry {pantry_id} already in current batch, skipping"
                        )
                        continue

                    # Get detailed information if available
                    try:
                        detailed_pantry = await self.get_pantry_details(page, pantry)
                        if detailed_pantry:
                            pantry = detailed_pantry
                    except Exception as e:
                        logger.warning(
                            f"Could not get detailed information for pantry {pantry_id}: {e}"
                        )

                    # Add to batch_pantries (one per coordinate pair within a batch)
                    batch_pantries[pantry_id] = pantry

                    # Check if we've seen this pantry in a previous batch
                    if pantry_id in self.unique_pantries:
                        previously_seen_pantries.add(pantry_id)
                    else:
                        # This is a completely new pantry
                        self.pantry_data[pantry_id] = pantry
                        self.unique_pantries.add(pantry_id)
                        self.total_pantries += 1

                        logger.info(
                            f"Found new pantry {pantry_id}: {pantry.get('name', 'Unknown')} "
                            f"(total: {self.total_pantries}, unique: {len(self.unique_pantries)})"
                        )

            except Exception as e:
                logger.error(f"Error processing coordinate {coord}: {e}")
                continue

            # Delay between coordinates to avoid rate limiting
            await asyncio.sleep(self.request_delay)

        # Log statistics about this batch
        new_in_batch = len(batch_pantries) - len(previously_seen_pantries)
        logger.info(f"Batch summary: {len(batch_pantries)} total pantries in batch")
        logger.info(f"- {new_in_batch} new pantries")
        logger.info(f"- {len(previously_seen_pantries)} previously seen pantries")

        # Submit batch of pantries to the queue
        if batch_pantries:
            logger.info("Submitting pantries from this batch to queue...")
            pantries_to_submit = 0
            pantries_already_processed = 0

            for pantry_id, pantry_data in batch_pantries.items():
                # Check if this pantry has already been processed by another worker
                if self.is_pantry_processed(pantry_id):
                    logger.debug(
                        f"Pantry {pantry_id} already processed by another worker, skipping"
                    )
                    pantries_already_processed += 1
                    continue

                # Transform to HSDS format
                hsds_data = self.transform_to_hsds(pantry_data)

                # Submit to queue
                try:
                    job_id = self.submit_to_queue(json.dumps(hsds_data))
                    # Handle both string and dictionary return types for job_id
                    if isinstance(job_id, dict) and "id" in job_id:
                        job_id_str = job_id["id"]
                    else:
                        job_id_str = str(job_id)
                    logger.info(f"Queued job {job_id_str} for pantry {pantry_id}")
                    pantries_to_submit += 1
                except Exception as e:
                    logger.error(f"Error submitting pantry {pantry_id} to queue: {e}")

            logger.info(
                f"Submitted {pantries_to_submit} pantries to queue, skipped {pantries_already_processed} already processed pantries"
            )

    def _prepare_regional_coordinate_sets(self) -> dict[str, list[GridPoint]]:
        """Prepare coordinate sets grouped by region priority."""

        # Get base coordinates for the US
        base_coordinates = self.utils.get_us_grid_points()

        # Define known populated areas by region and importance
        # 1. East Coast US (highest priority)
        east_coast_major = [
            GridPoint(latitude=40.7128, longitude=-74.0060, name="New York City"),
            GridPoint(latitude=38.9072, longitude=-77.0369, name="Washington DC"),
            GridPoint(latitude=42.3601, longitude=-71.0589, name="Boston"),
            GridPoint(latitude=39.9526, longitude=-75.1652, name="Philadelphia"),
            GridPoint(latitude=39.2904, longitude=-76.6122, name="Baltimore"),
        ]

        east_coast_secondary = [
            GridPoint(latitude=25.7617, longitude=-80.1918, name="Miami"),
            GridPoint(latitude=33.7490, longitude=-84.3880, name="Atlanta"),
            GridPoint(latitude=35.2271, longitude=-80.8431, name="Charlotte"),
            GridPoint(latitude=37.5407, longitude=-77.4360, name="Richmond"),
            GridPoint(latitude=40.4406, longitude=-79.9959, name="Pittsburgh"),
            GridPoint(latitude=40.7357, longitude=-74.1724, name="Newark"),
            GridPoint(latitude=40.7282, longitude=-74.0776, name="Jersey City"),
            GridPoint(latitude=41.8240, longitude=-71.4128, name="Providence"),
        ]

        east_coast_smaller = [
            GridPoint(latitude=35.7796, longitude=-78.6382, name="Raleigh"),
            GridPoint(latitude=36.8508, longitude=-76.2859, name="Norfolk"),
            GridPoint(latitude=30.3322, longitude=-81.6557, name="Jacksonville"),
            GridPoint(latitude=27.9506, longitude=-82.4572, name="Tampa"),
            GridPoint(latitude=28.5383, longitude=-81.3792, name="Orlando"),
            GridPoint(latitude=32.7765, longitude=-79.9311, name="Charleston"),
            GridPoint(latitude=32.0809, longitude=-81.0912, name="Savannah"),
            GridPoint(latitude=43.6591, longitude=-70.2568, name="Portland, ME"),
        ]

        # 2. West Coast US (second priority)
        west_coast_major = [
            GridPoint(latitude=34.0522, longitude=-118.2437, name="Los Angeles"),
            GridPoint(latitude=37.7749, longitude=-122.4194, name="San Francisco"),
            GridPoint(latitude=47.6062, longitude=-122.3321, name="Seattle"),
        ]

        west_coast_secondary = [
            GridPoint(latitude=32.7157, longitude=-117.1611, name="San Diego"),
            GridPoint(latitude=45.5152, longitude=-122.6784, name="Portland, OR"),
            GridPoint(latitude=38.5816, longitude=-121.4944, name="Sacramento"),
            GridPoint(latitude=37.3382, longitude=-121.8863, name="San Jose"),
            GridPoint(latitude=37.8044, longitude=-122.2712, name="Oakland"),
            GridPoint(latitude=47.2529, longitude=-122.4443, name="Tacoma"),
        ]

        west_coast_smaller = [
            GridPoint(latitude=36.7378, longitude=-119.7871, name="Fresno"),
            GridPoint(latitude=35.3733, longitude=-119.0187, name="Bakersfield"),
            GridPoint(latitude=44.0521, longitude=-123.0868, name="Eugene"),
            GridPoint(latitude=34.4208, longitude=-119.6982, name="Santa Barbara"),
            GridPoint(latitude=47.0379, longitude=-122.9007, name="Olympia"),
            GridPoint(latitude=47.6588, longitude=-117.4260, name="Spokane"),
        ]

        # 3. Colorado (third priority)
        colorado_major = [
            GridPoint(latitude=39.7392, longitude=-104.9903, name="Denver")
        ]

        colorado_secondary = [
            GridPoint(latitude=38.8339, longitude=-104.8214, name="Colorado Springs"),
            GridPoint(latitude=40.5853, longitude=-105.0844, name="Fort Collins"),
            GridPoint(latitude=40.0150, longitude=-105.2705, name="Boulder"),
            GridPoint(latitude=39.7294, longitude=-104.8319, name="Aurora"),
        ]

        colorado_smaller = [
            GridPoint(latitude=39.0639, longitude=-108.5506, name="Grand Junction"),
            GridPoint(latitude=38.2544, longitude=-104.6091, name="Pueblo"),
            GridPoint(latitude=40.4233, longitude=-104.7091, name="Greeley"),
            GridPoint(latitude=37.2753, longitude=-107.8801, name="Durango"),
        ]

        # 4. Rest of the US (lowest priority)
        other_major = [
            GridPoint(latitude=41.8781, longitude=-87.6298, name="Chicago"),
            GridPoint(latitude=29.7604, longitude=-95.3698, name="Houston"),
            GridPoint(latitude=33.4484, longitude=-112.0740, name="Phoenix"),
            GridPoint(latitude=32.7767, longitude=-96.7970, name="Dallas"),
            GridPoint(latitude=44.9778, longitude=-93.2650, name="Minneapolis"),
            GridPoint(latitude=42.3314, longitude=-83.0458, name="Detroit"),
            GridPoint(latitude=38.6270, longitude=-90.1994, name="St. Louis"),
            GridPoint(latitude=41.4993, longitude=-81.6944, name="Cleveland"),
            GridPoint(latitude=36.1699, longitude=-115.1398, name="Las Vegas"),
            GridPoint(latitude=36.1627, longitude=-86.7816, name="Nashville"),
            GridPoint(latitude=43.0389, longitude=-87.9065, name="Milwaukee"),
            GridPoint(latitude=29.4241, longitude=-98.4936, name="San Antonio"),
        ]

        # Create region sets with different grid densities based on population density
        region_sets = {
            # Priority 1: East Coast major cities (highest priority) - high density scanning
            "east_coast_major": self._create_region_grid(
                east_coast_major, radius_miles=15.0, high_density=False
            ),
            # Priority 2: East Coast secondary cities
            "east_coast_secondary": self._create_region_grid(
                east_coast_secondary, radius_miles=15.0
            ),
            # Priority 3: East Coast smaller cities
            "east_coast_smaller": self._create_region_grid(
                east_coast_smaller, radius_miles=15.0
            ),
            # Priority 4: West Coast major cities - high density scanning
            "west_coast_major": self._create_region_grid(
                west_coast_major, radius_miles=15.0, high_density=False
            ),
            # Priority 5: West Coast secondary cities
            "west_coast_secondary": self._create_region_grid(
                west_coast_secondary, radius_miles=15.0
            ),
            # Priority 6: West Coast smaller cities
            "west_coast_smaller": self._create_region_grid(
                west_coast_smaller, radius_miles=15.0
            ),
            # Priority 7: Colorado major cities - high density scanning
            "colorado_major": self._create_region_grid(
                colorado_major, radius_miles=15.0, high_density=False
            ),
            # Priority 8: Colorado secondary cities
            "colorado_secondary": self._create_region_grid(
                colorado_secondary, radius_miles=15.0
            ),
            # Priority 9: Colorado smaller cities
            "colorado_smaller": self._create_region_grid(
                colorado_smaller, radius_miles=15.0
            ),
            # Priority 10: Other major US cities - high density scanning for major population centers
            "other_major": self._create_region_grid(
                other_major, radius_miles=15.0, high_density=False
            ),
        }

        # Create general grid for the rest of the US
        general_grid = self._create_general_grid(base_coordinates)

        # Ensure we don't duplicate coordinates already in priority regions
        all_region_coords: set[tuple[float, float]] = set()
        for coords in region_sets.values():
            all_region_coords.update((c.latitude, c.longitude) for c in coords)

        # Filter out duplicates from general grid
        filtered_general_grid = [
            coord
            for coord in general_grid
            if (coord.latitude, coord.longitude) not in all_region_coords
        ]

        region_sets["general_grid"] = filtered_general_grid

        return region_sets

    def _create_region_grid(
        self,
        base_points: list[GridPoint],
        radius_miles: float = 10.0,
        high_density: bool = False,
    ) -> list[GridPoint]:
        """Create a uniform grid around base points with consistent spacing.

        Args:
            base_points: Central points for grid generation
            radius_miles: Radius around each point to create grid (miles)
            high_density: Whether to use high-density grid spacing

        Returns:
            List of grid points with uniform density
        """
        grid_points = []

        # Use high-density grid spacing if specified
        lat_step = self.HD_GRID_LAT_STEP if high_density else self.GRID_LAT_STEP
        lng_step = self.HD_GRID_LNG_STEP if high_density else self.GRID_LNG_STEP

        for base_point in base_points:
            # Calculate how many steps we need for the specified radius
            # 1 degree of latitude is approximately 69 miles
            lat_steps = math.ceil(radius_miles / 69.0 / lat_step)
            # 1 degree of longitude varies by latitude, approximately cos(lat) * 69 miles
            lng_miles_per_degree = math.cos(math.radians(base_point.latitude)) * 69.0
            lng_steps = math.ceil(radius_miles / lng_miles_per_degree / lng_step)

            # Generate grid points in a rectangular grid around the base point
            for lat_offset_steps in range(-lat_steps, lat_steps + 1):
                for lng_offset_steps in range(-lng_steps, lng_steps + 1):
                    lat_offset = lat_offset_steps * lat_step
                    lng_offset = lng_offset_steps * lng_step

                    new_lat = round(base_point.latitude + lat_offset, 6)
                    new_lng = round(base_point.longitude + lng_offset, 6)

                    # Skip points that are too far from the base point (create circular coverage)
                    lat_miles = lat_offset * 69.0
                    lng_miles = lng_offset * lng_miles_per_degree
                    distance = math.sqrt(lat_miles**2 + lng_miles**2)

                    if distance <= radius_miles:
                        # Include "high density" in the name for high-density regions
                        name_suffix = " (high density)" if high_density else ""
                        grid_point = GridPoint(
                            latitude=new_lat,
                            longitude=new_lng,
                            name=f"Grid Point near {base_point.name}{name_suffix}",
                        )
                        grid_points.append(grid_point)

        return grid_points

    def _create_general_grid(
        self, base_coordinates: list[GridPoint]
    ) -> list[GridPoint]:
        """Create a general grid for the US with same density as priority regions.

        Args:
            base_coordinates: Base points from the standard grid

        Returns:
            List of grid points with uniform density
        """
        # Use the same grid creation logic as priority regions, but with smaller radius
        # to ensure more even coverage across the country
        return self._create_region_grid(base_coordinates, radius_miles=5.0)

    def _distribute_coordinates(
        self, regional_coordinates: dict[str, list[GridPoint]]
    ) -> list[list[GridPoint]]:
        """Distribute coordinates among workers, assigning entire regions when possible.

        This method distributes coordinates to workers in a way that:
        1. Assigns entire regions to workers when possible
        2. Minimizes overlap between workers
        3. Ensures each worker gets a roughly equal number of points
        """
        worker_coordinate_sets: list[list[GridPoint]] = [
            [] for _ in range(self.num_workers)
        ]

        # Define region priority order (high-density regions first)
        region_priority = [
            "east_coast_major",  # High density
            "west_coast_major",  # High density
            "colorado_major",  # High density
            "other_major",  # High density
            "east_coast_secondary",
            "west_coast_secondary",
            "colorado_secondary",
            "east_coast_smaller",
            "west_coast_smaller",
            "colorado_smaller",
            "general_grid",  # Lowest priority
        ]

        # Calculate target points per worker
        total_points = sum(len(coords) for coords in regional_coordinates.values())
        target_points_per_worker = total_points // self.num_workers
        logger.info(
            f"Total coordinates: {total_points}, target per worker: {target_points_per_worker}"
        )

        # Track current worker index
        current_worker = 0

        # Process regions in priority order
        for region_name in region_priority:
            if region_name not in regional_coordinates:
                continue

            coords = regional_coordinates[region_name]
            logger.info(
                f"Distributing {len(coords)} coordinates from region '{region_name}'"
            )

            # If this region fits in one worker and doesn't exceed target, assign it whole
            if (
                len(coords) <= target_points_per_worker * 1.5
                and current_worker < self.num_workers
            ):
                logger.info(
                    f"Assigning entire region '{region_name}' to worker {current_worker}"
                )
                worker_coordinate_sets[current_worker].extend(coords)
                current_worker += 1

                # If we've used all workers, reset to the first one
                if current_worker >= self.num_workers:
                    current_worker = 0
            else:
                # Region is too large for one worker, divide it geographically
                # Sort by latitude and longitude to keep nearby points together
                coords.sort(key=lambda c: (c.latitude, c.longitude))

                # Calculate how many workers needed for this region
                workers_needed = max(
                    1, min(self.num_workers, len(coords) // target_points_per_worker)
                )
                points_per_worker_this_region = len(coords) // workers_needed

                logger.info(
                    f"Splitting region '{region_name}' among {workers_needed} workers"
                )

                # Distribute in chunks
                for i in range(workers_needed):
                    start_idx = i * points_per_worker_this_region
                    end_idx = (
                        start_idx + points_per_worker_this_region
                        if i < workers_needed - 1
                        else len(coords)
                    )

                    # Assign this chunk to the current worker
                    worker_coordinate_sets[current_worker].extend(
                        coords[start_idx:end_idx]
                    )

                    # Move to next worker
                    current_worker += 1
                    if current_worker >= self.num_workers:
                        current_worker = 0

        # Balance any remaining discrepancies
        self._balance_worker_loads(worker_coordinate_sets)

        # Log the distribution
        coord_counts = [len(coords) for coords in worker_coordinate_sets]
        logger.info(f"Final coordinate distribution among workers: {coord_counts}")
        logger.info(f"Total coordinates distributed: {sum(coord_counts)}")

        return worker_coordinate_sets

    def _balance_worker_loads(
        self, worker_coordinate_sets: list[list[GridPoint]]
    ) -> None:
        """Balance the workload among workers if there are significant discrepancies."""
        # Calculate average load
        total_coords = sum(len(coords) for coords in worker_coordinate_sets)
        avg_coords = total_coords // len(worker_coordinate_sets)

        # Find overloaded and underloaded workers
        overloaded = [
            (i, coords)
            for i, coords in enumerate(worker_coordinate_sets)
            if len(coords) > avg_coords * 1.2
        ]
        underloaded = [
            (i, coords)
            for i, coords in enumerate(worker_coordinate_sets)
            if len(coords) < avg_coords * 0.8
        ]

        if not overloaded or not underloaded:
            return  # No significant imbalance

        logger.info(f"Balancing worker loads. Average: {avg_coords}")

        # Move coordinates from overloaded to underloaded workers
        for under_idx, under_coords in underloaded:
            if not overloaded:
                break

            over_idx, over_coords = overloaded[0]

            # Calculate how many points to move
            deficit = avg_coords - len(under_coords)
            excess = len(over_coords) - avg_coords
            to_move = min(deficit, excess)

            if to_move <= 0:
                continue

            # Move points (take from the end to keep geographic proximity)
            points_to_move = over_coords[-to_move:]
            worker_coordinate_sets[under_idx].extend(points_to_move)
            worker_coordinate_sets[over_idx] = over_coords[:-to_move]

            # Check if this worker is still overloaded
            if len(worker_coordinate_sets[over_idx]) <= avg_coords * 1.2:
                overloaded.pop(0)
            else:
                # Update the overloaded entry
                overloaded[0] = (over_idx, worker_coordinate_sets[over_idx])

    async def geo_search_scrape(self) -> dict[str, Any]:
        """Scrape data using the geo search API with overlapping circles.

        Returns:
            Dictionary with scraping results
        """
        logger.info("Starting geo search scrape using API endpoint")
        
        # Initialize a single browser to get auth token
        playwright, browser, page = await self.initialize_browser()
        try:
            await self.navigate_to_map(page)
            
            if not self.auth_token or self.auth_token == "anonymous_access_token":
                logger.error("Failed to obtain valid auth token")
                return {
                    "error": "Authentication failed",
                    "total_pantries_found": 0,
                    "unique_pantries": 0,
                }
            
            # Define major search centers across the US with appropriate radii
            search_centers = [
                # Northeast
                {"lat": 40.7128, "lng": -74.0060, "radius": 50, "name": "New York City"},
                {"lat": 42.3601, "lng": -71.0589, "radius": 50, "name": "Boston"},
                {"lat": 39.9526, "lng": -75.1652, "radius": 50, "name": "Philadelphia"},
                {"lat": 38.9072, "lng": -77.0369, "radius": 50, "name": "Washington DC"},
                {"lat": 39.2904, "lng": -76.6122, "radius": 40, "name": "Baltimore"},
                {"lat": 40.4406, "lng": -79.9959, "radius": 40, "name": "Pittsburgh"},
                {"lat": 41.8240, "lng": -71.4128, "radius": 30, "name": "Providence"},
                {"lat": 43.0481, "lng": -76.1474, "radius": 40, "name": "Syracuse"},
                {"lat": 42.8864, "lng": -78.8784, "radius": 40, "name": "Buffalo"},
                
                # Southeast
                {"lat": 33.7490, "lng": -84.3880, "radius": 50, "name": "Atlanta"},
                {"lat": 25.7617, "lng": -80.1918, "radius": 50, "name": "Miami"},
                {"lat": 27.9506, "lng": -82.4572, "radius": 40, "name": "Tampa"},
                {"lat": 28.5383, "lng": -81.3792, "radius": 40, "name": "Orlando"},
                {"lat": 30.3322, "lng": -81.6557, "radius": 40, "name": "Jacksonville"},
                {"lat": 35.2271, "lng": -80.8431, "radius": 40, "name": "Charlotte"},
                {"lat": 35.7796, "lng": -78.6382, "radius": 40, "name": "Raleigh"},
                {"lat": 37.5407, "lng": -77.4360, "radius": 30, "name": "Richmond"},
                {"lat": 32.7765, "lng": -79.9311, "radius": 30, "name": "Charleston"},
                {"lat": 36.8508, "lng": -75.9742, "radius": 40, "name": "Virginia Beach"},
                
                # Midwest
                {"lat": 41.8781, "lng": -87.6298, "radius": 50, "name": "Chicago"},
                {"lat": 42.3314, "lng": -83.0458, "radius": 50, "name": "Detroit"},
                {"lat": 44.9778, "lng": -93.2650, "radius": 50, "name": "Minneapolis"},
                {"lat": 38.6270, "lng": -90.1994, "radius": 50, "name": "St. Louis"},
                {"lat": 39.7684, "lng": -86.1581, "radius": 40, "name": "Indianapolis"},
                {"lat": 41.2565, "lng": -95.9345, "radius": 40, "name": "Omaha"},
                {"lat": 39.0997, "lng": -94.5786, "radius": 50, "name": "Kansas City"},
                {"lat": 43.0389, "lng": -87.9065, "radius": 40, "name": "Milwaukee"},
                {"lat": 41.4993, "lng": -81.6944, "radius": 40, "name": "Cleveland"},
                {"lat": 39.9612, "lng": -82.9988, "radius": 40, "name": "Columbus"},
                {"lat": 39.1031, "lng": -84.5120, "radius": 40, "name": "Cincinnati"},
                
                # South
                {"lat": 29.7604, "lng": -95.3698, "radius": 50, "name": "Houston"},
                {"lat": 32.7767, "lng": -96.7970, "radius": 50, "name": "Dallas"},
                {"lat": 29.4241, "lng": -98.4936, "radius": 50, "name": "San Antonio"},
                {"lat": 30.2672, "lng": -97.7431, "radius": 50, "name": "Austin"},
                {"lat": 29.9511, "lng": -90.0715, "radius": 40, "name": "New Orleans"},
                {"lat": 36.1627, "lng": -86.7816, "radius": 40, "name": "Nashville"},
                {"lat": 35.1495, "lng": -90.0490, "radius": 40, "name": "Memphis"},
                {"lat": 33.5207, "lng": -86.8025, "radius": 40, "name": "Birmingham"},
                {"lat": 35.4676, "lng": -97.5164, "radius": 50, "name": "Oklahoma City"},
                
                # Mountain/West
                {"lat": 39.7392, "lng": -104.9903, "radius": 50, "name": "Denver"},
                {"lat": 40.7608, "lng": -111.8910, "radius": 50, "name": "Salt Lake City"},
                {"lat": 33.4484, "lng": -112.0740, "radius": 50, "name": "Phoenix"},
                {"lat": 32.2226, "lng": -110.9747, "radius": 40, "name": "Tucson"},
                {"lat": 35.0844, "lng": -106.6504, "radius": 40, "name": "Albuquerque"},
                {"lat": 36.1699, "lng": -115.1398, "radius": 50, "name": "Las Vegas"},
                {"lat": 43.6150, "lng": -116.2023, "radius": 40, "name": "Boise"},
                
                # West Coast
                {"lat": 34.0522, "lng": -118.2437, "radius": 50, "name": "Los Angeles"},
                {"lat": 37.7749, "lng": -122.4194, "radius": 50, "name": "San Francisco"},
                {"lat": 37.8044, "lng": -122.2712, "radius": 30, "name": "Oakland"},
                {"lat": 37.3382, "lng": -121.8863, "radius": 40, "name": "San Jose"},
                {"lat": 32.7157, "lng": -117.1611, "radius": 50, "name": "San Diego"},
                {"lat": 47.6062, "lng": -122.3321, "radius": 50, "name": "Seattle"},
                {"lat": 45.5152, "lng": -122.6784, "radius": 50, "name": "Portland"},
                {"lat": 38.5816, "lng": -121.4944, "radius": 40, "name": "Sacramento"},
                {"lat": 36.7378, "lng": -119.7871, "radius": 40, "name": "Fresno"},
                {"lat": 47.6588, "lng": -117.4260, "radius": 40, "name": "Spokane"},
                
                # Additional coverage for rural areas
                {"lat": 46.8772, "lng": -113.9961, "radius": 100, "name": "Montana"},
                {"lat": 44.3683, "lng": -100.3364, "radius": 100, "name": "South Dakota"},
                {"lat": 47.5515, "lng": -101.0020, "radius": 100, "name": "North Dakota"},
                {"lat": 43.0731, "lng": -107.2903, "radius": 100, "name": "Wyoming"},
                {"lat": 39.3210, "lng": -111.0937, "radius": 80, "name": "Central Utah"},
                {"lat": 44.0682, "lng": -114.7420, "radius": 100, "name": "Idaho"},
            ]
            
            # Track all unique pantries
            all_pantries = {}
            total_api_calls = len(search_centers)
            
            logger.info(f"Will make {total_api_calls} API calls to cover the US")
            
            # Process each search center
            for i, center in enumerate(search_centers):
                logger.info(
                    f"Progress: {i+1}/{total_api_calls} - Searching {center['name']} "
                    f"({center['lat']}, {center['lng']}) with radius {center['radius']} miles"
                )
                
                # Search for pantries in this area
                pantries = await self.search_pantries_by_location(
                    center["lat"], center["lng"], center["radius"]
                )
                
                # Process each pantry
                new_pantries = 0
                for pantry in pantries:
                    pantry_id = str(pantry.get("id", ""))
                    if pantry_id and pantry_id not in all_pantries:
                        all_pantries[pantry_id] = pantry
                        new_pantries += 1
                
                logger.info(
                    f"Found {len(pantries)} pantries in {center['name']}, "
                    f"{new_pantries} were new (total unique: {len(all_pantries)})"
                )
                
                # Small delay between API calls
                await asyncio.sleep(0.5)
            
            # Submit all pantries to the queue
            logger.info(f"Submitting {len(all_pantries)} unique pantries to queue")
            jobs_created = 0
            
            for pantry_id, pantry_data in all_pantries.items():
                # Get detailed information if needed
                if pantry_data.get("scheduleId") and not pantry_data.get("schedule"):
                    try:
                        detailed_pantry = await self.get_pantry_details(page, pantry_data)
                        if detailed_pantry:
                            pantry_data = detailed_pantry
                    except Exception as e:
                        logger.warning(f"Could not get details for pantry {pantry_id}: {e}")
                
                # Transform to HSDS format
                hsds_data = self.transform_to_hsds(pantry_data)
                
                # Submit to queue
                try:
                    job_id = self.submit_to_queue(json.dumps(hsds_data))
                    jobs_created += 1
                    if jobs_created % 100 == 0:
                        logger.info(f"Submitted {jobs_created} jobs to queue...")
                except Exception as e:
                    logger.error(f"Error submitting pantry {pantry_id}: {e}")
            
            return {
                "total_search_centers": total_api_calls,
                "total_pantries_found": len(all_pantries),
                "unique_pantries": len(all_pantries),
                "jobs_created": jobs_created,
                "source": self.base_url,
                "method": "geo_search_api",
            }
            
        finally:
            await browser.close()
            await playwright.stop()

    async def parallel_scrape(self) -> dict[str, Any]:
        """Scrape data using multiple browser instances in parallel.

        Returns:
            Dictionary with scraping results
        """
        logger.info(f"Starting parallel scrape with {self.num_workers} workers")

        # Prepare regional coordinate sets
        regional_coordinates = self._prepare_regional_coordinate_sets()

        # Distribute coordinates among workers
        worker_coordinate_sets = self._distribute_coordinates(regional_coordinates)

        # Calculate total coordinates for progress tracking
        total_coordinates = sum(len(coords) for coords in worker_coordinate_sets)
        logger.info(f"Total coordinates to process: {total_coordinates}")

        # Create workers
        workers = [BrowserWorker(i, self) for i in range(self.num_workers)]

        # Initialize workers
        logger.info("Initializing workers...")
        await asyncio.gather(*(worker.initialize() for worker in workers))

        # Set up progress tracking
        self.total_coordinates_processed = 0
        self.progress_lock = threading.Lock()

        # Start a background task to periodically log overall progress
        progress_task = asyncio.create_task(
            self._log_overall_progress(total_coordinates)
        )

        # Process coordinates in parallel
        logger.info("Processing coordinates in parallel...")
        worker_results = []
        try:
            worker_results = await asyncio.gather(
                *(
                    self._process_worker_coordinates(worker, coords, total_coordinates)
                    for worker, coords in zip(
                        workers, worker_coordinate_sets, strict=False
                    )
                )
            )

            # Cancel the progress logging task
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

        finally:
            # Clean up all workers
            logger.info("Cleaning up workers...")
            await asyncio.gather(*(worker.cleanup() for worker in workers))

        # Aggregate results
        total_pantries = sum(
            result["total_pantries_found"] for result in worker_results
        )
        unique_pantries_count = 0
        all_pantry_ids: set[str] = set()

        # Count truly unique pantries across all workers
        for result in worker_results:
            worker_pantry_ids = set(result["pantry_ids"])
            new_pantries = worker_pantry_ids - all_pantry_ids
            unique_pantries_count += len(new_pantries)
            all_pantry_ids.update(worker_pantry_ids)

        # Create summary
        summary = {
            "total_coordinates": total_coordinates,
            "total_pantries_found": total_pantries,
            "unique_pantries": len(all_pantry_ids),
            "duplicate_pantries": total_pantries - len(all_pantry_ids),
            "source": self.base_url,
            "workers": self.num_workers,
        }

        return summary

    async def _process_worker_coordinates(
        self,
        worker: BrowserWorker,
        coordinates: list[GridPoint],
        total_coordinates: int,
    ) -> dict[str, Any]:
        """Process coordinates with a worker and update overall progress.

        Args:
            worker: The worker to use
            coordinates: The coordinates to process
            total_coordinates: Total coordinates across all workers

        Returns:
            Worker results
        """
        # Process coordinates with the worker
        result = await worker.process_coordinates(coordinates)

        # Update overall progress and merge unique pantries
        with self.progress_lock:
            self.total_coordinates_processed += len(coordinates)
            # Add unique pantries from this worker to the global set
            for pantry_id in result["pantry_ids"]:
                self.unique_pantries.add(pantry_id)

        return result

    async def _log_overall_progress(self, total_coordinates: int) -> None:
        """Periodically log overall progress across all workers.

        Args:
            total_coordinates: Total coordinates to process
        """
        try:
            # Initialize counters
            self.total_coordinates_processed = 0

            while True:
                # Wait for 30 seconds between progress updates
                await asyncio.sleep(30)

                # Get current progress - directly count from worker data
                coordinates_processed = 0
                pantries_found = 0
                processed_pantries = 0

                with self.progress_lock:
                    # Count directly from the sets to ensure accuracy
                    pantries_found = len(self.unique_pantries)
                    processed_pantries = len(self.processed_pantry_ids)
                    coordinates_processed = self.total_coordinates_processed

                # Calculate progress percentage
                progress_percent = min(
                    100, round(coordinates_processed / total_coordinates * 100)
                )

                # Log overall progress with more detailed information
                logger.info(
                    f"OVERALL PROGRESS: {progress_percent}% of coordinates processed ({coordinates_processed}/{total_coordinates})"
                )
                logger.info(
                    f"OVERALL STATS: {pantries_found} unique pantries found, {processed_pantries} pantries processed"
                )

                # Debug log to help diagnose issues
                logger.info(
                    f"DEBUG: unique_pantries set size: {len(self.unique_pantries)}"
                )
                logger.info(
                    f"DEBUG: processed_pantry_ids set size: {len(self.processed_pantry_ids)}"
                )
                logger.info(
                    f"DEBUG: total_coordinates_processed: {self.total_coordinates_processed}"
                )

        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass

    async def scrape(self) -> str:
        """Scrape data from GetFull.app using the geo search API.

        Returns:
            Summary of scraping results as JSON string
        """
        # Reset storage for pantry data
        self.pantry_data = {}
        self.unique_pantries = set()
        self.total_pantries = 0
        self.processed_pantry_ids = (
            set()
        )  # Reset the shared set of processed pantry IDs

        # Use the new geo search approach which is more comprehensive
        summary = await self.geo_search_scrape()

        # Print summary to CLI
        print("\nGetFull.app Search Complete!")
        print("=" * 50)
        
        if "error" in summary:
            print(f"ERROR: {summary['error']}")
        else:
            print(f"Search Method: Geo Search API")
            print(f"Total Search Centers: {summary.get('total_search_centers', 0)}")
            print(f"Total Pantries Found: {summary.get('total_pantries_found', 0)}")
            print(f"Unique Pantries: {summary.get('unique_pantries', 0)}")
            print(f"Jobs Created: {summary.get('jobs_created', 0)}")
        
        print("=" * 50)

        return json.dumps(summary)
