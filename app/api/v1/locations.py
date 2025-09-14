"""Locations API endpoints."""

from uuid import UUID
from typing import Optional, Sequence, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from pydantic import BaseModel

from app.core.db import get_session
from app.database.repositories import LocationRepository
from app.database.models import LocationModel
from app.models.hsds.location import Location
from app.models.hsds.query import GeoBoundingBox, GeoPoint
from app.models.hsds.response import (
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

router = APIRouter(prefix="/locations", tags=["locations"])


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
        schedule = ScheduleInfo(
            opens_at=str(row.opens_at) if row.opens_at else None,
            closes_at=str(row.closes_at) if row.closes_at else None,
            byday=row.byday,
            freq=row.freq,
            description=row.description,
            valid_from=row.valid_from.isoformat() if row.valid_from else None,
            valid_to=row.valid_to.isoformat() if row.valid_to else None,
            notes=row.notes,
        )
        schedules.append(schedule)

    return schedules


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
            o.website,
            o.email,
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
        sources = await get_location_sources(location.id, session)
        if sources:
            location_data.sources = sources
            location_data.source_count = len(sources)

        # Add schedules information via direct SQL query
        schedules = await get_location_schedules(location.id, session)
        if schedules:
            location_data.schedules = schedules[:5]  # Limit to 5 schedules per location

        if include_services and location.services_at_location:
            location_data.services = [
                ServiceResponse.model_validate(sal.service)
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
        sources = await get_location_sources(location.id, session)
        if sources:
            location_data.sources = sources
            location_data.source_count = len(sources)

        # Add schedules information via direct SQL query
        schedules = await get_location_schedules(location.id, session)
        if schedules:
            location_data.schedules = schedules[:5]  # Limit to 5 schedules per location

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
                ServiceResponse.model_validate(sal.service)
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
    sources = await get_location_sources(location.id, session)
    if sources:
        location_response.sources = sources
        location_response.source_count = len(sources)

    # Add schedules information via direct SQL query
    schedules = await get_location_schedules(location.id, session)
    if schedules:
        location_response.schedules = schedules

    if include_services:
        # Load services at this location
        from app.database.repositories import ServiceAtLocationRepository

        sal_repo = ServiceAtLocationRepository(session)
        services_at_location = await sal_repo.get_services_at_location(location_id)

        location_response.services = [
            ServiceResponse.model_validate(sal.service) for sal in services_at_location
        ]

    return location_response


class ExportLocation(BaseModel):
    """Simplified location model for export."""

    id: str
    lat: float
    lng: float
    name: str
    org: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    confidence_score: Optional[float] = None
    validation_status: Optional[str] = None
    services: Optional[List[str]] = None
    schedule: Optional[Dict[str, Any]] = None


class LocationExportResponse(BaseModel):
    """Response model for bulk location export."""

    metadata: Dict[str, Any]
    locations: List[ExportLocation]


class SimpleExportResponse(BaseModel):
    """Simple export response model."""

    metadata: Dict[str, Any]
    locations: List[Dict[str, Any]]


# The /export endpoint has been removed as deprecated
# Use /export-simple endpoint instead for location export functionality


@router.get("/export-simple")
async def export_simple_locations(
    state: Optional[str] = Query(None, description="Filter by state code (e.g., 'CA')"),
    min_confidence: Optional[int] = Query(
        None, ge=0, le=100, description="Minimum confidence score"
    ),
    limit: int = Query(
        10000, ge=1, le=50000, description="Maximum number of locations to return"
    ),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Export locations in a simplified format with sources information.

    This endpoint returns location data including an array of sources showing
    which scrapers found each location and their specific data variations.

    The response includes:
    - Basic location information (name, coordinates, address)
    - Sources array with per-scraper data
    - Source count for quick reference
    """
    # Build optimized query to fetch locations with sources
    sql = """
        WITH location_data AS (
            SELECT
                l.id,
                l.latitude as lat,
                l.longitude as lng,
                l.name,
                o.name as org_name,
                CONCAT_WS(', ', a.address_1, a.city, a.state_province, a.postal_code) as address,
                a.city,
                a.state_province as state,
                a.postal_code as zip,
                p.number as phone,
                l.url as website,
                e.email,
                l.description,
                COALESCE(l.confidence_score, 50) as confidence_score,
                COALESCE(l.validation_status, 'needs_review') as validation_status
            FROM location l
            LEFT JOIN organization o ON l.organization_id = o.id
            LEFT JOIN address a ON a.location_id = l.id
            LEFT JOIN LATERAL (
                SELECT number FROM phone
                WHERE location_id = l.id
                LIMIT 1
            ) p ON true
            LEFT JOIN LATERAL (
                SELECT email FROM email
                WHERE location_id = l.id
                LIMIT 1
            ) e ON true
            WHERE l.latitude IS NOT NULL
              AND l.longitude IS NOT NULL
              AND l.latitude BETWEEN -90 AND 90
              AND l.longitude BETWEEN -180 AND 180
              AND l.is_canonical = true
              AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
    """

    params = {}

    # Add filters
    if state:
        sql += " AND a.state_province = :state"
        params["state"] = state.upper()

    if min_confidence:
        sql += " AND COALESCE(l.confidence_score, 50) >= :min_confidence"
        params["min_confidence"] = min_confidence

    sql += f"""
        ), source_data AS (
            SELECT
                ls.location_id,
                json_agg(
                    json_build_object(
                        'scraper', ls.scraper_id,
                        'name', ls.name,
                        'phone', p2.number,
                        'email', e2.email,
                        'website', o2.website,
                        'address', CONCAT_WS(', ', a2.address_1, a2.city, a2.state_province, a2.postal_code),
                        'confidence_score', COALESCE(l2.confidence_score, 50),
                        'last_updated', ls.updated_at,
                        'first_seen', ls.created_at
                    )
                    ORDER BY ls.updated_at DESC
                ) as sources,
                COUNT(DISTINCT ls.scraper_id) as source_count
            FROM location_source ls
            LEFT JOIN location l2 ON l2.id = ls.location_id
            LEFT JOIN organization o2 ON o2.id = l2.organization_id
            LEFT JOIN address a2 ON a2.location_id = l2.id
            LEFT JOIN LATERAL (
                SELECT number FROM phone WHERE location_id = l2.id LIMIT 1
            ) p2 ON true
            LEFT JOIN LATERAL (
                SELECT email FROM email WHERE location_id = l2.id LIMIT 1
            ) e2 ON true
            GROUP BY ls.location_id
        )
        SELECT
            ld.*,
            COALESCE(sd.sources, '[]'::json) as sources,
            COALESCE(sd.source_count, 0) as source_count
        FROM location_data ld
        LEFT JOIN source_data sd ON sd.location_id = ld.id
        ORDER BY ld.confidence_score DESC, ld.name
        LIMIT {limit}
    """

    # Execute query
    result = await session.execute(text(sql), params)
    rows = result.fetchall()

    # Convert to simple locations with sources
    locations = []
    states = set()

    for row in rows:
        if row.state:
            states.add(row.state)

        # Parse sources JSON
        sources = []
        if row.sources:
            if isinstance(row.sources, str):
                import json

                sources_data = json.loads(row.sources)
            else:
                sources_data = row.sources

            for src in sources_data:
                # Format timestamps
                if src.get("last_updated"):
                    src["last_updated"] = (
                        src["last_updated"].isoformat()
                        if hasattr(src["last_updated"], "isoformat")
                        else str(src["last_updated"])
                    )
                if src.get("first_seen"):
                    src["first_seen"] = (
                        src["first_seen"].isoformat()
                        if hasattr(src["first_seen"], "isoformat")
                        else str(src["first_seen"])
                    )
                sources.append(src)

        location_data = {
            "id": str(row.id),
            "lat": float(row.lat) if row.lat else 0.0,
            "lng": float(row.lng) if row.lng else 0.0,
            "name": row.name or "Unknown",
            "org": row.org_name or row.name or "",
            "address": row.address or "",
            "city": row.city,
            "state": row.state,
            "zip": row.zip,
            "phone": row.phone,
            "website": row.website,
            "email": row.email,
            "description": row.description,
            "confidence_score": (
                float(row.confidence_score) if row.confidence_score else 50.0
            ),
            "validation_status": row.validation_status or "needs_review",
            "sources": sources,
            "source_count": int(row.source_count) if row.source_count else 0,
        }

        locations.append(location_data)

    # Build metadata
    metadata = {
        "generated": datetime.utcnow().isoformat(),
        "total_locations": len(locations),
        "states_covered": len(states),
        "coverage": (
            f"{len(states)} US states/territories" if states else "No state data"
        ),
        "format_version": "2.0",
        "source": "Pantry Pirate Radio API",
        "includes_sources": True,
        "export_method": "Simple Export with Sources",
    }

    if state:
        metadata["filter_state"] = state.upper()
    if min_confidence:
        metadata["min_confidence"] = min_confidence

    return {"metadata": metadata, "locations": locations}
