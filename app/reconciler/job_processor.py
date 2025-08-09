"""Job processing utilities for the reconciler."""

import json
import logging
import re
import uuid
from typing import Any, cast

import demjson3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from typing_extensions import TypedDict

from app.core.config import settings
from app.llm.queue.models import JobResult
from app.reconciler.location_creator import LocationCreator
from app.reconciler.metrics import (
    LOCATION_MATCHES,
    RECONCILER_JOBS,
    SERVICE_LOCATION_LINKS,
    SERVICE_RECORDS,
)
from app.reconciler.organization_creator import OrganizationCreator
from app.reconciler.service_creator import ServiceCreator
from app.reconciler.version_tracker import VersionTracker

# Configure logging
logger = logging.getLogger(__name__)


def process_job_result(job_result: JobResult) -> dict[str, Any]:
    """Process a job result.

    This is the entry point for RQ to process job results.

    Args:
        job_result: The job result to process

    Returns:
        Dict with processing results
    """
    try:
        # Get database session
        engine = create_engine(settings.DATABASE_URL)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            # Process with job processor
            processor = JobProcessor(db=session)
            return processor.process_job_result(job_result)

    except Exception as e:
        logger.exception("Failed to process job result")
        error_result: dict[str, str] = {"status": "error", "error": str(e)}
        raise ValueError(json.dumps(error_result)) from e


class ScheduleDict(TypedDict):
    """Type definition for schedule data."""

    freq: str
    wkst: str
    opens_at: str
    closes_at: str
    byday: str | None


class ServiceDict(TypedDict):
    """Type definition for service data."""

    name: str
    description: str
    phones: list[dict[str, Any]]
    languages: list[dict[str, Any]]
    schedules: list[ScheduleDict]


class OrganizationDict(TypedDict):
    """Type definition for organization data."""

    name: str
    description: str
    website: str
    email: str
    year_incorporated: int
    legal_status: str
    uri: str
    phones: list[dict[str, Any]]
    services: list[ServiceDict]
    organization_identifiers: list[dict[str, Any]]


class LocationDict(TypedDict):
    """Type definition for location data."""

    name: str
    description: str
    latitude: float
    longitude: float
    addresss: list[dict[str, Any]]  # Note: HSDS spec uses "addresss" with 3 s's
    phones: list[dict[str, Any]]
    schedules: list[ScheduleDict]
    accessibility: list[dict[str, Any]]


class HSDataDict(TypedDict):
    """Type definition for HSDS data."""

    organization: list[OrganizationDict]
    service: list[ServiceDict]
    location: list[LocationDict]


