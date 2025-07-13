"""Scraper for Vivery API data."""

import asyncio
import json
import logging
import re
from typing import Any, TypedDict, cast

import httpx

from app.models.geographic import GridPoint
from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class ScheduleData(TypedDict):
    """Type definition for schedule data."""

    locationId: int
    weekDayDescr: str
    startTimeDescr: str
    endTimeDescr: str
    notes: str
    weeksOfMonth: str


class ServiceData(TypedDict):
    """Type definition for service data."""

    locationId: int
    serviceName: str
    serviceCategoryDescription: str
    overview: str
    qualifications: str
    contactName: str
    contactPhone: str


class SpecialHoursData(TypedDict):
    """Type definition for special hours data."""

    id: int
    data: list[dict[str, str]]


class LocationData(TypedDict):
    """Type definition for location data."""

    locationId: str
    organizationId: str
    name: str
    address1: str
    address2: str
    city: str
    state: str
    zipCode: str
    country: str
    phone: str
    phoneExt: str
    website: str
    latitude: str
    longitude: str
    foodPrograms: str
    serviceAreas: str
    languages: str
    features: str
    aboutUs: str
    notes: str
    contactName: str
    contactPhone: str
    contactEmail: str
    servicePrograms: str
    foodServiceTypes: str
    dietRestrictions: str
    foodOfferings: str
    networkAffiliations: list[str]
    timeZoneName: str
    timeZoneCode: str
    offsetHours: str
    schedules: list[str]
    services: list[dict[str, str]]
    specialHours: list[dict[str, str]]


class ScraperSummary(TypedDict):
    """Type definition for scraper summary."""

    total_coordinates: int
    total_locations_found: int
    unique_locations: int
    source: str


