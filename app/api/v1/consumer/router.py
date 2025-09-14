"""Consumer API endpoints for mobile and web clients."""

import logging
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.api.v1.consumer.models import (
    MapPinsResponse,
    MultiLocationResponse,
    SingleLocationResponse,
    LocationDetail,
)
from app.api.v1.consumer.services import ConsumerLocationService

router = APIRouter(prefix="/consumer", tags=["consumer"])
logger = logging.getLogger(__name__)


@router.get("/map/pins", response_model=MapPinsResponse)
async def get_map_pins(
    request: Request,
    # Required: Viewport boundaries
    min_lat: float = Query(..., ge=-90, le=90, description="Minimum latitude"),
    max_lat: float = Query(..., ge=-90, le=90, description="Maximum latitude"),
    min_lng: float = Query(..., ge=-180, le=180, description="Minimum longitude"),
    max_lng: float = Query(..., ge=-180, le=180, description="Maximum longitude"),
    # Optional: Grouping control
    grouping_radius: int = Query(
        150, ge=0, le=500, description="Grouping radius in meters (0 to disable)"
    ),
    # Optional: Filters
    min_confidence: Optional[int] = Query(
        None, ge=0, le=100, description="Minimum confidence score"
    ),
    open_now: Optional[bool] = Query(None, description="Filter by current schedule"),
    services: Optional[str] = Query(
        None, description="Comma-separated list of service types"
    ),
    session: AsyncSession = Depends(get_session),
) -> MapPinsResponse:
    """
    Get location pins for map display with dynamic grouping.

    This endpoint returns location data optimized for map visualization.
    Locations within the grouping radius are clustered together.

    ## Request Parameters:
    - **Viewport boundaries** (required): Define the visible map area
    - **grouping_radius**: Controls clustering (0-500 meters, default 150)
    - **min_confidence**: Filter low-quality locations
    - **open_now**: Show only currently open locations
    - **services**: Filter by service types (comma-separated)

    ## Response:
    Returns a mix of single and grouped pins based on the grouping radius.
    Each pin includes minimal data for efficient map rendering.

    ## Performance:
    - Optimized for < 100ms response times
    - Returns maximum 1000 locations
    - Uses PostGIS spatial indexing
    """
    # Validate viewport bounds
    if min_lat >= max_lat:
        raise HTTPException(400, "min_lat must be less than max_lat")
    if min_lng >= max_lng:
        raise HTTPException(400, "min_lng must be less than max_lng")

    # Parse services list if provided
    service_list = None
    if services:
        service_list = [s.strip() for s in services.split(",") if s.strip()]

    # Get pins from service
    service = ConsumerLocationService(session)
    pins, metadata = await service.get_map_pins(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lng=min_lng,
        max_lng=max_lng,
        grouping_radius=grouping_radius,
        min_confidence=min_confidence,
        open_now=open_now,
        services=service_list,
    )

    return MapPinsResponse(pins=pins, metadata=metadata)


@router.get("/locations/multi", response_model=MultiLocationResponse)
async def get_multiple_locations(
    request: Request,
    ids: str = Query(..., description="Comma-separated location UUIDs (max 100)"),
    include_sources: bool = Query(True, description="Include source data"),
    include_schedule: bool = Query(True, description="Include schedules"),
    session: AsyncSession = Depends(get_session),
) -> MultiLocationResponse:
    """
    Fetch detailed information for multiple locations.

    This endpoint is used when a user taps on a grouped pin to see all locations
    in that group.

    ## Request Parameters:
    - **ids**: Comma-separated list of location UUIDs (maximum 100)
    - **include_sources**: Include data from all scrapers (default: true)
    - **include_schedule**: Include schedule information (default: true)

    ## Response:
    Returns detailed information for each location including:
    - Canonical (best) data
    - All source variations
    - Merged schedule information
    - Data quality metrics

    ## Use Case:
    When a user taps a grouped pin showing "5 locations", this endpoint
    fetches the details for all 5 locations in that group.
    """
    # Parse and validate IDs
    id_list = [id.strip() for id in ids.split(",") if id.strip()]

    if not id_list:
        raise HTTPException(400, "No location IDs provided")

    if len(id_list) > 100:
        raise HTTPException(400, "Maximum 100 locations can be fetched at once")

    # Validate UUIDs
    validated_ids = []
    for id_str in id_list:
        try:
            # Validate it's a proper UUID format
            UUID(id_str)
            validated_ids.append(id_str)
        except ValueError:
            raise HTTPException(400, f"Invalid UUID format: {id_str}")

    # Get locations from service
    service = ConsumerLocationService(session)
    locations = await service.get_multiple_locations(
        location_ids=validated_ids,
        include_sources=include_sources,
        include_schedule=include_schedule,
    )

    # Note: Similarities analysis would be added in future phase
    return MultiLocationResponse(locations=locations, similarities=None)


@router.get("/locations/{location_id}", response_model=SingleLocationResponse)
async def get_location_detail(
    location_id: UUID,
    request: Request,
    include_nearby: bool = Query(False, description="Include nearby locations"),
    nearby_radius: int = Query(
        500, ge=0, le=5000, description="Radius in meters for nearby locations"
    ),
    include_history: bool = Query(False, description="Include version history"),
    session: AsyncSession = Depends(get_session),
) -> SingleLocationResponse:
    """
    Get comprehensive details for a single location.

    This endpoint returns all available information for a specific location.

    ## Request Parameters:
    - **location_id**: UUID of the location
    - **include_nearby**: Include nearby locations (default: false)
    - **nearby_radius**: Search radius for nearby locations (default: 500m)
    - **include_history**: Include version history (default: false)

    ## Response:
    Returns comprehensive location data including:
    - Full canonical information
    - All source data with timestamps
    - Merged schedule from all sources
    - Optional nearby locations
    - Optional version history

    ## Use Case:
    When a user taps on a single location pin or selects a location
    from a group, this endpoint provides the full details view.
    """
    # Get location details from service
    service = ConsumerLocationService(session)
    result = await service.get_single_location(
        location_id=location_id,
        include_nearby=include_nearby,
        nearby_radius=nearby_radius,
        include_history=include_history,
    )

    if not result:
        raise HTTPException(404, "Location not found")

    return SingleLocationResponse(**result)