"""Job processing utilities for the reconciler."""

import json
import logging
import re
import uuid
from typing import Any, cast
from uuid import UUID

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
    address: list[
        dict[str, Any]
    ]  # Fixed: HSDS JSON schema uses "address" (CSV had typo)
    phones: list[dict[str, Any]]
    schedules: list[ScheduleDict]
    accessibility: list[dict[str, Any]]


class HSDataDict(TypedDict):
    """Type definition for HSDS data."""

    organization: list[OrganizationDict]
    service: list[ServiceDict]
    location: list[LocationDict]


def validate_website(website: str | None) -> str | None:
    """Validate and clean website URL.

    Args:
        website: The website URL to validate

    Returns:
        Cleaned website URL or None if invalid/too long
    """
    if not website:
        return None

    # Strip whitespace
    website = website.strip()

    # If it doesn't start with http:// or https://, add http://
    if not website.startswith(("http://", "https://")):
        # Check if it looks like a domain (has dots and valid characters)
        domain_pattern = r"^[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(/.*)?$"
        if re.match(domain_pattern, website):
            website = "http://" + website
            logger.debug(f"Added http:// prefix to website: {website}")
        else:
            logger.warning(f"Invalid website URL format, dropping: {website[:100]}...")
            return None

    # Check length after potential http:// addition
    if len(website) > 255:
        logger.warning(
            f"Website URL too long ({len(website)} chars), dropping: {website[:100]}..."
        )
        return None

    # Final validation - must be a proper URL now
    # Pattern: https? means "http" with optional "s", so matches both http:// and https://
    url_pattern = r"^https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(/.*)?$"
    if not re.match(url_pattern, website):
        logger.warning(
            f"Invalid website URL format after processing, dropping: {website[:100]}..."
        )
        return None

    return website


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
        if (
            "times" in schedule
            and isinstance(schedule["times"], list)
            and schedule["times"]
        ):
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
                # Convert ONCE to a proper one-time event representation per HSDS spec
                transformed["freq"] = "WEEKLY"

                # Set count to 1 to indicate single occurrence
                transformed["count"] = 1

                # If dtstart is available, also set until to the same date
                if "dtstart" in transformed:
                    transformed["until"] = transformed["dtstart"]

                # If we have valid_from but not valid_to, set them the same
                if "valid_from" in transformed and "valid_to" not in transformed:
                    transformed["valid_to"] = transformed["valid_from"]

                logger.debug("Converted one-time event: ONCE -> WEEKLY with count=1")
            elif freq_value not in ["WEEKLY", "MONTHLY"]:
                # Skip schedules with invalid frequency
                logger.warning(
                    f"Skipping schedule with invalid frequency: {freq_value}"
                )
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
        # Check for validation data in job_result.data (from validator)
        validation_data = None
        if hasattr(job_result, "data") and job_result.data:
            # Extract validation data from enriched job_result
            validation_data = job_result.data
            logger.info(
                f"Found validation data in job_result.data with {len(validation_data)} keys"
            )

        # Parse HSDS data
        if not job_result.result:
            raise ValueError("Job result has no result")

        if not job_result.result.text or job_result.result.text.strip() == "":
            raise ValueError("Job result has empty text")

        try:
            # Extract JSON from markdown code blocks if present
            json_text = self._extract_json_from_markdown(job_result.result.text)

            # Check if we got empty text after extraction
            if not json_text or json_text.strip() == "":
                raise ValueError(
                    f"Empty JSON text after extraction from: {job_result.result.text[:200]}"
                )

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

            # With structured outputs, data should already be in HSDS format
            if not isinstance(raw_data, dict):
                raise ValueError(
                    f"Expected dict with HSDS structure but got {type(raw_data)}"
                )

            # Validate and ensure we have the expected HSDS structure with three top-level arrays
            required_fields = ["organization", "service", "location"]
            missing_fields = [f for f in required_fields if f not in raw_data]

            if missing_fields:
                logger.warning(
                    f"Missing HSDS fields: {missing_fields}. Found: {list(raw_data.keys())}"
                )
                # Create empty arrays for missing fields
                for field in required_fields:
                    if field not in raw_data:
                        raw_data[field] = []

            # Ensure all top-level fields are arrays (convert single objects to arrays if needed)
            for field in required_fields:
                if field in raw_data:
                    if not isinstance(raw_data[field], list):
                        logger.info(f"Converting {field} from object to array")
                        raw_data[field] = [raw_data[field]]

            # Use the data as-is (already in HSDS format)
            data = cast(HSDataDict, raw_data)

            logger.info(
                f"Processing HSDS data: {len(data.get('organization', []))} orgs, "
                f"{len(data.get('service', []))} services, "
                f"{len(data.get('location', []))} locations, "
                f"{len(data.get('phone', []))} phones, "
                f"{len(data.get('schedule', []))} schedules"
            )

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

            # Initialize ID mappings for foreign key resolution
            # Map entity names (and old IDs) to created UUIDs
            org_name_map: dict[str, UUID] = {}  # Maps org names to created UUIDs
            service_id_map: dict[str, UUID] = (
                {}
            )  # Maps service names/IDs to created UUIDs
            service_at_location_id_map: dict[str, UUID] = (
                {}
            )  # Maps SAL names/IDs to created UUIDs

            # Process organization
            if "organization" in data and len(data["organization"]) > 0:
                # Use first organization since they should all be the same
                org = data["organization"][0]

                # Ensure organization has a name
                if "name" not in org or not org.get("name"):
                    org["name"] = "Food Service Organization"
                    logger.warning(
                        f"Missing name for organization, using default: {org['name']}"
                    )

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

                    # Extract confidence data if available
                    org_confidence_score = None
                    org_validation_status = None
                    org_validation_notes = None

                    if validation_data and "organization" in validation_data:
                        for val_org in validation_data["organization"]:
                            if val_org.get("name") == org["name"]:
                                org_confidence_score = val_org.get("confidence_score")
                                org_validation_status = val_org.get("validation_status")
                                org_validation_notes = val_org.get("validation_notes")
                                if org_confidence_score:
                                    logger.info(
                                        f"Organization '{org['name']}' has confidence score: {org_confidence_score}"
                                    )
                                break

                    # Extract first location's coordinates for proximity matching
                    first_latitude = None
                    first_longitude = None
                    if "location" in data and len(data["location"]) > 0:
                        first_location = data["location"][0]
                        # Try to get coordinates from various possible structures
                        if (
                            "latitude" in first_location
                            and "longitude" in first_location
                        ):
                            first_latitude = (
                                float(first_location["latitude"])
                                if first_location["latitude"]
                                else None
                            )
                            first_longitude = (
                                float(first_location["longitude"])
                                if first_location["longitude"]
                                else None
                            )
                        elif "coordinates" in first_location and isinstance(
                            first_location["coordinates"], dict
                        ):
                            coords = first_location["coordinates"]
                            first_latitude = (
                                float(coords["latitude"])
                                if coords.get("latitude")
                                else None
                            )
                            first_longitude = (
                                float(coords["longitude"])
                                if coords.get("longitude")
                                else None
                            )

                        if first_latitude and first_longitude:
                            logger.debug(
                                f"Using location ({first_latitude}, {first_longitude}) for organization proximity matching"
                            )

                    org_id, is_new_org = org_creator.process_organization(
                        org["name"],
                        description,
                        job_result.job.metadata,
                        website=validate_website(org.get("website")),
                        email=org.get("email") or None,
                        year_incorporated=year_inc,
                        legal_status=org.get("legal_status") or None,
                        uri=org.get("uri") or None,
                        confidence_score=org_confidence_score,
                        validation_status=org_validation_status,
                        validation_notes=org_validation_notes,
                        latitude=first_latitude,
                        longitude=first_longitude,
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

                    # Extract confidence data if available (for backward compatibility)
                    org_confidence_score = None
                    org_validation_status = None
                    org_validation_notes = None

                    if validation_data and "organization" in validation_data:
                        for val_org in validation_data["organization"]:
                            if val_org.get("name") == org["name"]:
                                org_confidence_score = val_org.get("confidence_score")
                                org_validation_status = val_org.get("validation_status")
                                org_validation_notes = val_org.get("validation_notes")
                                break

                    org_id = org_creator.create_organization(
                        org["name"],
                        description,
                        job_result.job.metadata,
                        website=validate_website(org.get("website")),
                        email=org.get("email") or None,
                        year_incorporated=year_inc,
                        legal_status=org.get("legal_status") or None,
                        uri=org.get("uri") or None,
                        confidence_score=org_confidence_score,
                        validation_status=org_validation_status,
                        validation_notes=org_validation_notes,
                    )

                # Store organization name mapping (ignore LLM-provided IDs)
                if org_id and org.get("name"):
                    org_name_map[org["name"]] = org_id
                    logger.debug(
                        f"Mapped organization '{org['name']}' to UUID {org_id}"
                    )

                # Try to extract phone numbers from text if none provided
                # Check if phones is None (missing) or empty list
                if org.get("phones") is None or len(org.get("phones", [])) == 0:
                    # Try to extract from various text fields
                    extracted_phones = []
                    phone_patterns = [
                        r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",  # (123) 456-7890
                        r"\d{3}[-.\s]\d{3}[-.\s]\d{4}",  # 123-456-7890
                        r"\d{10}",  # 1234567890
                        r"1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",  # 1-123-456-7890
                        r"1[-.\s]?8\d{2}[-.\s]?[A-Z]{3}[-.\s]?[A-Z]{4}",  # 1-800-FLOWERS vanity
                    ]

                    # Search in various fields including year_incorporated and legal_status
                    search_fields = [
                        "description",
                        "email",
                        "website",
                        "alternate_name",
                        "year_incorporated",
                        "legal_status",
                    ]
                    search_text = ""
                    for field in search_fields:
                        if org.get(field):
                            search_text += " " + str(org[field])

                    if search_text:
                        for pattern in phone_patterns:
                            matches = re.findall(pattern, search_text)
                            for match in matches:
                                # Avoid duplicates
                                if match not in [
                                    p.get("number") for p in extracted_phones
                                ]:
                                    extracted_phones.append(
                                        {
                                            "number": match,
                                            "type": "voice",
                                            "languages": [],  # Empty array, now optional
                                        }
                                    )

                        if extracted_phones:
                            org["phones"] = extracted_phones
                            logger.info(
                                f"Extracted {len(extracted_phones)} phone numbers from text for organization '{org.get('name', 'Unknown')}'"
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
                    # Extract validation data for this location
                    # First check if validation data is directly on the location (from validator)
                    loc_confidence_score = location.get("confidence_score")
                    loc_validation_status = location.get("validation_status")
                    loc_validation_notes = location.get("validation_notes")
                    loc_geocoding_source = location.get("geocoding_source")

                    # Log if we found validation data directly on location
                    if loc_confidence_score is not None:
                        logger.info(
                            f"Location '{location.get('name')}' has confidence score: {loc_confidence_score}, "
                            f"status: {loc_validation_status}"
                        )

                    # If not found directly, look in separate validation_data
                    elif validation_data and "location" in validation_data:
                        for val_loc in validation_data["location"]:
                            # Match by name and coordinates if available
                            if val_loc.get("name") == location.get("name") or (
                                location.get("latitude")
                                and location.get("longitude")
                                and abs(
                                    float(val_loc.get("latitude", 0))
                                    - float(location.get("latitude", 0))
                                )
                                < settings.RECONCILER_LOCATION_TOLERANCE
                                and abs(
                                    float(val_loc.get("longitude", 0))
                                    - float(location.get("longitude", 0))
                                )
                                < settings.RECONCILER_LOCATION_TOLERANCE
                            ):
                                loc_confidence_score = val_loc.get("confidence_score")
                                loc_validation_status = val_loc.get("validation_status")
                                loc_validation_notes = val_loc.get("validation_notes")
                                loc_geocoding_source = val_loc.get("geocoding_source")

                                if loc_confidence_score:
                                    logger.info(
                                        f"Location '{location.get('name')}' has confidence score: {loc_confidence_score}, "
                                        f"status: {loc_validation_status}"
                                    )
                                break

                    # Skip locations marked as rejected by validator
                    if loc_validation_status == "rejected":
                        logger.warning(
                            f"Location '{location.get('name')}' rejected: "
                            f"confidence={loc_confidence_score}, notes={loc_validation_notes}"
                        )
                        # Skip this location entirely - it won't be created in the database
                        continue
                    # Check if coordinates are directly on location (from array format)
                    if "coordinates" in location and isinstance(
                        location["coordinates"], dict
                    ):
                        coords = location["coordinates"]
                        if "latitude" in coords and "longitude" in coords:
                            # Extract coordinates to location level
                            location["latitude"] = coords["latitude"]
                            location["longitude"] = coords["longitude"]
                            # Remove the coordinates dict since we've extracted them
                            del location["coordinates"]
                            logger.debug(
                                f"Extracted coordinates from location object for '{location.get('name', 'Unknown')}'"
                            )
                    # Also check if coordinates are nested in addresses structure
                    elif (
                        "addresses" in location
                        and isinstance(location.get("addresses"), list)
                        and len(location["addresses"]) > 0
                    ):
                        first_address = location["addresses"][0]
                        if "coordinates" in first_address and isinstance(
                            first_address["coordinates"], dict
                        ):
                            coords = first_address["coordinates"]
                            if "latitude" in coords and "longitude" in coords:
                                # Extract coordinates to location level
                                location["latitude"] = coords["latitude"]
                                location["longitude"] = coords["longitude"]
                                logger.debug(
                                    f"Extracted coordinates from nested address structure for location '{location.get('name', 'Unknown')}'"
                                )

                    # Handle address fields directly on location (from array format)
                    if "address_1" in location or "city" in location:
                        # Create address array from direct fields
                        if "address" not in location:
                            location["address"] = [
                                {
                                    "address_1": location.pop("address_1", ""),
                                    "city": location.pop("city", ""),
                                    "state_province": location.pop(
                                        "state_province", ""
                                    ),
                                    "postal_code": location.pop("postal_code", ""),
                                    "country": location.pop("country", "US"),
                                    "address_type": "physical",
                                }
                            ]
                            logger.debug(
                                f"Created address array from direct fields for location '{location.get('name', 'Unknown')}'"
                            )
                    # Rename addresses to address (fixed from CSV typo)
                    elif "addresses" in location and "address" not in location:
                        location["address"] = location.pop("addresses")
                        # Remove coordinates from address entries since we've extracted them
                        for addr in location.get("address", []):
                            if "coordinates" in addr:
                                del addr["coordinates"]

                    # Trust the validator's coordinates - no geocoding needed here
                    # The validator has already enriched and validated coordinates
                    if (
                        "latitude" in location
                        and "longitude" in location
                        and location["latitude"] is not None
                        and location["longitude"] is not None
                    ):
                        # Check for existing location by coordinates
                        match_id = location_creator.find_matching_location(
                            float(location["latitude"]), float(location["longitude"])
                        )
                    else:
                        # No coordinates from validator - this location should have been rejected
                        location_name = location.get("name", "Unknown")
                        logger.warning(
                            f"Skipping location '{location_name}' - no coordinates after validation"
                        )
                        continue

                    location_id = None
                    if match_id:
                        # Update existing location
                        LOCATION_MATCHES.labels(match_type="exact").inc()
                        # Convert string ID to UUID
                        location_id = uuid.UUID(match_id)

                        # Check if location name is just the city name (common LLM issue)
                        if "address" in location and location["address"]:
                            first_addr = (
                                location["address"][0]
                                if isinstance(location["address"], list)
                                else location["address"]
                            )
                            city = first_addr.get("city", "")

                            # If the location name equals the city name, it's likely wrong
                            if location["name"] == city and city:
                                # Don't update the name to the city - keep existing name
                                # Get the current name from database
                                query = text("SELECT name FROM location WHERE id = :id")
                                result = self.db.execute(
                                    query, {"id": str(location_id)}
                                )
                                row = result.first()
                                if row and row[0] and row[0] != city:
                                    # Keep existing name if it's not the city name
                                    logger.info(
                                        f"Keeping existing location name '{row[0]}' instead of city name '{city}'"
                                    )
                                    location["name"] = row[0]

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

                        # Create/update location_source entry for this scraper
                        # This ensures every scraper that finds a location is recorded
                        location_creator.create_location_source(
                            str(location_id),
                            job_result.job.metadata.get("scraper_id", "unknown"),
                            location["name"],
                            update_description,
                            float(location["latitude"]),
                            float(location["longitude"]),
                            job_result.job.metadata,
                        )

                    else:
                        # Create new location with all fields
                        # Ensure location has a name
                        if "name" not in location or not location.get("name"):
                            location["name"] = f"Location {len(location_ids) + 1}"
                            logger.warning(
                                f"Missing name for location, using default: {location['name']}"
                            )

                        # Check if location name is just the city name (common LLM issue)
                        # If so, try to use a better name from the original data
                        if "address" in location and location["address"]:
                            first_addr = (
                                location["address"][0]
                                if isinstance(location["address"], list)
                                else location["address"]
                            )
                            city = first_addr.get("city", "")

                            # If the location name equals the city name, it's likely wrong
                            if location["name"] == city and city:
                                # Try to extract a better name from description or other fields
                                better_name = None

                                # Check if description has a better name pattern
                                if location.get("description"):
                                    # Look for patterns like "Food service location: [Real Name]"
                                    import re

                                    match = re.search(
                                        r"Food service location:\s*(.+)",
                                        location.get("description", ""),
                                    )
                                    if match:
                                        better_name = match.group(1).strip()

                                # If we found a better name, use it
                                if better_name and better_name != city:
                                    logger.info(
                                        f"Fixing location name from '{location['name']}' to '{better_name}' (was using city name)"
                                    )
                                    location["name"] = better_name
                                else:
                                    # Log warning but keep the city name for now
                                    logger.warning(
                                        f"Location name '{location['name']}' matches city name, may be incorrect"
                                    )

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
                            confidence_score=loc_confidence_score,
                            validation_status=loc_validation_status,
                            validation_notes=loc_validation_notes,
                            geocoding_source=loc_geocoding_source,
                        )
                        location_id = uuid.UUID(location_id_str)

                        # Create location addresses for both new and existing locations
                        if "address" in location and location_id:
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
                                for address in location["address"]:
                                    # Ensure country defaults to US if not provided
                                    country = address.get("country", "US")
                                    if not country or country == "":
                                        country = "US"

                                    # Create address without any geocoding - validator already enriched the data
                                    location_creator.create_address(
                                        address_1=address.get("address_1", ""),
                                        city=address.get("city", ""),
                                        state_province=address.get(
                                            "state_province", ""
                                        ),
                                        postal_code=address.get("postal_code", ""),
                                        country=country,
                                        address_type=address.get(
                                            "address_type", "physical"
                                        ),
                                        location_id=location_id_str,
                                        metadata=job_result.job.metadata,
                                    )

                        # Try to extract phone numbers from location text if none provided
                        if location_id and (
                            not location.get("phones")
                            or len(location.get("phones", [])) == 0
                        ):
                            # Try to extract from location fields
                            extracted_phones = []
                            phone_patterns = [
                                r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",  # (123) 456-7890
                                r"\d{3}[-.\s]\d{3}[-.\s]\d{4}",  # 123-456-7890
                                r"\d{10}",  # 1234567890
                                r"1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",  # 1-800-123-4567
                                r"1[-.\s]?8\d{2}[-.\s]?[A-Z]{3}[-.\s]?[A-Z]{4}",  # 1-800-FLOWERS vanity
                            ]

                            # Search in more location fields including website
                            search_text = ""
                            for field in [
                                "name",
                                "description",
                                "transportation",
                                "alternate_name",
                                "website",
                            ]:
                                if location.get(field):
                                    search_text += " " + str(location[field])

                            if search_text:
                                for pattern in phone_patterns:
                                    matches = re.findall(pattern, search_text)
                                    for match in matches:
                                        if match not in [
                                            p.get("number") for p in extracted_phones
                                        ]:
                                            extracted_phones.append(
                                                {
                                                    "number": match,
                                                    "type": "voice",
                                                    "languages": [],
                                                }
                                            )

                                if extracted_phones:
                                    location["phones"] = extracted_phones
                                    logger.info(
                                        f"Extracted {len(extracted_phones)} phone numbers for location '{location.get('name', 'Unknown')}'"
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
                        if (
                            "accessibility" in location
                            and location_id
                            and location["accessibility"]
                        ):
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
                    logger.warning(
                        f"Missing name for service, using default: {service['name']}"
                    )

                # Ensure description is never null - use name as fallback if no description
                service_description = service.get("description")
                if service_description is None or service_description == "":
                    service_description = f"Food service: {service['name']}"
                    logger.warning(
                        f"Missing description for service {service['name']}, using generated description"
                    )

                # Extract validation data for this service
                svc_confidence_score = None
                svc_validation_status = None
                svc_validation_notes = None

                if validation_data and "service" in validation_data:
                    for val_svc in validation_data["service"]:
                        if val_svc.get("name") == service["name"]:
                            svc_confidence_score = val_svc.get("confidence_score")
                            svc_validation_status = val_svc.get("validation_status")
                            svc_validation_notes = val_svc.get("validation_notes")
                            if svc_confidence_score:
                                logger.info(
                                    f"Service '{service['name']}' has confidence score: {svc_confidence_score}"
                                )
                            break

                # Check if process_service method exists (for source-specific handling)
                if hasattr(service_creator, "process_service"):
                    # Process service to find a match or create a new one
                    service_id, is_new_service = service_creator.process_service(
                        service["name"],
                        service_description,
                        org_id,
                        job_result.job.metadata,
                        confidence_score=svc_confidence_score,
                        validation_status=svc_validation_status,
                        validation_notes=svc_validation_notes,
                    )
                else:
                    # Fall back to old method for backward compatibility with tests
                    service_id = service_creator.create_service(
                        service["name"],
                        service_description,
                        org_id,
                        job_result.job.metadata,
                        confidence_score=svc_confidence_score,
                        validation_status=svc_validation_status,
                        validation_notes=svc_validation_notes,
                    )
                    is_new_service = True  # Assume new service for simplicity

                # Store the mapping from service name to created UUID
                # Ignore any LLM-provided IDs - we generate our own
                if service.get("name"):
                    service_id_map[service["name"]] = service_id
                    logger.debug(
                        f"Mapped service '{service['name']}' to UUID {service_id}"
                    )

                # Also store by LLM ID if provided (for backward compatibility)
                if service.get("id"):
                    service_id_map[service["id"]] = service_id

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
                                            transformed_sched = (
                                                self._transform_schedule(sched)
                                            )
                                            if transformed_sched:
                                                schedules_to_create.append(
                                                    transformed_sched
                                                )

                                    # Add location schedules if they don't overlap with service schedules
                                    if "schedules" in loc:
                                        loc_schedules = loc["schedules"]
                                        for loc_schedule in loc_schedules:
                                            transformed_sched = (
                                                self._transform_schedule(loc_schedule)
                                            )
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

                                    # Create or update schedules for this service_at_location
                                    for schedule in schedules_to_create:
                                        # Get byday from the schedule data if available
                                        # Validate schedule exists and is a dict
                                        if schedule and isinstance(schedule, dict):
                                            byday = schedule.get("byday")
                                        else:
                                            byday = None
                                            logger.warning(
                                                "Invalid schedule data, skipping byday extraction"
                                            )

                                        # Create a human-readable description of the schedule
                                        if byday:
                                            # Convert RRULE format to readable format
                                            day_map = {
                                                "MO": "Monday",
                                                "TU": "Tuesday",
                                                "WE": "Wednesday",
                                                "TH": "Thursday",
                                                "FR": "Friday",
                                                "SA": "Saturday",
                                                "SU": "Sunday",
                                            }
                                            days = [
                                                day_map.get(d.strip(), d.strip())
                                                for d in byday.split(",")
                                            ]
                                            days_str = ", ".join(days)
                                            description = (
                                                f"Open {schedule['opens_at']} to {schedule['closes_at']} "
                                                f"on {days_str}"
                                            )
                                        else:
                                            description = (
                                                f"Open {schedule['opens_at']} to {schedule['closes_at']} "
                                                f"every {schedule['wkst']}"
                                            )

                                        schedule_id, was_updated = (
                                            service_creator.update_or_create_schedule(
                                                freq=schedule["freq"],
                                                wkst=schedule["wkst"],
                                                opens_at=schedule["opens_at"],
                                                closes_at=schedule["closes_at"],
                                                service_at_location_id=sal_id,
                                                metadata=job_result.job.metadata,
                                                byday=byday,
                                                description=description,
                                            )
                                        )
                                        if was_updated:
                                            logger.info(
                                                f"Updated schedule {schedule_id} with new data including byday: {byday}"
                                            )

            # Log available top-level keys for debugging
            logger.debug(f"Available top-level keys in data: {list(data.keys())}")

            # Process top-level phone array if present
            if "phone" in data:
                logger.info(
                    f"Processing {len(data['phone'])} phone records from top-level array"
                )
                for phone in data["phone"]:
                    # Map original IDs to actual database IDs
                    org_id_for_phone = None
                    service_id_for_phone = None
                    location_id_for_phone = None

                    # Try to map relationships - prefer names over IDs
                    if phone.get("organization_id") or phone.get("organization_name"):
                        ref = phone.get("organization_name") or phone.get(
                            "organization_id"
                        )
                        # Try name mapping first
                        org_id_for_phone = org_name_map.get(ref)
                        if not org_id_for_phone:
                            # Default to the main org if reference not found
                            org_id_for_phone = org_id if org_id else None
                            if ref:
                                logger.debug(
                                    f"Could not map organization reference '{ref}' for phone, using main org"
                                )

                    if phone.get("service_id") or phone.get("service_name"):
                        ref = phone.get("service_name") or phone.get("service_id")
                        # Try mapping by name or ID
                        service_id_for_phone = service_id_map.get(ref)
                        if not service_id_for_phone:
                            logger.warning(
                                f"Could not map service reference '{ref}' for phone, using org ID instead"
                            )
                            org_id_for_phone = org_id if org_id else None

                    if phone.get("location_id") or phone.get("location_name"):
                        ref = phone.get("location_name") or phone.get("location_id")
                        # Try mapping by name or ID
                        location_id_for_phone = location_ids.get(ref)
                        if not location_id_for_phone:
                            logger.warning(
                                f"Could not map location reference '{ref}' for phone, using org ID instead"
                            )
                            org_id_for_phone = org_id if org_id else None

                    # Default to organization if no entity relationship specified
                    if not any(
                        [org_id_for_phone, service_id_for_phone, location_id_for_phone]
                    ):
                        org_id_for_phone = org_id if org_id else None
                        logger.debug(
                            f"Phone {phone.get('number')} has no entity reference, attaching to organization"
                        )

                    # Create phone record
                    if phone.get("number"):
                        phone_id = service_creator.create_phone(
                            number=phone.get("number", ""),
                            phone_type=phone.get("type", "voice"),
                            organization_id=org_id_for_phone,
                            service_id=service_id_for_phone,
                            location_id=location_id_for_phone,
                            metadata=job_result.job.metadata,
                            transaction=self.db,
                        )
                        logger.debug(f"Created phone {phone_id} from top-level array")

            # Process top-level schedule array if present
            if "schedule" in data:
                logger.info(
                    f"Processing {len(data['schedule'])} schedule records from top-level array"
                )
                for schedule in data["schedule"]:
                    # Map original IDs to actual database IDs
                    service_id_for_schedule = None
                    location_id_for_schedule = None
                    service_at_location_id_for_schedule = None

                    # Map service reference if present (try name first, then ID)
                    if schedule.get("service_id") or schedule.get("service_name"):
                        ref = schedule.get("service_name") or schedule.get("service_id")
                        service_id_for_schedule = service_id_map.get(ref)
                        if not service_id_for_schedule:
                            logger.warning(
                                f"Could not map service reference '{ref}' for schedule, skipping"
                            )
                            continue

                    # Map location reference if present (try name first, then ID)
                    if schedule.get("location_id") or schedule.get("location_name"):
                        ref = schedule.get("location_name") or schedule.get(
                            "location_id"
                        )
                        location_id_for_schedule = location_ids.get(ref)
                        if not location_id_for_schedule:
                            logger.warning(
                                f"Could not map location reference '{ref}' for schedule, skipping"
                            )
                            continue

                    # Map service_at_location ID if present
                    if schedule.get("service_at_location_id"):
                        original_sal_id = schedule.get("service_at_location_id")
                        service_at_location_id_for_schedule = (
                            service_at_location_id_map.get(original_sal_id)
                        )
                        if not service_at_location_id_for_schedule:
                            logger.warning(
                                f"Could not map service_at_location ID {original_sal_id} for schedule, skipping this schedule"
                            )
                            continue

                    # Skip if no valid entity reference exists
                    if not any(
                        [
                            service_id_for_schedule,
                            location_id_for_schedule,
                            service_at_location_id_for_schedule,
                        ]
                    ):
                        logger.warning(
                            "Schedule has no valid entity references, skipping"
                        )
                        continue

                    # Parse schedule fields with validation
                    if schedule and isinstance(schedule, dict):
                        byday = schedule.get("byday")
                    else:
                        byday = None
                        logger.warning("Invalid schedule data in top-level array")

                    description = schedule.get("description", "") if schedule else ""

                    # Update or create schedule record
                    schedule_id, was_updated = (
                        service_creator.update_or_create_schedule(
                            freq=schedule.get("freq"),
                            wkst=schedule.get("wkst"),
                            opens_at=schedule.get("opens_at"),
                            closes_at=schedule.get("closes_at"),
                            service_id=service_id_for_schedule,
                            location_id=location_id_for_schedule,
                            service_at_location_id=service_at_location_id_for_schedule,
                            metadata=job_result.job.metadata,
                            byday=byday,
                            description=description,
                        )
                    )
                    if was_updated:
                        logger.info(
                            f"Updated schedule {schedule_id} from top-level array with byday: {byday}"
                        )
                    else:
                        logger.debug(
                            f"Schedule {schedule_id} from top-level array unchanged or newly created"
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