class Vivery_ApiScraper(ScraperJob):
    """Scraper for Vivery API data."""

    def __init__(self, scraper_id: str = "vivery") -> None:
        """Initialize scraper with ID 'vivery' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'vivery'
        """
        super().__init__(scraper_id=scraper_id)
        self.base_url = "https://api.accessfood.org/api"
        self.batch_size = 25
        self.request_delay = 0.01  # 10ms between requests
        self.total_locations = 0
        self.unique_locations: set[str] = set()
        self.location_data: dict[str, LocationData] = {}

    async def search_locations(self, lat: float, lng: float) -> list[dict[str, Any]]:
        """Search for locations at given coordinates.

        Args:
            lat: Latitude
            lng: Longitude

        Returns:
            List of location data dictionaries

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient(headers=get_scraper_headers()) as client:
            # Search for locations
            search_url = f"{self.base_url}/MapInformation/LocationSearch"
            params: dict[str, Any] = {
                "radius": 90,
                "lat": lat,
                "lng": lng,
                "dayAv": "",
                "foodProgramAv": "",
                "serviceTypeAv": "",
                "foodOfferingAv": "",
                "dietRestrictionAv": "",
                "locationFeatureAv": "",
                "languagesAv": "",
                "serviceCategoriesAv": "",
                "regionId": 3,
                "regionMapId": 28,
                "showOutOfNetwork": 0,
                "page": 0,
                "includeLocationOperatingHours": True,
            }

            response = await client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()

            # Handle API response which could be a dictionary with 'item1' or a direct list
            if isinstance(data, dict):
                data_dict = cast(dict[str, Any], data)
                if "item1" in data_dict:
                    item1 = data_dict["item1"]
                    if isinstance(item1, list):
                        return cast(list[dict[str, Any]], item1)
                return []
            elif isinstance(data, list):
                return cast(list[dict[str, Any]], data)
            return []

    async def fetch_additional_data(
        self, location_ids: list[str]
    ) -> tuple[list[ScheduleData], list[ServiceData], list[SpecialHoursData]]:
        """Fetch additional data for locations.

        Args:
            location_ids: List of location IDs

        Returns:
            Tuple of (schedules, services, special hours)

        Raises:
            httpx.HTTPError: If API request fails
        """
        if not location_ids:
            return [], [], []

        async with httpx.AsyncClient(headers=get_scraper_headers()) as client:
            # Fetch schedules, services, and special hours in parallel
            responses = await asyncio.gather(
                client.get(
                    f"{self.base_url}/MapInformation/LocationServiceSchedules",
                    params={"LocationIds": ",".join(location_ids)},
                ),
                client.get(
                    f"{self.base_url}/MapInformation/LocationServices",
                    params={
                        "LocationIds": ",".join(f"{id}|1" for id in location_ids),
                        "PreviewMode": False,
                        "MapRegionId": 3,
                    },
                ),
                client.get(
                    f"{self.base_url}/MapInformation/MultipleLocations_LocationSpecialHoursByFirstPage",
                    params={
                        "LocationIds": ",".join(location_ids),
                        "TimezoneOffsetMinutes": 480,
                        "PageSize": 5,
                    },
                ),
            )

            # Process responses
            schedules = cast(
                list[ScheduleData],
                responses[0].json() if responses[0].status_code == 200 else [],
            )
            services = cast(
                list[ServiceData],
                responses[1].json() if responses[1].status_code == 200 else [],
            )
            special_hours = cast(
                list[SpecialHoursData],
                responses[2].json() if responses[2].status_code == 200 else [],
            )

            return schedules, services, special_hours

    def format_schedule(self, schedule: ScheduleData) -> str:
        """Format schedule data into string.

        Args:
            schedule: Schedule data dictionary

        Returns:
            Formatted schedule string
        """
        parts: list[str] = [
            schedule.get("weekDayDescr", ""),
            f"{schedule.get('startTimeDescr', '')}-{schedule.get('endTimeDescr', '')}",
        ]

        if notes := schedule.get("notes"):
            parts.append(f"({notes})")

        if weeks := schedule.get("weeksOfMonth"):
            parts.append(f"[{weeks} week(s)]")

        return " ".join(filter(None, parts))

    def format_service(self, service: ServiceData) -> dict[str, str]:
        """Format service data.

        Args:
            service: Service data dictionary

        Returns:
            Formatted service dictionary
        """
        overview = service.get("overview", "")
        if overview:
            # Remove HTML tags
            overview = re.sub(r"<[^>]*>", " ", overview).strip()

        contact = ""
        if name := service.get("contactName"):
            contact = name
            if phone := service.get("contactPhone"):
                contact += f" ({phone})"

        return {
            "name": service.get("serviceName", ""),
            "category": service.get("serviceCategoryDescription", ""),
            "overview": overview,
            "qualifications": service.get("qualifications", ""),
            "contact": contact,
        }

    async def process_batch(self, coordinates: list[GridPoint]) -> None:
        """Process a batch of coordinates.

        Args:
            coordinates: List of coordinate points to process
        """
        for coord in coordinates:
            try:
                # Search for locations
                locations = await self.search_locations(coord.latitude, coord.longitude)

                if not locations:
                    continue

                # Get location IDs
                location_ids = [str(loc["locationId"]) for loc in locations]

                # Fetch additional data
                schedules, services, special_hours = await self.fetch_additional_data(
                    location_ids
                )

                # Process each location
                for location in locations:
                    loc_id = str(location["locationId"])

                    # Get special hours data for this location
                    special_hours_data: list[dict[str, str]] = []
                    for sh in special_hours:
                        if sh.get("id") == int(loc_id):
                            special_hours_data = sh.get("data", [])
                            break

                    # Store enriched data for later processing
                    self.location_data[loc_id] = {
                        "locationId": loc_id,
                        "organizationId": str(location.get("organizationId", "")),
                        "name": location.get("locationName", ""),
                        "address1": location.get("address1", ""),
                        "address2": location.get("address2", ""),
                        "city": location.get("city", ""),
                        "state": location.get("state", ""),
                        "zipCode": location.get("zipCode", "").strip(),
                        "country": location.get("country", ""),
                        "phone": location.get("phone", ""),
                        "phoneExt": location.get("phoneExt", ""),
                        "website": location.get("website", ""),
                        "latitude": str(location.get("latitude", "")),
                        "longitude": str(location.get("longitude", "")),
                        "foodPrograms": (location.get("foodPrograms") or "").strip(),
                        "serviceAreas": (location.get("serviceAreas") or "").strip(),
                        "languages": (location.get("serviceLanguages") or "").strip(),
                        "features": (
                            location.get("locationFeatures", "").split("|")[0] or ""
                        ).strip(),
                        "aboutUs": re.sub(
                            r"<[^>]*>", " ", location.get("aboutUs") or ""
                        ).strip(),
                        "notes": re.sub(
                            r"<[^>]*>", " ", location.get("notes") or ""
                        ).strip(),
                        "contactName": location.get("contactName", ""),
                        "contactPhone": location.get("contactPhone", ""),
                        "contactEmail": location.get("contactEmail", ""),
                        "servicePrograms": (
                            location.get("servicePrograms") or ""
                        ).strip(),
                        "foodServiceTypes": (
                            location.get("foodServiceTypes") or ""
                        ).strip(),
                        "dietRestrictions": (
                            location.get("dietRestrictions") or ""
                        ).strip(),
                        "foodOfferings": (location.get("foodOfferings") or "").strip(),
                        "networkAffiliations": location.get(
                            "networkAffiliationsList", []
                        ),
                        "timeZoneName": location.get("timeZoneName", ""),
                        "timeZoneCode": location.get("timeZoneCode", ""),
                        "offsetHours": str(location.get("offsetHours", "")),
                        "schedules": [
                            self.format_schedule(s)
                            for s in schedules
                            if s.get("locationId") == int(loc_id)
                        ],
                        "services": [
                            self.format_service(s)
                            for s in services
                            if s.get("locationId") == int(loc_id)
                        ],
                        "specialHours": special_hours_data,
                    }

                    # Only process and count if it's a new location
                    if loc_id not in self.unique_locations:
                        self.total_locations += 1
                        self.unique_locations.add(loc_id)
                        logger.info(
                            f"Found location {loc_id} (total: {self.total_locations}, unique: {len(self.unique_locations)})"
                        )

            except Exception as e:
                logger.error(f"Error processing coordinate {coord}: {e}")
                continue

            # Delay between coordinates
            await asyncio.sleep(self.request_delay)

    async def scrape(self) -> str:
        """Scrape data from Vivery API.

        Returns:
            Summary of scraping results as JSON string
        """
        # Reset storage for enriched location data
        self.location_data = {}

        # Get grid points for continental US
        coordinates = self.utils.get_us_grid_points()
        logger.info(f"Starting search with {len(coordinates)} coordinate points...")

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
        logger.info(
            f"\nSubmitting {len(self.unique_locations)} unique locations to queue..."
        )

        for loc_id, location_data in self.location_data.items():
            if loc_id in self.unique_locations:
                job_id = self.submit_to_queue(json.dumps(location_data))
                logger.info(f"Queued job {job_id} for location {loc_id}")

        # Create summary
        summary: ScraperSummary = {
            "total_coordinates": len(coordinates),
            "total_locations_found": self.total_locations,
            "unique_locations": len(self.unique_locations),
            "source": self.base_url,
        }

        # Print summary to CLI
        print("\nSearch complete!")
        print("Final Stats:")
        print(f"- Total locations processed: {self.total_locations}")
        print(f"- Unique locations found: {len(self.unique_locations)}")

        return json.dumps(summary)
