"""PTF /locations endpoints.

Public, read-only, no auth. Returns Plentiful-shaped responses with
a `feeding_america_food_bank` enrichment block. Designed as a drop-in
for consumers of Plentiful's /map/locations and /map/location/:id.
"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery
from app.api.v1.partners.ptf.locations_schemas import (
    PtfLocationDetail,
    PtfLocationListItem,
)
from app.api.v1.partners.ptf.locations_transformer import (
    to_detail,
    to_list_item,
)
from app.core.db import get_session

logger = structlog.get_logger(__name__)

locations_router = APIRouter(tags=["partners"])


@locations_router.get(
    "/locations",
    response_model=list[PtfLocationListItem],
    summary="List PTF-shaped locations",
    description=(
        "Public read-only endpoint returning PPR locations in Plentiful's "
        "/map/locations wire shape, with a feeding_america_food_bank block "
        "populated when the location's ZIP matches a Feeding America "
        "regional food bank."
    ),
)
async def list_ptf_locations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    lat1: Optional[float] = Query(None, ge=-90, le=90),
    lng1: Optional[float] = Query(None, ge=-180, le=180),
    lat2: Optional[float] = Query(None, ge=-90, le=90),
    lng2: Optional[float] = Query(None, ge=-180, le=180),
    q: Optional[str] = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session),
) -> list[PtfLocationListItem]:
    bbox_parts = [lat1, lng1, lat2, lng2]
    provided = [p for p in bbox_parts if p is not None]
    if 0 < len(provided) < 4:
        raise HTTPException(
            status_code=422,
            detail="Bounding box requires all of lat1, lng1, lat2, lng2",
        )
    bbox = tuple(bbox_parts) if len(provided) == 4 else None  # type: ignore[assignment]

    query = PtfLocationsQuery(session)
    rows = await query.list_locations(limit=limit, offset=offset, bbox=bbox, q=q)
    return [to_list_item(row) for row in rows]


@locations_router.get(
    "/locations/{location_id}",
    response_model=PtfLocationDetail,
    summary="Get a single PTF-shaped location",
    responses={404: {"description": "Location not found"}},
)
async def get_ptf_location(
    location_id: str,
    session: AsyncSession = Depends(get_session),
) -> PtfLocationDetail:
    query = PtfLocationsQuery(session)
    row = await query.get_location(location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    schedules = await query.get_schedules(location_id)
    return to_detail(row, schedules=list(schedules))
