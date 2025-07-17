"""Locations API endpoints."""

import math
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.database.repositories import LocationRepository
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
    from typing import Sequence
    from app.database.models import LocationModel

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

    # Get total count (approximation for geographic searches)
    total = len(locations) if locations else 0

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
            and location.latitude
            and location.longitude
        ):
            # Calculate distance (simplified - would use PostGIS in production)
            lat1, lon1 = math.radians(latitude), math.radians(longitude)
            lat2, lon2 = math.radians(float(location.latitude)), math.radians(
                float(location.longitude)
            )

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            )
            c = 2 * math.asin(math.sqrt(a))
            distance_miles = 3959 * c  # Earth's radius in miles

            location_data.distance = f"{distance_miles:.1f}mi"

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
