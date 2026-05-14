"""PTF /locations endpoints.

Public, read-only, no auth. Returns Plentiful-shaped responses with
a `feeding_america_food_bank` enrichment block. Designed as a drop-in
for consumers of Plentiful's /map/locations and /map/location/:id.

Caching: list responses are short-cached (60s, s-maxage 300s) so a
mobile map-pan that revisits the same bbox hits CloudFront, matching
Plentiful's Redis-15min posture. Detail is 5min cached.
"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery
from app.api.v1.partners.ptf.locations_schemas import (
    PtfLocationDetail,
    PtfLocationListItem,
)
from app.api.v1.partners.ptf.locations_transformer import (
    PtfRowIncomplete,
    to_detail,
    to_list_item,
)
from app.core.db import get_session

logger = structlog.get_logger(__name__)

locations_router = APIRouter(tags=["partners"])

_LIST_CACHE_CONTROL = "public, max-age=60, s-maxage=300"
_DETAIL_CACHE_CONTROL = "public, max-age=300, s-maxage=300"

# Minimum bbox side length, in SRID-4326 degrees. ~3 miles at the
# equator (0.0435 * 111km/deg = 4.83 km ≈ 3 mi); slightly less in real
# distance at higher US latitudes for longitude, which is fine for a
# floor. Clients zooming into a single block would otherwise see pins
# pop out of the response as the viewport edge clips them — this floor
# guarantees a ~3-mile margin around any small viewport.
_BBOX_MIN_SIZE_DEG = 0.0435


def _pad_bbox_to_min(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Expand small bboxes to a minimum side length around their center.

    Also incidentally normalizes min/max ordering, so callers that swap
    `lat1`/`lat2` (or `lng1`/`lng2`) still get a valid envelope. Inputs
    above the floor pass through untouched.
    """
    lat1, lng1, lat2, lng2 = bbox
    lat_min, lat_max = sorted((lat1, lat2))
    lng_min, lng_max = sorted((lng1, lng2))
    lat_center = (lat_min + lat_max) / 2
    lng_center = (lng_min + lng_max) / 2
    half = _BBOX_MIN_SIZE_DEG / 2
    if (lat_max - lat_min) < _BBOX_MIN_SIZE_DEG:
        lat_min = lat_center - half
        lat_max = lat_center + half
    if (lng_max - lng_min) < _BBOX_MIN_SIZE_DEG:
        lng_min = lng_center - half
        lng_max = lng_center + half
    return (lat_min, lng_min, lat_max, lng_max)


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
    response: Response,
    limit: int = Query(50, ge=1, le=500),
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
    bbox: Optional[tuple[float, float, float, float]] = (
        (
            float(bbox_parts[0]),  # type: ignore[arg-type]
            float(bbox_parts[1]),  # type: ignore[arg-type]
            float(bbox_parts[2]),  # type: ignore[arg-type]
            float(bbox_parts[3]),  # type: ignore[arg-type]
        )
        if len(provided) == 4
        else None
    )
    bbox_padded = False
    if bbox is not None:
        padded = _pad_bbox_to_min(bbox)
        if padded != bbox:
            bbox_padded = True
            bbox = padded

    log = logger.bind(
        endpoint="ptf_locations_list",
        limit=limit,
        offset=offset,
        has_bbox=bbox is not None,
        bbox_padded=bbox_padded,
        has_q=q is not None,
    )

    query = PtfLocationsQuery(session)
    rows = await query.list_locations(limit=limit, offset=offset, bbox=bbox, q=q)

    items: list[PtfLocationListItem] = []
    dropped = 0
    fa_matched = 0
    for row in rows:
        try:
            item = to_list_item(row)
        except PtfRowIncomplete as exc:
            # Defense-in-depth: SQL should have filtered these. Don't
            # poison the response with bad data — log and continue.
            log.warning(
                "ptf_row_skipped",
                row_id=str(getattr(row, "id", "?")),
                reason=str(exc),
            )
            dropped += 1
            continue
        items.append(item)
        if item.feeding_america_food_bank is not None:
            fa_matched += 1

    log.info(
        "ptf_locations_list_complete",
        returned=len(items),
        dropped=dropped,
        fa_matched=fa_matched,
        # Near-duplicate canonicals are collapsed at query time via a
        # tiered connected-components walk (tight ~50m always-merge,
        # loose ~200m gated by name/address similarity). See
        # `_LIST_SQL` in locations_queries.py.
        dedup_active=True,
    )
    response.headers["Cache-Control"] = _LIST_CACHE_CONTROL
    return items


@locations_router.get(
    "/locations/{location_id}",
    response_model=PtfLocationDetail,
    summary="Get a single PTF-shaped location",
    responses={404: {"description": "Location not found"}},
)
async def get_ptf_location(
    location_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> PtfLocationDetail:
    log = logger.bind(endpoint="ptf_location_detail", location_id=location_id)
    query = PtfLocationsQuery(session)
    row = await query.get_location(location_id)
    if row is None:
        log.info("ptf_location_not_found")
        raise HTTPException(status_code=404, detail="Location not found")
    schedules = await query.get_schedules(location_id)
    try:
        detail = to_detail(row, schedules=list(schedules))
    except PtfRowIncomplete as exc:
        # Same defense-in-depth as the list endpoint.
        log.warning("ptf_location_detail_incomplete", reason=str(exc))
        raise HTTPException(status_code=404, detail="Location data incomplete")
    log.info(
        "ptf_location_detail_complete",
        has_fa_match=detail.feeding_america_food_bank is not None,
        schedule_rows=len(schedules) if schedules else 0,
    )
    response.headers["Cache-Control"] = _DETAIL_CACHE_CONTROL
    return detail
