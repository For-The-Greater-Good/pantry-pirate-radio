"""Locations API endpoints."""

from uuid import UUID
from typing import Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.db import get_session
from app.database.repositories import LocationRepository
from app.database.models import LocationModel
from app.models.hsds.location import Location
from app.models.hsds.query import GeoBoundingBox, GeoPoint
from app.models.hsds.response import (
    Address,
    LocationResponse,
    ServiceResponse,
    Page,
    SourceInfo,
    ScheduleInfo,
)
from app.api.v1.utils import (
    create_pagination_links,
    calculate_pagination_metadata,
    validate_pagination_params,
    build_filter_dict,
)

import structlog
from pydantic import ValidationError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/locations", tags=["locations"])


def _shallow_service_for_location(service) -> dict:
    """Shallow Service dict for embedding in a Location response (no nested locations)."""
    return {
        "id": str(service.id),
        "organization_id": str(service.organization_id),
        "name": service.name,
        "alternate_name": getattr(service, "alternate_name", None),
        "description": service.description,
        "url": getattr(service, "url", None),
        "email": getattr(service, "email", None),
        "status": service.status,
    }


async def get_location_schedules(
    location_id: str, session: AsyncSession
) -> list[ScheduleInfo]:
    """Get schedule information for a location via direct SQL query.

    Args:
        location_id: Location ID
        session: Database session

    Returns:
        List of schedule information
    """
    # Query for schedules directly
    schedule_query = """
        SELECT
            opens_at,
            closes_at,
            byday,
            bymonthday,
            freq,
            description,
            valid_from,
            valid_to,
            notes
        FROM schedule
        WHERE location_id = :location_id
           OR service_id IN (
               SELECT service_id
               FROM service_at_location
               WHERE location_id = :location_id
           )
    """

    result = await session.execute(
        text(schedule_query), {"location_id": str(location_id)}
    )
    rows = result.fetchall()

    schedules = []
    for row in rows:
        # Fail soft: ScheduleInfo's byday/bymonthday validators RAISE on a value
        # that the RFC 5545 normalizer can't parse. A single corrupt row (from
        # any write path that bypassed normalization) must not 500 the whole
        # page — skip it and log so the bad row is traceable. This matches the
        # reconciler/submarine/normalizer fail-soft posture for the same fields.
        try:
            schedule = ScheduleInfo(
                opens_at=str(row.opens_at) if row.opens_at else None,
                closes_at=str(row.closes_at) if row.closes_at else None,
                byday=row.byday,
                bymonthday=row.bymonthday,
                freq=row.freq,
                description=row.description,
                valid_from=row.valid_from.isoformat() if row.valid_from else None,
                valid_to=row.valid_to.isoformat() if row.valid_to else None,
                notes=row.notes,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            logger.warning(
                "location_schedule_dropped_invalid",
                location_id=str(location_id),
                byday=row.byday,
                bymonthday=row.bymonthday,
                freq=row.freq,
                error=str(exc),
            )
            continue
        schedules.append(schedule)

    return schedules


async def get_location_addresses(
    location_id: str, session: AsyncSession
) -> list[Address]:
    """Get structured HSDS addresses for a location via direct SQL query.

    Args:
        location_id: Location ID
        session: Database session

    Returns:
        List of structured Address models. The `address` table NOT-NULLs
        address_1/city/state_province/postal_code/country/address_type
        (init-scripts/01-hsds-schema.sql), so every row satisfies Address's
        required fields.
    """
    address_query = """
        SELECT
            id,
            location_id,
            attention,
            address_1,
            address_2,
            city,
            region,
            state_province,
            postal_code,
            country,
            address_type
        FROM address
        WHERE location_id = :location_id
        ORDER BY id
    """

    result = await session.execute(
        text(address_query), {"location_id": str(location_id)}
    )
    rows = result.fetchall()

    addresses = []
    for row in rows:
        addresses.append(
            Address(
                id=row.id,
                location_id=row.location_id,
                attention=row.attention,
                address_1=row.address_1,
                address_2=row.address_2,
                city=row.city,
                region=row.region,
                state_province=row.state_province,
                postal_code=row.postal_code,
                country=row.country,
                address_type=row.address_type,
            )
        )

    return addresses


async def get_location_sources(
    location_id: str, session: AsyncSession
) -> list[SourceInfo]:
    """Get source information for a location.

    Args:
        location_id: Location ID
        session: Database session

    Returns:
        List of source information
    """
    # Query for source information
    sources_query = """
        SELECT
            ls.scraper_id,
            ls.name,
            ls.description,
            ls.created_at as first_seen,
            ls.updated_at as last_updated,
            p.number as phone,
            COALESCE(o.website, (
                SELECT os.website FROM organization_source os
                WHERE os.organization_id = o.id AND os.website IS NOT NULL
                ORDER BY os.updated_at DESC LIMIT 1
            )) as website,
            COALESCE(o.email, (
                SELECT os.email FROM organization_source os
                WHERE os.organization_id = o.id AND os.email IS NOT NULL
                ORDER BY os.updated_at DESC LIMIT 1
            )) as email,
            CONCAT_WS(', ',
                NULLIF(a.address_1, ''),
                NULLIF(a.city, ''),
                NULLIF(a.state_province, ''),
                NULLIF(a.postal_code, '')
            ) as address,
            l.confidence_score
        FROM location_source ls
        LEFT JOIN location l ON l.id = ls.location_id
        LEFT JOIN organization o ON o.id = l.organization_id
        LEFT JOIN address a ON a.location_id = l.id
        LEFT JOIN phone p ON p.location_id = l.id
        WHERE ls.location_id = :location_id
    """

    result = await session.execute(
        text(sources_query), {"location_id": str(location_id)}
    )
    rows = result.fetchall()

    sources = []
    for row in rows:
        source = SourceInfo(
            scraper=row.scraper_id,
            name=row.name,
            phone=row.phone,
            email=row.email,
            website=row.website,
            address=row.address,
            confidence_score=row.confidence_score or 50,
            first_seen=row.first_seen.isoformat() if row.first_seen else None,
            last_updated=row.last_updated.isoformat() if row.last_updated else None,
        )
        sources.append(source)

    return sources


@router.get("/", response_model=Page[LocationResponse])
async def list_locations(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    organization_id: Optional[UUID] = Query(
        None, description="Filter by organization ID"
    ),
    include_services: bool = Query(False, description="Include services in response"),
    session: AsyncSession = Depends(get_session),
) -> Page[LocationResponse]:
    """
    List locations with optional filtering and pagination.

    Returns paginated list of locations with optional service details.
    """
    validate_pagination_params(page, per_page)

    repository = LocationRepository(session)

    # Calculate pagination
    pagination = calculate_pagination_metadata(
        0, page, per_page
    )  # Will update total later

    # Build filters - convert UUID to string
    filters = build_filter_dict(
        organization_id=str(organization_id) if organization_id else None
    )

    # Get locations
    if include_services:
        locations = await repository.get_locations_with_services(
            skip=pagination["skip"], limit=per_page
        )
    else:
        locations = await repository.get_all(
            skip=pagination["skip"], limit=per_page, filters=filters
        )

    # Get total count
    total = await repository.count(filters=filters)

    # Update pagination metadata
    pagination["total_items"] = total
    pagination["total_pages"] = max(1, (total + per_page - 1) // per_page)

    # Convert to response models
    location_responses = []
    for location in locations:
        try:
            location_data = LocationResponse.model_validate(location)
        except Exception:
            # Fallback to manual construction if validation fails
            loc_dict = {
                "id": str(location.id),
                "name": location.name,
                "alternate_name": location.alternate_name,
                "description": location.description,
                "url": location.url,
                "organization_id": (
                    str(location.organization_id) if location.organization_id else None
                ),
                "latitude": float(location.latitude) if location.latitude else None,
                "longitude": float(location.longitude) if location.longitude else None,
                "transportation": location.transportation,
                "external_identifier": location.external_identifier,
                "external_identifier_type": location.external_identifier_type,
                "location_type": location.location_type,
                "metadata": {
                    "last_updated": (
                        location.updated_at.isoformat()
                        if hasattr(location, "updated_at") and location.updated_at
                        else None
                    )
                },
            }
            location_data = LocationResponse.model_validate(loc_dict)

        # Add sources information
        sources = await get_location_sources(str(location.id), session)
        if sources:
            location_data.sources = sources
            location_data.source_count = len(sources)

        # Add schedules information via direct SQL query
        schedules = await get_location_schedules(str(location.id), session)
        if schedules:
            location_data.schedules = schedules[:5]  # Limit to 5 schedules per location

        # Add structured addresses information via direct SQL query
        addresses = await get_location_addresses(str(location.id), session)
        if addresses:
            location_data.addresses = addresses

        if include_services and location.services_at_location:
            location_data.services = [
                ServiceResponse.model_validate(
                    _shallow_service_for_location(sal.service)
                )
                for sal in location.services_at_location
            ]

        location_responses.append(location_data)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=pagination["total_pages"],
        per_page=per_page,
        extra_params={
            "organization_id": organization_id,
            "include_services": include_services,
        },
    )

    return Page(
        count=len(location_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        page=page,
        total_pages=pagination["total_pages"],
        links=links,
        data=location_responses,
    )


@router.get("/search", response_model=Page[LocationResponse])
async def search_locations(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    # Geographic search parameters
    latitude: Optional[float] = Query(None, description="Latitude for radius search"),
    longitude: Optional[float] = Query(None, description="Longitude for radius search"),
    radius_miles: Optional[float] = Query(
        None, ge=0, le=1000, description="Radius in miles"
    ),
    # Bounding box search parameters
    min_latitude: Optional[float] = Query(
        None, description="Minimum latitude for bounding box"
    ),
    max_latitude: Optional[float] = Query(
        None, description="Maximum latitude for bounding box"
    ),
    min_longitude: Optional[float] = Query(
        None, description="Minimum longitude for bounding box"
    ),
    max_longitude: Optional[float] = Query(
        None, description="Maximum longitude for bounding box"
    ),
    # Other filters
    organization_id: Optional[UUID] = Query(
        None, description="Filter by organization ID"
    ),
    include_services: bool = Query(False, description="Include services in response"),
    session: AsyncSession = Depends(get_session),
) -> Page[LocationResponse]:
    """
    Search locations by geographic area.

    Supports both radius-based search (latitude, longitude, radius_miles) and
    bounding box search (min/max latitude/longitude).
    """
    validate_pagination_params(page, per_page)

    repository = LocationRepository(session)

    # Calculate pagination
    pagination = calculate_pagination_metadata(0, page, per_page)

    # Build filters - convert UUID to string
    filters = build_filter_dict(
        organization_id=str(organization_id) if organization_id else None
    )

    # Determine search type and execute query
    locations: Sequence[LocationModel] = []

    if latitude is not None and longitude is not None and radius_miles is not None:
        # Radius search
        center = GeoPoint(latitude=latitude, longitude=longitude)
        locations = await repository.get_locations_by_radius(
            center=center,
            radius_miles=radius_miles,
            skip=pagination["skip"],
            limit=per_page,
            filters=filters,
        )
    elif all(
        coord is not None
        for coord in [min_latitude, max_latitude, min_longitude, max_longitude]
    ):
        # Bounding box search - all coords are guaranteed to be not None by the check above
        bbox = GeoBoundingBox(
            min_latitude=min_latitude,  # type: ignore[arg-type]
            max_latitude=max_latitude,  # type: ignore[arg-type]
            min_longitude=min_longitude,  # type: ignore[arg-type]
            max_longitude=max_longitude,  # type: ignore[arg-type]
        )
        locations = await repository.get_locations_by_bbox(
            bbox=bbox,
            skip=pagination["skip"],
            limit=per_page,
            filters=filters,
        )
    else:
        # No geographic search, use regular list
        if include_services:
            locations = await repository.get_locations_with_services(
                skip=pagination["skip"], limit=per_page
            )
        else:
            locations = await repository.get_all(
                skip=pagination["skip"], limit=per_page, filters=filters
            )

    # Get total count using proper count queries
    if latitude is not None and longitude is not None and radius_miles is not None:
        # Radius search count
        center = GeoPoint(latitude=latitude, longitude=longitude)
        total = await repository.count_by_radius(
            center=center,
            radius_miles=radius_miles,
            filters=filters,
        )
    elif all(
        coord is not None
        for coord in [min_latitude, max_latitude, min_longitude, max_longitude]
    ):
        # Bounding box search count
        bbox = GeoBoundingBox(
            min_latitude=min_latitude,  # type: ignore[arg-type]
            max_latitude=max_latitude,  # type: ignore[arg-type]
            min_longitude=min_longitude,  # type: ignore[arg-type]
            max_longitude=max_longitude,  # type: ignore[arg-type]
        )
        total = await repository.count_by_bbox(
            bbox=bbox,
            filters=filters,
        )
    else:
        # Regular count
        total = await repository.count(filters=filters)

    # Update pagination metadata
    pagination["total_items"] = total
    pagination["total_pages"] = max(1, (total + per_page - 1) // per_page)

    # Convert to response models
    location_responses = []
    for location in locations:
        try:
            location_data = LocationResponse.model_validate(location)
        except Exception:
            # Fallback to manual construction if validation fails
            loc_dict = {
                "id": str(location.id),
                "name": location.name,
                "alternate_name": location.alternate_name,
                "description": location.description,
                "url": location.url,
                "organization_id": (
                    str(location.organization_id) if location.organization_id else None
                ),
                "latitude": float(location.latitude) if location.latitude else None,
                "longitude": float(location.longitude) if location.longitude else None,
                "transportation": location.transportation,
                "external_identifier": location.external_identifier,
                "external_identifier_type": location.external_identifier_type,
                "location_type": location.location_type,
                "metadata": {
                    "last_updated": (
                        location.updated_at.isoformat()
                        if hasattr(location, "updated_at") and location.updated_at
                        else None
                    )
                },
            }
            location_data = LocationResponse.model_validate(loc_dict)

        # Add sources information
        sources = await get_location_sources(str(location.id), session)
        if sources:
            location_data.sources = sources
            location_data.source_count = len(sources)

        # Add schedules information via direct SQL query
        schedules = await get_location_schedules(str(location.id), session)
        if schedules:
            location_data.schedules = schedules[:5]  # Limit to 5 schedules per location

        # Add structured addresses information via direct SQL query
        addresses = await get_location_addresses(str(location.id), session)
        if addresses:
            location_data.addresses = addresses

        # Add distance information for radius searches
        if (
            latitude is not None
            and longitude is not None
            and hasattr(location, "distance_miles")
        ):
            # Use distance from PostGIS query
            location_data.distance = f"{location.distance_miles:.1f}mi"

        if (
            include_services
            and hasattr(location, "services_at_location")
            and location.services_at_location
        ):
            location_data.services = [
                ServiceResponse.model_validate(
                    _shallow_service_for_location(sal.service)
                )
                for sal in location.services_at_location
            ]

        location_responses.append(location_data)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=pagination["total_pages"],
        per_page=per_page,
        extra_params={
            "latitude": latitude,
            "longitude": longitude,
            "radius_miles": radius_miles,
            "min_latitude": min_latitude,
            "max_latitude": max_latitude,
            "min_longitude": min_longitude,
            "max_longitude": max_longitude,
            "organization_id": organization_id,
            "include_services": include_services,
        },
    )

    return Page(
        count=len(location_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        page=page,
        total_pages=pagination["total_pages"],
        links=links,
        data=location_responses,
    )


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: UUID,
    include_services: bool = Query(False, description="Include services in response"),
    session: AsyncSession = Depends(get_session),
) -> LocationResponse:
    """
    Get a specific location by ID.

    Returns detailed information about a location with optional service details.
    """
    repository = LocationRepository(session)

    location = await repository.get_by_id(location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Convert to response model
    try:
        location_response = LocationResponse.model_validate(location)
    except Exception:
        # Fallback to manual construction if validation fails
        loc_dict = {
            "id": str(location.id),
            "name": location.name,
            "alternate_name": location.alternate_name,
            "description": location.description,
            "url": location.url,
            "organization_id": (
                str(location.organization_id) if location.organization_id else None
            ),
            "latitude": float(location.latitude) if location.latitude else None,
            "longitude": float(location.longitude) if location.longitude else None,
            "transportation": location.transportation,
            "external_identifier": location.external_identifier,
            "external_identifier_type": location.external_identifier_type,
            "location_type": location.location_type,
            "metadata": {
                "last_updated": (
                    location.updated_at.isoformat()
                    if hasattr(location, "updated_at") and location.updated_at
                    else None
                )
            },
        }
        location_response = LocationResponse.model_validate(loc_dict)

    # Add sources information
    sources = await get_location_sources(str(location.id), session)
    if sources:
        location_response.sources = sources
        location_response.source_count = len(sources)

    # Add schedules information via direct SQL query
    schedules = await get_location_schedules(str(location.id), session)
    if schedules:
        location_response.schedules = schedules

    # Add structured addresses information via direct SQL query
    addresses = await get_location_addresses(str(location.id), session)
    if addresses:
        location_response.addresses = addresses

    if include_services:
        # Load services at this location. Build shallow dicts so Pydantic never
        # recurses into service.locations (not eager-loaded → MissingGreenlet).
        from app.database.repositories import ServiceAtLocationRepository

        sal_repo = ServiceAtLocationRepository(session)
        services_at_location = await sal_repo.get_services_at_location(location_id)

        location_response.services = [
            ServiceResponse.model_validate(_shallow_service_for_location(sal.service))
            for sal in services_at_location
        ]

    return location_response


# Export models and endpoint moved to locations_export.py