class JobProcessor:
    """Utilities for processing reconciliation jobs."""

    def __init__(self, db: Session) -> None:
        """Initialize reconciler utils.

        Args:
            db: Database session
        """
        self.db = db
        self.logger = logging.getLogger(__name__)

    def process_completed_jobs(self) -> None:
        """Process completed jobs.

        This method is no longer needed since we're using RQ's worker system.
        Jobs are now processed directly by the RQ worker when they arrive.
        """
        self.logger.info("Method deprecated - jobs are processed by RQ worker")

    def _transform_schedule(self, schedule: dict) -> dict | None:
        """Transform schedule from various formats to expected format.
        
        Handles conversion from times array with start_time/end_time 
        to opens_at/closes_at format.
        """
        if not schedule:
            return None
            
        transformed = schedule.copy()
        
        # Handle times array format (from LLM output)
        if "times" in schedule and isinstance(schedule["times"], list) and schedule["times"]:
            time_info = schedule["times"][0]  # Use first time entry
            if "start_time" in time_info:
                transformed["opens_at"] = time_info["start_time"]
            if "end_time" in time_info:
                transformed["closes_at"] = time_info["end_time"]
            # Remove times array after extracting
            transformed.pop("times", None)
        
        # Handle direct start_time/end_time fields
        elif "start_time" in schedule:
            transformed["opens_at"] = schedule["start_time"]
            transformed["closes_at"] = schedule.get("end_time", schedule["start_time"])
            transformed.pop("start_time", None)
            transformed.pop("end_time", None)
        
        # Ensure required fields exist
        if "opens_at" not in transformed or "closes_at" not in transformed:
            # Skip schedules without time information
            return None
        
        # Convert invalid frequency values to valid ones
        if "freq" in transformed:
            freq_value = transformed["freq"].upper()
            if freq_value == "ONCE":
                # Convert ONCE to WEEKLY since database doesn't support ONCE
                transformed["freq"] = "WEEKLY"
                logger.debug(f"Converted schedule frequency from ONCE to WEEKLY")
            elif freq_value not in ["WEEKLY", "MONTHLY"]:
                # Skip schedules with invalid frequency
                logger.warning(f"Skipping schedule with invalid frequency: {freq_value}")
                return None
            else:
                transformed["freq"] = freq_value
            
        # Only return if we have actual freq/wkst data, don't create defaults
        if "freq" not in transformed or "wkst" not in transformed:
            # Log that we're skipping incomplete schedule
            logger.warning(f"Skipping schedule missing freq or wkst: {transformed}")
            return None
            
        return transformed
    
    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON content from markdown code blocks.

        Args:
            text: Text that may contain markdown code blocks

        Returns:
            str: Extracted JSON content or original text if no code blocks found
        """
        # Look for ```json ... ``` blocks
        json_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_block_match:
            extracted = json_block_match.group(1).strip()
            # Clean up common LLM mistakes
            # Replace bare identifiers like "I don't know" with quoted strings
            extracted = re.sub(r":\s*I\s+don\'t\s+know", ': "Unknown"', extracted)
            extracted = re.sub(r":\s*I\s+am\s+not\s+sure", ': "Unknown"', extracted)
            return extracted
        return text

    def process_job_result(self, job_result: JobResult) -> dict[str, Any]:
        """Process completed job result.

        Args:
            job_result: Completed job result to process

        Raises:
            ValueError: If job result has no result
            json.JSONDecodeError: If result text is not valid JSON
        """
        # Parse HSDS data
        if not job_result.result:
            raise ValueError("Job result has no result")

        try:
            # Extract JSON from markdown code blocks if present
            json_text = self._extract_json_from_markdown(job_result.result.text)

            # Additional cleanup for known problematic patterns
            # Fix unquoted values that start with 'I'
            json_text = re.sub(r':\s*I\s+([^",}\]]+)', r': "I \1"', json_text)
            # Fix other bare words that might cause issues
            json_text = re.sub(
                r":\s*([Nn]one|[Uu]nknown|[Nn]/[Aa])(?=\s*[,}])", r': "\1"', json_text
            )

            # Try standard JSON parsing first
            try:
                raw_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                # If standard parsing fails, use demjson3 which is more tolerant
                logger.info(f"Standard JSON parsing failed: {e}")
                logger.debug(
                    f"Attempting to parse with demjson3. First 200 chars: {json_text[:200]}"
                )
                try:
                    raw_data = demjson3.decode(json_text)
                except Exception as demjson_error:
                    # Log the problematic JSON for debugging
                    logger.error(f"demjson3 also failed: {demjson_error}")
                    logger.error(
                        f"Problematic JSON (first 500 chars): {json_text[:500]}"
                    )
                    # Re-raise with more context
                    raise ValueError(
                        f"Failed to parse JSON: {demjson_error}"
                    ) from demjson_error

            # Transform data structure if needed
            # Check if we have a single organization object instead of the expected structure
            if (
                isinstance(raw_data, dict)
                and "name" in raw_data
                and "organization" not in raw_data
            ):
                logger.info("Transforming LLM output to expected structure")

                # Extract services and locations from the organization object
                services = raw_data.pop("services", [])
                locations = raw_data.pop("locations", [])
                
                # Process locations to extract nested coordinates
                for loc in locations:
                    # Check if coordinates are nested in addresses
                    if "addresses" in loc and isinstance(loc.get("addresses"), list) and len(loc["addresses"]) > 0:
                        first_address = loc["addresses"][0]
                        if "coordinates" in first_address and isinstance(first_address["coordinates"], dict):
                            coords = first_address["coordinates"]
                            if "latitude" in coords and "longitude" in coords:
                                # Extract coordinates to location level
                                loc["latitude"] = coords["latitude"]
                                loc["longitude"] = coords["longitude"]
                                # Remove coordinates from addresses since we've extracted them
                                for addr in loc["addresses"]:
                                    if "coordinates" in addr:
                                        del addr["coordinates"]
                    
                    # Also rename addresses to addresss (HSDS uses 3 s's)
                    if "addresses" in loc and "addresss" not in loc:
                        loc["addresss"] = loc.pop("addresses")

                # Create the expected structure
                transformed_data = {
                    # Wrap the organization in a list
                    "organization": [raw_data],
                    "service": services,
                    "location": locations,
                }
                data = cast(HSDataDict, transformed_data)
            else:
                # Handle plural field names from some LLM providers
                if isinstance(raw_data, dict):
                    # Normalize plural names to singular
                    if "organizations" in raw_data and "organization" not in raw_data:
                        logger.info("Converting 'organizations' to 'organization'")
                        raw_data["organization"] = raw_data.pop("organizations")
                    if "services" in raw_data and "service" not in raw_data:
                        logger.info("Converting 'services' to 'service'")
                        services = raw_data.pop("services")
                        # Normalize service field names
                        for svc in services if isinstance(services, list) else []:
                            if "service_name" in svc and "name" not in svc:
                                svc["name"] = svc.pop("service_name")
                        raw_data["service"] = services
                    if "locations" in raw_data and "location" not in raw_data:
                        logger.info("Converting 'locations' to 'location'")
                        locations = raw_data.pop("locations")
                        
                        # Process each location to extract nested coordinates and fix addresses
                        for loc in locations if isinstance(locations, list) else []:
                            # Check if coordinates are nested in addresses
                            if "addresses" in loc and isinstance(loc.get("addresses"), list) and len(loc["addresses"]) > 0:
                                first_address = loc["addresses"][0]
                                if "coordinates" in first_address and isinstance(first_address["coordinates"], dict):
                                    coords = first_address["coordinates"]
                                    if "latitude" in coords and "longitude" in coords:
                                        # Extract coordinates to location level
                                        loc["latitude"] = coords["latitude"]
                                        loc["longitude"] = coords["longitude"]
                                        # Remove coordinates from addresses since we've extracted them
                                        for addr in loc["addresses"]:
                                            if "coordinates" in addr:
                                                del addr["coordinates"]
                            
                            # Also rename addresses to addresss (HSDS uses 3 s's)
                            if "addresses" in loc and "addresss" not in loc:
                                loc["addresss"] = loc.pop("addresses")
                        
                        raw_data["location"] = locations
                    
                    # Extract locations from nested services if needed
                    if "service" in raw_data and isinstance(raw_data["service"], list):
                        all_locations = []
                        for svc in raw_data["service"]:
                            if isinstance(svc, dict) and "locations" in svc:
                                locations = svc.pop("locations")
                                if isinstance(locations, list):
                                    for loc in locations:
                                        # Handle case where location is just a string
                                        if isinstance(loc, str):
                                            # Convert string to location dict
                                            transformed_loc = {
                                                "name": loc,
                                                "description": f"Service location: {loc}"
                                            }
                                            all_locations.append(transformed_loc)
                                            continue
                                        
                                        # Transform location to expected format
                                        transformed_loc = {}
                                        
                                        # Use location_id as name if no name exists
                                        transformed_loc["name"] = loc.get("name") or loc.get("location_id") or f"location_{len(all_locations) + 1}"
                                        transformed_loc["description"] = loc.get("description", f"Service location")
                                        
                                        # Extract coordinates - check multiple possible locations
                                        if "coordinates" in loc:
                                            # Direct coordinates object on location
                                            transformed_loc["latitude"] = loc["coordinates"].get("latitude")
                                            transformed_loc["longitude"] = loc["coordinates"].get("longitude")
                                        elif "addresses" in loc and isinstance(loc.get("addresses"), list) and len(loc["addresses"]) > 0:
                                            # Coordinates nested in addresses array
                                            first_address = loc["addresses"][0]
                                            if "coordinates" in first_address:
                                                coords = first_address["coordinates"]
                                                transformed_loc["latitude"] = coords.get("latitude")
                                                transformed_loc["longitude"] = coords.get("longitude")
                                            else:
                                                transformed_loc["latitude"] = loc.get("latitude")
                                                transformed_loc["longitude"] = loc.get("longitude")
                                        else:
                                            # Direct latitude/longitude on location
                                            transformed_loc["latitude"] = loc.get("latitude")
                                            transformed_loc["longitude"] = loc.get("longitude")
                                        
                                        # Transform address to addresss (triple 's' as per HSDS spec)
                                        if "address" in loc:
                                            # Address is nested
                                            addr = loc["address"]
                                            transformed_loc["addresss"] = [{
                                                "address_1": addr.get("address_1", ""),
                                                "city": addr.get("city", ""),
                                                "state_province": addr.get("state_province", ""),
                                                "postal_code": addr.get("postal_code", ""),
                                                "country": addr.get("country", "US"),
                                                "address_type": "physical"
                                            }]
                                        elif "addresses" in loc:
                                            # Already an array - rename and clean up coordinates
                                            addresses_copy = []
                                            for addr in loc["addresses"]:
                                                addr_copy = dict(addr)
                                                # Remove coordinates from address since we extracted them
                                                if "coordinates" in addr_copy:
                                                    del addr_copy["coordinates"]
                                                addresses_copy.append(addr_copy)
                                            transformed_loc["addresss"] = addresses_copy
                                        elif "address_1" in loc or "city" in loc:
                                            # Address fields are directly on location
                                            transformed_loc["addresss"] = [{
                                                "address_1": loc.get("address_1", ""),
                                                "city": loc.get("city", ""),
                                                "state_province": loc.get("state_province", ""),
                                                "postal_code": loc.get("postal_code", ""),
                                                "country": loc.get("country", "US"),
                                                "address_type": loc.get("address_type", "physical")
                                            }]
                                        
                                        all_locations.append(transformed_loc)
                        
                        if all_locations and "location" not in raw_data:
                            logger.info(f"Extracted and transformed {len(all_locations)} locations from services")
                            raw_data["location"] = all_locations
                    
                    # Check if organization is an object instead of array
                    if "organization" in raw_data:
                        if isinstance(raw_data["organization"], dict):
                            # Convert single organization object to array
                            logger.info("Converting organization from object to array format")
                            raw_data["organization"] = [raw_data["organization"]]
                    
                    # Also check service and location - ensure they are arrays
                    if "service" in raw_data and isinstance(raw_data["service"], dict):
                        raw_data["service"] = [raw_data["service"]]
                    if "location" in raw_data and isinstance(raw_data["location"], dict):
                        raw_data["location"] = [raw_data["location"]]
                
                # Use the data as-is (now normalized)
                data = cast(HSDataDict, raw_data)

            # Log the structure for debugging
            logger.debug(
                "Data structure: organization=%s, service=%s, location=%s",
                "organization" in data,
                "service" in data,
                "location" in data,
            )

            # Track created IDs
            org_id: uuid.UUID | None = None
            location_ids: dict[str, uuid.UUID] = {}
            service_ids: dict[str, uuid.UUID] = {}

            # Initialize creators
            org_creator = OrganizationCreator(self.db)
            location_creator = LocationCreator(self.db)
            service_creator = ServiceCreator(self.db)

            # Process organization
            if "organization" in data and len(data["organization"]) > 0:
                # Use first organization since they should all be the same
                org = data["organization"][0]

                # Ensure description is never null - use name as fallback if no description
                description = org.get("description")
                if description is None or description == "":
                    description = f"Food service organization: {org['name']}"
                    logger.warning(
                        f"Missing description for organization {org['name']}, using generated description"
                    )

                # Check if process_organization method exists (for source-specific handling)
                if hasattr(org_creator, "process_organization"):
                    # Process organization to find a match or create a new one
                    # Convert empty strings and invalid values to None for numeric fields
                    year_inc = org.get("year_incorporated")
                    if isinstance(year_inc, str):
                        year_inc = (
                            int(year_inc)
                            if year_inc.strip() and year_inc.strip().isdigit()
                            else None
                        )
                    elif not isinstance(year_inc, int | type(None)):
                        year_inc = None

                    org_id, is_new_org = org_creator.process_organization(
                        org["name"],
                        description,
                        job_result.job.metadata,
                        website=org.get("website") or None,
                        email=org.get("email") or None,
                        year_incorporated=year_inc,
                        legal_status=org.get("legal_status") or None,
                        uri=org.get("uri") or None,
                    )
                else:
                    # Fall back to old method for backward compatibility with tests
                    # Convert empty strings and invalid values to None for numeric fields
                    year_inc = org.get("year_incorporated")
                    if isinstance(year_inc, str):
                        year_inc = (
                            int(year_inc)
                            if year_inc.strip() and year_inc.strip().isdigit()
                            else None
                        )
                    elif not isinstance(year_inc, int | type(None)):
                        year_inc = None

                    org_id = org_creator.create_organization(
                        org["name"],
                        description,
                        job_result.job.metadata,
                        website=org.get("website") or None,
                        email=org.get("email") or None,
                        year_incorporated=year_inc,
                        legal_status=org.get("legal_status") or None,
                        uri=org.get("uri") or None,
                    )

                # Create organization phones with languages
                if "phones" in org:
                    for phone in org["phones"]:
                        # Use empty strings for missing fields
                        phone_id = service_creator.create_phone(
                            number=phone.get("number", ""),
                            phone_type=phone.get("type", ""),
                            organization_id=org_id,
                            metadata=job_result.job.metadata,
                            transaction=self.db,
                        )
                        # Add phone languages
                        if "languages" in phone:
                            for language in phone["languages"]:
                                service_creator.create_language(
                                    name=language.get("name", ""),
                                    code=language.get("code", ""),
                                    phone_id=phone_id,
                                    metadata=job_result.job.metadata,
                                )

                # Create organization identifiers
                if "organization_identifiers" in org:
                    for identifier in org["organization_identifiers"]:
                        # Use empty strings for missing fields
                        org_creator.create_organization_identifier(
                            org_id,
                            identifier.get("identifier_type", ""),
                            identifier.get("identifier", ""),
                        )
            else:
                # Log a warning if organization list is empty
                logger.warning(
                    f"Empty organization list for scraper_id: {job_result.job.metadata.get('scraper_id', 'unknown')}"
                )

            # Process locations
            if "location" in data:
                for location in data["location"]:
                    # First check if coordinates are nested in addresses structure
                    if "addresses" in location and isinstance(location.get("addresses"), list) and len(location["addresses"]) > 0:
                        first_address = location["addresses"][0]
                        if "coordinates" in first_address and isinstance(first_address["coordinates"], dict):
                            coords = first_address["coordinates"]
                            if "latitude" in coords and "longitude" in coords:
                                # Extract coordinates to location level
                                location["latitude"] = coords["latitude"]
                                location["longitude"] = coords["longitude"]
                                logger.debug(f"Extracted coordinates from nested address structure for location '{location.get('name', 'Unknown')}'")
                    
                    # Also rename addresses to addresss (HSDS uses 3 s's)
                    if "addresses" in location and "addresss" not in location:
                        location["addresss"] = location.pop("addresses")
                        # Remove coordinates from addresss entries since we've extracted them
                        for addr in location.get("addresss", []):
                            if "coordinates" in addr:
                                del addr["coordinates"]
                    
                    # Check that latitude and longitude exist and are not None
                    # Note: 0,0 coordinates are invalid (ocean off Africa) and should be geocoded
                    has_valid_coords = False

                    if (
                        "latitude" in location
                        and "longitude" in location
                        and location["latitude"] is not None
                        and location["longitude"] is not None
                    ):
                        # Check if coordinates are invalid (0,0)
                        lat = float(location["latitude"])
                        lon = float(location["longitude"])
                        if lat == 0.0 and lon == 0.0:
                            logger.warning(
                                f"Location '{location.get('name', 'Unknown')}' has invalid 0,0 coordinates, will attempt geocoding"
                            )
                        else:
                            has_valid_coords = True

                    if has_valid_coords:
                        # Check for existing location by coordinates
                        match_id = location_creator.find_matching_location(
                            float(location["latitude"]), float(location["longitude"])
                        )
                    else:
                        # Try to geocode if we have address information
                        location_name = location.get("name", "Unknown")
                        geocoded_coords = None
                        match_id = None

                        # Check if we have address information
                        if location.get("addresss"):
                            # Build address string from first address (HSDS uses "addresss" with 3 s's)
                            address_data = (
                                location["addresss"][0]
                                if isinstance(location["addresss"], list)
                                else location["addresss"]
                            )
                            address_parts = []

                            if address_data.get("address_1"):
                                address_parts.append(address_data["address_1"])
                            if address_data.get("city"):
                                address_parts.append(address_data["city"])
                            if address_data.get("state_province"):
                                address_parts.append(address_data["state_province"])
                            if address_data.get("postal_code"):
                                address_parts.append(address_data["postal_code"])
                            if address_data.get("country"):
                                address_parts.append(address_data["country"])

                            if address_parts:
                                address_string = ", ".join(address_parts)
                                logger.info(
                                    f"Attempting to geocode location '{location_name}' with address: {address_string}"
                                )

                                try:
                                    # Use the geocoding service directly
                                    from app.core.geocoding import get_geocoding_service

                                    geocoding_service = get_geocoding_service()

                                    # Try primary provider first (usually ArcGIS)
                                    geocoded_coords = geocoding_service.geocode(
                                        address_string
                                    )

                                    # If primary failed and we have fallback, try all providers explicitly
                                    if not geocoded_coords:
                                        logger.info(
                                            f"Primary geocoding failed for '{location_name}', trying all providers"
                                        )

                                        # Try ArcGIS explicitly
                                        geocoded_coords = geocoding_service.geocode(
                                            address_string, force_provider="arcgis"
                                        )

                                        # If ArcGIS failed, try Nominatim
                                        if not geocoded_coords:
                                            geocoded_coords = geocoding_service.geocode(
                                                address_string,
                                                force_provider="nominatim",
                                            )

                                    if geocoded_coords:
                                        logger.info(
                                            f"Successfully geocoded '{location_name}' to {geocoded_coords}"
                                        )
                                        # Update the location data with geocoded coordinates
                                        location["latitude"] = geocoded_coords[0]
                                        location["longitude"] = geocoded_coords[1]
                                        # Continue processing with the new coordinates
                                        match_id = (
                                            location_creator.find_matching_location(
                                                float(location["latitude"]),
                                                float(location["longitude"]),
                                            )
                                        )
                                    else:
                                        logger.error(
                                            f"All geocoding providers failed for location '{location_name}' with address: {address_string}"
                                        )
                                        # Mark this as a critical failure
                                        raise ValueError(
                                            f"Unable to geocode location '{location_name}' - all providers failed"
                                        )
                                except ValueError:
                                    # Re-raise ValueError to handle as job failure
                                    raise
                                except Exception as e:
                                    logger.error(
                                        f"Error geocoding location '{location_name}': {e}"
                                    )

                        # If geocoding failed or no address available
                        if not geocoded_coords:
                            missing_fields = []
                            if (
                                "latitude" not in location
                                or location.get("latitude") is None
                            ):
                                missing_fields.append("latitude")
                            if (
                                "longitude" not in location
                                or location.get("longitude") is None
                            ):
                                missing_fields.append("longitude")
                            
                            # Check if we have meaningful address data that failed to geocode
                            has_address_data = False
                            if location.get("addresss"):
                                first_address = location["addresss"][0] if isinstance(location["addresss"], list) else location["addresss"]
                                # Check if address has meaningful data (not just empty strings)
                                if (first_address.get("address_1") and first_address["address_1"].strip()) or \
                                   (first_address.get("city") and first_address["city"].strip()):
                                    has_address_data = True
                            
                            if has_address_data:
                                # We have real address data but couldn't geocode it - this is an error
                                error_msg = f"Unable to geocode location '{location_name}' with address data - missing coordinates: {', '.join(missing_fields)}"
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                            else:
                                # No meaningful address data and no coordinates - skip this location
                                logger.warning(
                                    f"Skipping location '{location_name}' - no address data and missing coordinates: {', '.join(missing_fields)}"
                                )
                                continue

                    location_id = None
                    if match_id:
                        # Update existing location
                        LOCATION_MATCHES.labels(match_type="exact").inc()
                        # Convert string ID to UUID
                        location_id = uuid.UUID(match_id)

                        # Update location record
                        # Ensure description is never null
                        update_description = location.get("description")
                        if update_description is None or update_description == "":
                            update_description = (
                                f"Food service location: {location['name']}"
                            )
                            logger.warning(
                                f"Missing description for location update {location['name']}, using generated description"
                            )

                        query = text(
                            """
                            UPDATE location
                            SET name=:name,
                                description=:description,
                                latitude=:latitude,
                                longitude=:longitude,
                                organization_id=:organization_id
                            WHERE id=:id
                            """
                        )

                        self.db.execute(
                            query,
                            {
                                "id": str(location_id),
                                "name": location["name"],
                                "description": update_description,
                                "latitude": float(location["latitude"]),
                                "longitude": float(location["longitude"]),
                                "organization_id": str(org_id) if org_id else None,
                            },
                        )
                        self.db.commit()

                        # Create version for update
                        version_tracker = VersionTracker(self.db)
                        version_tracker.create_version(
                            str(location_id),
                            "location",
                            {
                                "name": location["name"],
                                "description": update_description,  # Use the same description as the update
                                "latitude": float(location["latitude"]),
                                "longitude": float(location["longitude"]),
                                "organization_id": str(org_id) if org_id else None,
                                **job_result.job.metadata,
                            },
                            "reconciler",
                            commit=True,
                        )

                    else:
                        # Create new location with all fields
                        # Ensure description is never null
                        loc_description = location.get("description")
                        if loc_description is None or loc_description == "":
                            loc_description = (
                                f"Food service location: {location['name']}"
                            )
                            logger.warning(
                                f"Missing description for location {location['name']}, using generated description"
                            )

                        # Create location returns a string ID, convert to UUID
                        location_id_str = location_creator.create_location(
                            location["name"],
                            loc_description,
                            float(location["latitude"]),
                            float(location["longitude"]),
                            job_result.job.metadata,
                            str(org_id) if org_id else None,
                        )
                        location_id = uuid.UUID(location_id_str)

                        # Create location addresses for both new and existing locations (HSDS spec uses "addresss" with 3 s's)
                        if "addresss" in location and location_id:
                            location_id_str = str(location_id)

                            # Check if addresses already exist for this location
                            existing_addresses_query = text(
                                "SELECT COUNT(*) FROM address WHERE location_id = :location_id"
                            )
                            result = self.db.execute(
                                existing_addresses_query,
                                {"location_id": location_id_str},
                            )
                            row = result.first()
                            address_count = row[0] if row else 0

                            # Only create addresses if none exist
                            if address_count == 0:
                                for address in location["addresss"]:
                                    # Ensure required address fields are never null by using empty strings
                                    # These will be updated later based on lat/long
                                    location_creator.create_address(
                                        address_1=address.get("address_1", ""),
                                        city=address.get("city", ""),
                                        state_province=address.get(
                                            "state_province", ""
                                        ),
                                        postal_code=address.get("postal_code", ""),
                                        country=address.get("country", ""),
                                        address_type=address.get(
                                            "address_type", "physical"
                                        ),
                                        location_id=location_id_str,
                                        metadata=job_result.job.metadata,
                                    )

                        # Create location phones with languages (for both new and existing locations)
                        if "phones" in location and location_id:
                            for phone in location["phones"]:
                                # Use empty strings for missing fields
                                phone_id = service_creator.create_phone(
                                    number=phone.get("number", ""),
                                    phone_type=phone.get("type", ""),
                                    location_id=location_id,  # Pass UUID
                                    metadata=job_result.job.metadata,
                                    transaction=self.db,
                                )
                                # Add phone languages
                                if "languages" in phone:
                                    for language in phone["languages"]:
                                        service_creator.create_language(
                                            name=language.get("name", ""),
                                            code=language.get("code", ""),
                                            phone_id=phone_id,
                                            metadata=job_result.job.metadata,
                                        )

                        # Create location accessibility (for both new and existing locations)
                        if "accessibility" in location and location_id:
                            location_id_str = str(location_id)
                            for access in location["accessibility"]:
                                location_creator.create_accessibility(
                                    location_id=location_id_str,
                                    description=access.get("description"),
                                    details=access.get("details"),
                                    url=access.get("url"),
                                    metadata=job_result.job.metadata,
                                )

                        # Store UUID in location_ids dictionary
                        location_ids[location["name"]] = location_id

            # Process services (both top-level and organization-nested)
            services_to_process: list[ServiceDict] = []

            # Add top-level services if present
            if "service" in data:
                # Handle services as either strings or dicts
                for service_item in data["service"]:
                    if isinstance(service_item, str):
                        # Convert string to ServiceDict format
                        service_dict: ServiceDict = {
                            "name": service_item,
                            "description": f"Food service: {service_item}",
                            "phones": [],
                            "languages": [],
                            "schedules": [],
                        }
                        services_to_process.append(service_dict)
                    else:
                        # Already a dict, use as-is
                        services_to_process.append(service_item)

            # Add services from organizations if present
            if "organization" in data and len(data["organization"]) > 0:
                for org in data["organization"]:
                    if "services" in org:
                        # Handle services as either strings or dicts
                        for service_item in org["services"]:
                            if isinstance(service_item, str):
                                # Convert string to ServiceDict format
                                service_dict: ServiceDict = {
                                    "name": service_item,
                                    "description": f"Food service: {service_item}",
                                    "phones": [],
                                    "languages": [],
                                    "schedules": [],
                                }
                                services_to_process.append(service_dict)
                            else:
                                # Already a dict, use as-is
                                services_to_process.append(service_item)

            # Process all collected services
            for service in services_to_process:
                # Ensure service has a name
                if "name" not in service or not service.get("name"):
                    service["name"] = service.get("service_name") or "Food Service"
                    logger.warning(f"Missing name for service, using default: {service['name']}")
                
                # Ensure description is never null - use name as fallback if no description
                service_description = service.get("description")
                if service_description is None or service_description == "":
                    service_description = f"Food service: {service['name']}"
                    logger.warning(
                        f"Missing description for service {service['name']}, using generated description"
                    )

                # Check if process_service method exists (for source-specific handling)
                if hasattr(service_creator, "process_service"):
                    # Process service to find a match or create a new one
                    service_id, is_new_service = service_creator.process_service(
                        service["name"],
                        service_description,
                        org_id,
                        job_result.job.metadata,
                    )
                else:
                    # Fall back to old method for backward compatibility with tests
                    service_id = service_creator.create_service(
                        service["name"],
                        service_description,
                        org_id,
                        job_result.job.metadata,
                    )
                    is_new_service = True  # Assume new service for simplicity

                # Create service phones with languages
                if "phones" in service:
                    for phone in service["phones"]:
                        # Use empty strings for missing fields
                        phone_id = service_creator.create_phone(
                            number=phone.get("number", ""),
                            phone_type=phone.get("type", ""),
                            service_id=service_id,
                            metadata=job_result.job.metadata,
                            transaction=self.db,
                        )
                        # Add phone languages
                        if "languages" in phone:
                            for language in phone["languages"]:
                                service_creator.create_language(
                                    name=language.get("name", ""),
                                    code=language.get("code", ""),
                                    phone_id=phone_id,
                                    metadata=job_result.job.metadata,
                                )

                # Create service languages
                if "languages" in service:
                    for language in service["languages"]:
                        service_creator.create_language(
                            name=language.get("name", ""),
                            code=language.get("code", ""),
                            service_id=service_id,
                            metadata=job_result.job.metadata,
                        )

                if is_new_service:  # Only increment for new services
                    SERVICE_RECORDS.labels(
                        has_organization="true" if org_id else "false"
                    ).inc()
                service_ids[service["name"]] = service_id

                # Link service to locations and create schedules
                if "location" in data:
                    for loc in data["location"]:
                        # Get location identifier - could be 'name' or fallback to other fields
                        loc_identifier = loc.get("name")
                        if not loc_identifier:
                            continue  # Skip if no identifier
                        
                        if loc_identifier in location_ids:
                            # Check for existing service_at_location
                            query = text(
                                """
                                SELECT id FROM service_at_location
                                WHERE service_id=:service_id
                                AND location_id=:location_id
                                LIMIT 1
                                """
                            )
                            result = self.db.execute(
                                query,
                                {
                                    "service_id": str(service_id),
                                    "location_id": str(location_ids[loc["name"]]),
                                },
                            )
                            row = result.first()

                            if not row:
                                # Create new service_at_location with service description
                                # Ensure description is never null
                                sal_description = service.get("description")
                                if sal_description is None or sal_description == "":
                                    sal_description = f"Food service at {loc['name']}: {service['name']}"
                                    logger.warning(
                                        f"Missing description for service_at_location {service['name']} at {loc['name']}, using generated description"
                                    )

                                sal_id = service_creator.create_service_at_location(
                                    service_id,
                                    location_ids[loc["name"]],
                                    sal_description,
                                    job_result.job.metadata,
                                )
                                if sal_id:  # Only increment if creation was successful
                                    SERVICE_LOCATION_LINKS.labels(
                                        location_match_type="exact"
                                    ).inc()

                                    # Collect all schedules from service and location
                                    schedules_to_create: list[ScheduleDict] = []

                                    # Add service schedules (transform format if needed)
                                    if "schedules" in service:
                                        for sched in service["schedules"]:
                                            transformed_sched = self._transform_schedule(sched)
                                            if transformed_sched:
                                                schedules_to_create.append(transformed_sched)

                                    # Add location schedules if they don't overlap with service schedules
                                    if "schedules" in loc:
                                        loc_schedules = loc["schedules"]
                                        for loc_schedule in loc_schedules:
                                            transformed_sched = self._transform_schedule(loc_schedule)
                                            if not transformed_sched:
                                                continue
                                            loc_schedule = transformed_sched
                                            # Check if this schedule already exists
                                            exists = False
                                            for existing in schedules_to_create:
                                                if (
                                                    existing["freq"]
                                                    == loc_schedule["freq"]
                                                    and existing["wkst"]
                                                    == loc_schedule["wkst"]
                                                    and existing["opens_at"]
                                                    == loc_schedule["opens_at"]
                                                    and existing["closes_at"]
                                                    == loc_schedule["closes_at"]
                                                ):
                                                    exists = True
                                                    break
                                            if not exists:
                                                schedules_to_create.append(loc_schedule)

                                    # Create unique schedules for this service_at_location
                                    for schedule in schedules_to_create:
                                        # For weekly schedules, set byday to the same as wkst
                                        # This ensures the schedule shows up in the correct day
                                        byday = (
                                            schedule["wkst"]
                                            if schedule["freq"] == "WEEKLY"
                                            else None
                                        )

                                        # Create a human-readable description of the schedule
                                        description = (
                                            f"Open {schedule['opens_at']} to {schedule['closes_at']} "
                                            f"every {schedule['wkst']}"
                                        )

                                        service_creator.create_schedule(
                                            freq=schedule["freq"],
                                            wkst=schedule["wkst"],
                                            opens_at=schedule["opens_at"],
                                            closes_at=schedule["closes_at"],
                                            service_at_location_id=sal_id,
                                            metadata=job_result.job.metadata,
                                            byday=byday,
                                            description=description,
                                        )

            # Update success metric and return result
            scraper_id = job_result.job.metadata.get("scraper_id", "unknown")
            RECONCILER_JOBS.labels(scraper_id=scraper_id, status="success").inc()

            return {
                "status": "success",
                "scraper_id": scraper_id,
                "organization_id": str(org_id) if org_id else None,
                "location_ids": {k: str(v) for k, v in location_ids.items()},
                "service_ids": {k: str(v) for k, v in service_ids.items()},
            }

        except Exception as e:
            # Update failure metric and re-raise
            scraper_id = job_result.job.metadata.get("scraper_id", "unknown")
            RECONCILER_JOBS.labels(scraper_id=scraper_id, status="failure").inc()

            error_result: dict[str, str] = {
                "status": "error",
                "scraper_id": scraper_id,
                "error": str(e),
            }
            raise ValueError(json.dumps(error_result)) from e
