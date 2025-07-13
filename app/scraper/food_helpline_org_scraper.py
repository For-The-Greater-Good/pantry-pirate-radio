"""Scraper for FoodHelpline.org API data."""

import asyncio
import json
import logging
from typing import Any

import httpx

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Food_Helpline_OrgScraper(ScraperJob):
    """Scraper for FoodHelpline.org API data."""

    def __init__(self, scraper_id: str = "food_helpline_org") -> None:
        """Initialize scraper with ID 'food_helpline_org' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'food_helpline_org'
        """
        super().__init__(scraper_id=scraper_id)
        self.base_url = "https://platform.foodhelpline.org/api"
        self.locations_url = f"{self.base_url}/locations"
        self.resources_url = f"{self.base_url}/resources"
        self.regions_url = f"{self.base_url}/regions"
        self.tag_categories_url = f"{self.base_url}/tagCategories"
        self.batch_size = 50  # Number of locations to process in each batch
        self.headers = get_scraper_headers()

    async def fetch_api_data(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
        retries: int = 3,
    ) -> Any:
        """Fetch data from API endpoint.

        Args:
            url: API endpoint URL
            params: Optional query parameters
            timeout: Request timeout in seconds
            retries: Number of retry attempts for failed requests

        Returns:
            Parsed JSON data

        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        logger.info(f"Fetching data from {url} with params {params}")

        attempt = 0
        last_error = None

        while attempt < retries:
            try:
                async with httpx.AsyncClient(
                    headers=self.headers, timeout=timeout
                ) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()

                    # Log response details for debugging
                    logger.info(f"Response status: {response.status_code}")
                    logger.info(f"Response headers: {response.headers}")

                    # Try to parse JSON response
                    try:
                        data = response.json()
                        logger.info(f"Response data type: {type(data)}")
                        if isinstance(data, dict):
                            logger.info(f"Response keys: {list(data.keys())}")
                        return data
                    except json.JSONDecodeError as e:
                        # Log the raw response content for debugging
                        logger.error(f"JSON decode error: {e}")
                        logger.error(
                            f"Response content: {response.text[:500]}..."
                        )  # Log first 500 chars
                        raise

            except (httpx.HTTPError, json.JSONDecodeError) as e:
                last_error = e
                attempt += 1
                if attempt < retries:
                    wait_time = 2**attempt  # Exponential backoff
                    logger.warning(
                        f"Request failed (attempt {attempt}/{retries}): {e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {retries} attempts: {e}")
                    raise

        # This should not be reached, but just in case
        if last_error:
            raise last_error
        raise RuntimeError("Failed to fetch data after all retries")

    async def fetch_regions(self) -> list[dict[str, Any]]:
        """Fetch regions data from API.

        Returns:
            List of region objects
        """
        params = {"include": "resources", "depth": "1"}
        data = await self.fetch_api_data(self.regions_url, params)

        # Extract regions from the response
        logger.info(f"Regions response type: {type(data)}")

        # Handle different response formats
        if isinstance(data, dict):
            if "json" in data and isinstance(data["json"], list):
                logger.info(f"Found {len(data['json'])} regions in json array")
                return data["json"]
            elif "data" in data and isinstance(data["data"], list):
                logger.info(f"Found {len(data['data'])} regions in data array")
                return data["data"]
        elif isinstance(data, list):
            logger.info(f"Response is a list with {len(data)} regions")
            return data

        # If we couldn't extract regions, log the response structure and return empty list
        logger.error(
            f"Could not extract regions from response. Keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
        )
        return []

    async def fetch_locations(
        self, batch_size: int = 50, has_resources: bool = True
    ) -> list[dict[str, Any]]:
        """Fetch locations data from API in batches.

        Args:
            batch_size: Number of locations to fetch per request
            has_resources: Whether to only fetch locations with resources

        Returns:
            List of location objects
        """
        all_locations = []
        cursor = None
        page = 1

        while True:
            logger.info(f"Fetching locations page {page} with cursor: {cursor}")

            params = {"limit": str(batch_size)}

            if has_resources:
                params["hasResources"] = "true"

            if cursor:
                params["cursor"] = cursor

            try:
                data = await self.fetch_api_data(self.locations_url, params)

                # Log the response structure for debugging
                logger.info(f"Location API response type: {type(data)}")

                # Handle different response formats
                locations = []
                next_cursor = None

                if isinstance(data, list):
                    # If the response is a list, use it directly
                    logger.info(f"Response is a list with {len(data)} items")
                    if len(data) > 0:
                        logger.info(f"First item type: {type(data[0])}")
                        # Log a sample of the first item
                        if isinstance(data[0], dict):
                            sample_keys = list(data[0].keys())[:5]  # First 5 keys
                            logger.info(f"Sample keys: {sample_keys}")
                    locations = data

                    # If we got a full batch, there might be more
                    if len(locations) >= batch_size:
                        # Use the last location's ID as a cursor
                        if (
                            locations
                            and isinstance(locations[-1], dict)
                            and "id" in locations[-1]
                        ):
                            next_cursor = locations[-1]["id"]
                            logger.info(
                                f"Using last location ID as cursor: {next_cursor}"
                            )

                elif isinstance(data, dict):
                    # If the response is a dict, try to find locations in it
                    if "data" in data and isinstance(data["data"], list):
                        locations = data["data"]
                    elif "json" in data:
                        json_data = data["json"]
                        if isinstance(json_data, list):
                            locations = json_data
                        elif isinstance(json_data, dict) and "data" in json_data:
                            locations = json_data["data"]

                    # Extract cursor from response
                    if data.get("cursor"):
                        next_cursor = data["cursor"]
                    elif (
                        "json" in data
                        and isinstance(data["json"], dict)
                        and "cursor" in data["json"]
                    ):
                        next_cursor = data["json"]["cursor"]

                logger.info(f"Found {len(locations)} locations on page {page}")
                all_locations.extend(locations)

                # Check if we should fetch more
                if next_cursor and next_cursor != cursor and len(locations) > 0:
                    cursor = next_cursor
                    page += 1
                else:
                    logger.info("No more locations to fetch")
                    break

            except Exception as e:
                logger.error(f"Error fetching locations page {page}: {e}")
                break

        logger.info(f"Total locations fetched: {len(all_locations)}")
        return all_locations

    async def fetch_resources_for_location(
        self, location_id: str
    ) -> list[dict[str, Any]]:
        """Fetch resources for a specific location.

        Args:
            location_id: Location ID

        Returns:
            List of resource objects
        """
        params = {"take": "10", "location": location_id}  # Adjust as needed

        data = await self.fetch_api_data(self.resources_url, params)

        # Log response structure for debugging
        logger.info(f"Resources response type for location {location_id}: {type(data)}")

        # Handle different response formats
        if isinstance(data, dict):
            if (
                "json" in data
                and isinstance(data["json"], dict)
                and "resources" in data["json"]
            ):
                logger.info("Found resources in json.resources")
                return data["json"]["resources"]
            elif "json" in data and isinstance(data["json"], list):
                logger.info("Found resources in json array")
                return data["json"]
            elif "data" in data and isinstance(data["data"], list):
                logger.info("Found resources in data array")
                return data["data"]
            elif "resources" in data and isinstance(data["resources"], list):
                logger.info("Found resources directly in resources array")
                return data["resources"]
        elif isinstance(data, list):
            logger.info(f"Response is a list with {len(data)} resources")
            return data

        # If we couldn't extract resources, log the response structure and return empty list
        logger.error(
            f"Could not extract resources from response for location {location_id}. Keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
        )
        return []

    def transform_to_hsds(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Transform resource data to HSDS format.

        Args:
            resource: Resource data from API

        Returns:
            Resource data in HSDS format
        """
        # Extract basic information
        hsds_data = {
            "name": resource.get("name", ""),
            "alternate_name": "",
            "description": resource.get("description", ""),
            "email": "",
            "url": resource.get("website", ""),
            "status": "active",
            "address": {
                "address_1": resource.get("addressStreet1", ""),
                "address_2": resource.get("addressStreet2", ""),
                "city": resource.get("city", ""),
                "state_province": resource.get("state", ""),
                "postal_code": resource.get("zipCode", ""),
                "country": "US",
            },
            "location": {
                "latitude": resource.get("latitude", 0),
                "longitude": resource.get("longitude", 0),
            },
        }

        # Extract contact information
        if resource.get("contacts"):
            for contact in resource["contacts"]:
                if "phone" in contact and contact.get("public", False):
                    hsds_data["phones"] = [
                        {"number": contact["phone"], "type": "voice"}
                    ]
                    break

        # Extract hours information from shifts
        if resource.get("shifts"):
            regular_schedule = []
            for shift in resource["shifts"]:
                if shift.get("recurrencePattern"):
                    # Parse recurrence pattern to extract days and hours
                    pattern = shift["recurrencePattern"]

                    # Extract days (BYDAY parameter)
                    days = []
                    if pattern and "BYDAY=" in pattern:
                        days_match = pattern.find("BYDAY=")
                        if days_match != -1:
                            days_part = pattern[days_match:].split(";")[0].split("=")[1]
                            days = days_part.split(",")

                        # Map days to HSDS format
                        day_mapping = {
                            "MO": "Monday",
                            "TU": "Tuesday",
                            "WE": "Wednesday",
                            "TH": "Thursday",
                            "FR": "Friday",
                            "SA": "Saturday",
                            "SU": "Sunday",
                        }

                        # Extract start and end times
                        start_time = ""
                        end_time = ""
                        if shift.get("startTime"):
                            start_parts = shift["startTime"].split("T")
                            if len(start_parts) > 1:
                                start_time = start_parts[1][:5]

                        if shift.get("endTime"):
                            end_parts = shift["endTime"].split("T")
                            if len(end_parts) > 1:
                                end_time = end_parts[1][:5]

                        for day_code in days:
                            if day_code in day_mapping:
                                regular_schedule.append(
                                    {
                                        "weekday": day_mapping[day_code],
                                        "opens_at": start_time,
                                        "closes_at": end_time,
                                    }
                                )

            if regular_schedule:
                hsds_data["regular_schedule"] = regular_schedule

        # Extract tags as service attributes
        if resource.get("tags"):
            service_attributes = []
            for tag in resource["tags"]:
                service_attributes.append(
                    {
                        "attribute_key": tag.get("tagCategoryId", "UNCATEGORIZED"),
                        "attribute_value": tag.get("name", ""),
                    }
                )

            if service_attributes:
                hsds_data["service_attributes"] = service_attributes

        return hsds_data

    async def fetch_resources_directly(self) -> list[dict[str, Any]]:
        """Fetch resources directly from the API.

        This is an alternative approach to fetch resources without going through locations.

        Returns:
            List of resource objects
        """
        all_resources = []
        cursor = None
        page = 1
        batch_size = 50

        while True:
            logger.info(f"Fetching resources page {page} with cursor: {cursor}")

            params = {"take": str(batch_size)}

            if cursor:
                params["cursor"] = cursor

            try:
                data = await self.fetch_api_data(f"{self.base_url}/resources", params)

                # Log response structure for debugging
                logger.info(f"Direct resources response type: {type(data)}")

                # Extract resources from the response
                resources = []
                next_cursor = None

                if isinstance(data, dict):
                    if (
                        "json" in data
                        and isinstance(data["json"], dict)
                        and "resources" in data["json"]
                    ):
                        resources = data["json"]["resources"]
                        if "cursor" in data["json"]:
                            next_cursor = data["json"]["cursor"]
                    elif "json" in data and isinstance(data["json"], list):
                        resources = data["json"]
                    elif "data" in data and isinstance(data["data"], list):
                        resources = data["data"]
                    elif "resources" in data and isinstance(data["resources"], list):
                        resources = data["resources"]
                elif isinstance(data, list):
                    resources = data

                logger.info(f"Found {len(resources)} resources on page {page}")
                all_resources.extend(resources)

                # Check if we should fetch more
                if next_cursor and next_cursor != cursor and len(resources) > 0:
                    cursor = next_cursor
                    page += 1
                else:
                    logger.info("No more resources to fetch")
                    break

            except Exception as e:
                logger.error(f"Error fetching resources page {page}: {e}")
                break

        logger.info(f"Total resources fetched directly: {len(all_resources)}")
        return all_resources

    async def fetch_resources_from_regions(self) -> list[dict[str, Any]]:
        """Fetch resources from all regions.

        Returns:
            List of resource objects
        """
        # 1. Fetch regions
        regions = await self.fetch_regions()
        logger.info(f"Fetched {len(regions)} regions")

        # 2. Extract resources from regions
        all_resources = []
        processed_resource_ids = set()

        for region in regions:
            region_id = region.get("id", "")
            region_name = region.get("name", "Unknown")

            if not region_id:
                continue

            logger.info(f"Processing region: {region_name} ({region_id})")

            # Extract resources directly from region
            if "resources" in region and isinstance(region["resources"], list):
                region_resources = region["resources"]
                logger.info(
                    f"Found {len(region_resources)} resources in region {region_name}"
                )

                for resource in region_resources:
                    resource_id = resource.get("id", "")

                    # Skip resources we've already processed
                    if resource_id and resource_id in processed_resource_ids:
                        continue

                    # Add to processed set
                    if resource_id:
                        processed_resource_ids.add(resource_id)
                        all_resources.append(resource)

            # Process child regions
            if "children" in region and isinstance(region["children"], list):
                for child in region["children"]:
                    child_id = child.get("id", "")
                    child_name = child.get("name", "Unknown")

                    if not child_id:
                        continue

                    logger.info(f"Processing child region: {child_name} ({child_id})")

                    # Extract resources from child region
                    if "resources" in child and isinstance(child["resources"], list):
                        child_resources = child["resources"]
                        logger.info(
                            f"Found {len(child_resources)} resources in child region {child_name}"
                        )

                        for resource in child_resources:
                            resource_id = resource.get("id", "")

                            # Skip resources we've already processed
                            if resource_id and resource_id in processed_resource_ids:
                                continue

                            # Add to processed set
                            if resource_id:
                                processed_resource_ids.add(resource_id)
                                all_resources.append(resource)

        logger.info(f"Total resources fetched from regions: {len(all_resources)}")
        return all_resources

    async def scrape(self) -> str:
        """Scrape data from FoodHelpline.org API.

        Returns:
            Summary of scraping operation as JSON string
        """
        # 1. Fetch regions to understand geographic coverage
        regions = await self.fetch_regions()
        logger.info(f"Fetched {len(regions)} regions")

        # 2. Fetch locations in batches
        locations = await self.fetch_locations(self.batch_size)
        logger.info(f"Fetched {len(locations)} locations")

        # 3. Fetch resources directly from regions
        region_resources = await self.fetch_resources_from_regions()
        logger.info(f"Fetched {len(region_resources)} resources from regions")

        # 4. Fetch resources directly from API
        direct_resources = await self.fetch_resources_directly()
        logger.info(f"Fetched {len(direct_resources)} resources directly")

        # 5. Process resources and submit to queue
        total_resources = 0
        processed_resources = set()  # Track resources we've already processed

        # Combine all resources
        all_resources = []

        # Add resources from regions
        for resource in region_resources:
            resource_id = resource.get("id", "")
            if resource_id and resource_id not in processed_resources:
                processed_resources.add(resource_id)
                all_resources.append(resource)

        # Add resources from direct API
        for resource in direct_resources:
            resource_id = resource.get("id", "")
            if resource_id and resource_id not in processed_resources:
                processed_resources.add(resource_id)
                all_resources.append(resource)

        # Process locations
        for i, location in enumerate(locations):
            location_id = location.get("id", "")
            if not location_id:
                continue

            logger.info(f"Processing location {i+1}/{len(locations)}: {location_id}")

            try:
                resources = await self.fetch_resources_for_location(location_id)
                logger.info(
                    f"Fetched {len(resources)} resources for location {location_id}"
                )

                for resource in resources:
                    resource_id = resource.get("id", "")

                    # Skip resources we've already processed
                    if resource_id and resource_id in processed_resources:
                        logger.info(
                            f"Skipping already processed resource: {resource.get('name', 'Unknown')}"
                        )
                        continue

                    # Add to processed set
                    if resource_id:
                        processed_resources.add(resource_id)
                        all_resources.append(resource)
            except httpx.HTTPError as e:
                # Handle HTTP errors gracefully
                logger.error(f"HTTP error for location {location_id}: {e}")
                continue
            except Exception as e:
                # Handle other errors gracefully
                logger.error(f"Error processing location {location_id}: {e}")
                continue

        # Process all unique resources
        logger.info(f"Processing {len(all_resources)} unique resources")
        for resource in all_resources:
            try:
                # Transform resource to HSDS format
                hsds_data = self.transform_to_hsds(resource)

                # Submit to queue
                job_id = self.submit_to_queue(json.dumps(hsds_data))
                logger.info(
                    f"Queued job {job_id} for resource: {resource.get('name', 'Unknown')}"
                )
                total_resources += 1
            except Exception as e:
                logger.error(
                    f"Error processing resource {resource.get('name', 'Unknown')}: {e}"
                )
                continue

        # 4. Create summary
        summary = {
            "total_regions": len(regions),
            "total_locations": len(locations),
            "total_resources": total_resources,
            "source": self.base_url,
        }

        # Print summary to CLI
        print("\nScraper Summary:")
        print(f"Source: {self.base_url}")
        print(f"Total regions: {len(regions)}")
        print(f"Total locations: {len(locations)}")
        print(f"Total resources: {total_resources}")
        print("Status: Complete\n")

        # Return summary as JSON string
        return json.dumps(summary)
