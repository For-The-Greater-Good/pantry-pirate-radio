"""Tightbeam API router — location management for field staff and plugins."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session

from .auth import require_api_key
from .models import (
    CallerIdentity,
    HistoryResponse,
    LocationDetail,
    LocationUpdateRequest,
    LocationUpdateResponse,
    MutationResponse,
    RestoreRequest,
    SearchResponse,
    SoftDeleteRequest,
)
from .services import TightbeamService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/tightbeam",
    tags=["tightbeam"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search locations",
    description="Multi-field search across locations by name, address, phone, etc.",
)
async def search_locations(
    q: str | None = Query(default=None, description="Free-text search"),
    name: str | None = Query(default=None, description="Filter by name"),
    address: str | None = Query(default=None, description="Filter by address"),
    city: str | None = Query(default=None, description="Filter by city"),
    state: str | None = Query(default=None, description="Filter by state"),
    zip_code: str | None = Query(default=None, description="Filter by ZIP"),
    phone: str | None = Query(default=None, description="Filter by phone"),
    email: str | None = Query(default=None, description="Filter by email"),
    website: str | None = Query(default=None, description="Filter by website"),
    include_rejected: bool = Query(
        default=False, description="Include soft-deleted locations"
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    """Search locations with multi-field filtering."""
    service = TightbeamService(session)
    return await service.search(
        q=q,
        name=name,
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        phone=phone,
        email=email,
        website=website,
        include_rejected=include_rejected,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/locations/{location_id}",
    response_model=LocationDetail,
    summary="Get location detail",
    description="Get a location with all source version records.",
)
async def get_location(
    location_id: str,
    session: AsyncSession = Depends(get_session),
) -> LocationDetail:
    """Get full location detail including source records."""
    service = TightbeamService(session)
    result = await service.get_location(location_id)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.get(
    "/locations/{location_id}/history",
    response_model=HistoryResponse,
    summary="Get change history",
    description="Full audit trail for a location.",
)
async def get_history(
    location_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> HistoryResponse:
    """Get the audit trail for a location."""
    service = TightbeamService(session)
    result = await service.get_history(location_id, limit=limit, offset=offset)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.put(
    "/locations/{location_id}",
    response_model=LocationUpdateResponse,
    summary="Update location",
    description="Human correction via append-only upsert with audit trail.",
)
async def update_location(
    location_id: str,
    body: LocationUpdateRequest,
    caller: CallerIdentity = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> LocationUpdateResponse:
    """Apply a human correction to a location (append-only)."""
    service = TightbeamService(session)
    result = await service.update_location(
        location_id=location_id,
        name=body.name,
        address_1=body.address_1,
        city=body.city,
        state=body.state,
        postal_code=body.postal_code,
        latitude=body.latitude,
        longitude=body.longitude,
        phone=body.phone,
        email=body.email,
        website=body.website,
        description=body.description,
        caller=caller,
        caller_context=body.caller_context,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.delete(
    "/locations/{location_id}",
    response_model=MutationResponse,
    summary="Soft-delete location",
    description="Soft-delete by setting validation_status to 'rejected'.",
)
async def delete_location(
    location_id: str,
    body: SoftDeleteRequest | None = None,
    caller: CallerIdentity = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> MutationResponse:
    """Soft-delete a location (sets validation_status='rejected')."""
    service = TightbeamService(session)
    result = await service.soft_delete(
        location_id=location_id,
        reason=body.reason if body else None,
        caller=caller,
        caller_context=body.caller_context if body else None,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.post(
    "/locations/{location_id}/restore",
    response_model=MutationResponse,
    summary="Restore location",
    description="Restore a soft-deleted location.",
)
async def restore_location(
    location_id: str,
    body: RestoreRequest | None = None,
    caller: CallerIdentity = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> MutationResponse:
    """Restore a soft-deleted location (sets validation_status='verified')."""
    service = TightbeamService(session)
    result = await service.restore(
        location_id=location_id,
        reason=body.reason if body else None,
        caller=caller,
        caller_context=body.caller_context if body else None,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result
