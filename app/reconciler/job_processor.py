"""Job processing utilities for the reconciler."""

import json
import logging
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
    addresses: list[dict[str, Any]]
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
            # Try standard JSON parsing first
            try:
                raw_data = json.loads(job_result.result.text)
            except json.JSONDecodeError:
                # If standard parsing fails, use demjson3 which is more tolerant
                logger.info("Standard JSON parsing failed, trying demjson3")
                raw_data = demjson3.decode(job_result.result.text)

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

                # Create the expected structure
                transformed_data = {
                    # Wrap the organization in a list
                    "organization": [raw_data],
                    "service": services,
                    "location": locations,
                }
                data = cast(HSDataDict, transformed_data)
            else:
                # Use the data as-is
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
                    org_id, is_new_org = org_creator.process_organization(
                        org["name"],
                        description,
                        job_result.job.metadata,
                        website=org.get("website"),
                        email=org.get("email"),
                        year_incorporated=org.get("year_incorporated"),
                        legal_status=org.get("legal_status"),
                        uri=org.get("uri"),
                    )
                else:
                    # Fall back to old method for backward compatibility with tests
                    org_id = org_creator.create_organization(
                        org["name"],
                        description,
                        job_result.job.metadata,
                        website=org.get("website"),
                        email=org.get("email"),
                        year_incorporated=org.get("year_incorporated"),
                        legal_status=org.get("legal_status"),
                        uri=org.get("uri"),
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
                    if "latitude" in location and "longitude" in location:
                        # Check for existing location by coordinates
                        match_id = location_creator.find_matching_location(
                            float(location["latitude"]), float(location["longitude"])
                        )

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

                            # Create location addresses
                            if "addresses" in location:
                                for address in location["addresses"]:
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

                            # Create location phones with languages
                            if "phones" in location:
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

                            # Create location accessibility
                            if "accessibility" in location:
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
                services_to_process.extend(data["service"])

            # Add services from organizations if present
            if "organization" in data and len(data["organization"]) > 0:
                for org in data["organization"]:
                    if "services" in org:
                        services_to_process.extend(org["services"])

            # Process all collected services
            for service in services_to_process:
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
                        if loc["name"] in location_ids:
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

                                    # Add service schedules
                                    if "schedules" in service:
                                        schedules_to_create.extend(service["schedules"])

                                    # Add location schedules if they don't overlap with service schedules
                                    if "schedules" in loc:
                                        loc_schedules = loc["schedules"]
                                        for loc_schedule in loc_schedules:
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
