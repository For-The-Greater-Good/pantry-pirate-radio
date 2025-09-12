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
from app.models.hsds.response import LocationResponse, ServiceResponse, Page
from app.api.v1.utils import (
    create_pagination_links,
    calculate_pagination_metadata,
    validate_pagination_params,
    build_filter_dict,
)

router = APIRouter(prefix="/locations", tags=["locations"])


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

    # Build filters
    filters = build_filter_dict(organization_id=organization_id)

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
        location_data = LocationResponse.model_validate(location)

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
        None, ge=0, le=100, description="Radius in miles"
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

    # Build filters
    filters = build_filter_dict(organization_id=organization_id)

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
        location_data = LocationResponse.model_validate(location)

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
    location_response = LocationResponse.model_validate(location)

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


@router.get("/test-before-export", response_model=Dict[str, str])
async def test_before_export() -> Dict[str, str]:
    """Test endpoint before export."""
    return {"test": "working", "position": "before export"}


@router.get("/export")
async def export_locations(
    request: Request,
    state: Optional[str] = Query(None, description="Filter by state code (e.g., 'CA')"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Minimum confidence score"),
    session: AsyncSession = Depends(get_session),
) -> LocationExportResponse:
    """
    Export all locations in a lightweight format for client-side caching.
    
    This endpoint is optimized for bulk data export similar to HAARRRvest.
    Returns a compact JSON representation of all locations suitable for
    offline use and client-side clustering.
    
    The response is cached-friendly and can be stored in browser IndexedDB
    for offline functionality.
    """
    from sqlalchemy.orm import selectinload, joinedload
    from app.database.models import AddressModel, OrganizationModel, PhoneModel, EmailModel
    
    # Build optimized query with eager loading - fix the relationship loading
    query = (
        select(LocationModel)
        .options(
            selectinload(LocationModel.address),
            selectinload(LocationModel.organization),
            selectinload(LocationModel.phones),
            selectinload(LocationModel.emails),
            selectinload(LocationModel.schedules),
        )
        .where(LocationModel.latitude.isnot(None))
        .where(LocationModel.longitude.isnot(None))
        .where(LocationModel.latitude.between(-90, 90))
        .where(LocationModel.longitude.between(-180, 180))
    )
    
    # Add filters
    if state:
        query = query.join(AddressModel).where(
            AddressModel.state_province == state.upper()
        )
    
    # Filter by validation status (exclude rejected)
    query = query.where(
        (LocationModel.validation_status.is_(None)) | 
        (LocationModel.validation_status != 'rejected')
    )
    
    # Execute query
    result = await session.execute(query)
    locations = result.scalars().unique().all()
    
    # Get total count and state coverage
    total_count = len(locations)
    states = set()
    
    # Convert to export format
    export_locations = []
    for loc in locations:
        # Extract state from address if available
        if loc.address and loc.address.state_province:
            states.add(loc.address.state_province)
        
        # Build address string
        address_parts = []
        if loc.address:
            if loc.address.address_1:
                address_parts.append(loc.address.address_1)
            if loc.address.city:
                address_parts.append(loc.address.city)
            if loc.address.state_province:
                address_parts.append(loc.address.state_province)
            if loc.address.postal_code:
                address_parts.append(loc.address.postal_code)
        
        # Build simplified location object
        export_loc = ExportLocation(
            id=str(loc.id),
            lat=float(loc.latitude) if loc.latitude else 0.0,
            lng=float(loc.longitude) if loc.longitude else 0.0,
            name=loc.name or "Unknown",
            org=loc.organization.name if loc.organization else loc.name,
            address=", ".join(address_parts) if address_parts else "",
            city=loc.address.city if loc.address else None,
            state=loc.address.state_province if loc.address else None,
            zip=loc.address.postal_code if loc.address else None,
            phone=loc.phones[0].number if loc.phones else None,
            website=loc.url,
            email=loc.emails[0].email if loc.emails else None,
            description=loc.description,
            confidence_score=getattr(loc, 'confidence_score', 50),
            validation_status=getattr(loc, 'validation_status', 'needs_review'),
        )
        
        # Add services if available (skip for now to avoid relationship issues)
        # if loc.services_at_location:
        #     export_loc.services = [sal.service.name for sal in loc.services_at_location if sal.service]
        
        # Add schedule if available
        if loc.schedules:
            schedule_data = {}
            for schedule in loc.schedules[:1]:  # Take first schedule
                if schedule.opens_at:
                    schedule_data['opens_at'] = str(schedule.opens_at)
                if schedule.closes_at:
                    schedule_data['closes_at'] = str(schedule.closes_at)
                if hasattr(schedule, 'description') and schedule.description:
                    schedule_data['description'] = schedule.description
            if schedule_data:
                export_loc.schedule = schedule_data
        
        # Skip locations with confidence below threshold if specified
        if min_confidence and export_loc.confidence_score < min_confidence:
            continue
            
        export_locations.append(export_loc)
    
    # Build metadata
    metadata = {
        "generated": datetime.utcnow().isoformat(),
        "total_locations": len(export_locations),
        "states_covered": len(states),
        "coverage": f"{len(states)} US states/territories" if states else "No state data",
        "format_version": "1.0",
        "source": "Pantry Pirate Radio API",
        "export_method": "Full Database Export",
    }
    
    if state:
        metadata["filter_state"] = state.upper()
    if min_confidence:
        metadata["min_confidence"] = min_confidence
    
    response = LocationExportResponse(
        metadata=metadata,
        locations=export_locations
    )
    
    # Return with cache headers for client-side caching
    return JSONResponse(
        content=response.model_dump(),
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "ETag": f'"{len(export_locations)}-{datetime.utcnow().date()}"',
        }
    )


@router.get("/test-endpoint", response_model=SimpleExportResponse)
async def test_endpoint() -> SimpleExportResponse:
    """
    Simple export endpoint that uses raw SQL to avoid ORM issues.
    Returns a JSONResponse with properly serialized data.
    """
    
    # TEMPORARY: Return hardcoded response to test if endpoint works
    return SimpleExportResponse(
        metadata={
            "test": "hardcoded",
            "working": True
        },
        locations=[]
    )
    
    # Build SQL query
    sql = """
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
        WHERE l.latitude IS NOT NULL 
          AND l.longitude IS NOT NULL
          AND l.latitude BETWEEN -90 AND 90
          AND l.longitude BETWEEN -180 AND 180
          AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
    """
    
    params = {}
    if state:
        sql += " AND a.state_province = :state"
        params['state'] = state.upper()
    
    sql += f" LIMIT {limit}"
    
    # Execute query
    result = await session.execute(text(sql), params)
    rows = result.fetchall()
    
    # Convert to simple locations
    locations = []
    states = set()
    
    for row in rows:
        if row.state:
            states.add(row.state)
            
        locations.append({
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
            "confidence_score": float(row.confidence_score) if row.confidence_score else 50.0,
            "validation_status": row.validation_status or "needs_review"
        })
    
    # Return plain dict - let FastAPI handle serialization
    return {
        "metadata": {
            "generated": datetime.utcnow().isoformat(),
            "total_locations": len(locations),
            "states_covered": len(states),
            "format_version": "1.0",
            "source": "Pantry Pirate Radio API"
        },
        "locations": locations
    }
