"""Beacon partner sync endpoint — rich location data for static site generation."""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.beacon.models import (
    BeaconRedirectsResponse,
    BeaconSyncResponse,
)
from app.api.v1.partners.beacon.services import (
    BeaconRedirectService,
    BeaconSyncService,
)
from app.core.db import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/partners/beacon", tags=["partners"])


@router.get(
    "/sync",
    response_model=BeaconSyncResponse,
    summary="Sync locations for beacon static site",
    description=(
        "Returns qualified locations with full sub-entities (schedules, phones, "
        "languages, accessibility) for rendering static mini-site pages. "
        "Cursor-based pagination, incremental sync via updated_since, "
        "and optional state filtering."
    ),
)
async def beacon_sync(
    request: Request,
    cursor: Optional[str] = Query(
        None, description="Pagination cursor from previous response"
    ),
    page_size: int = Query(
        1000, ge=1, le=5000, description="Records per page (max 5000)"
    ),
    updated_since: Optional[datetime] = Query(
        None,
        description="ISO 8601 datetime for incremental sync",
    ),
    state: Optional[str] = Query(
        None,
        description="Filter by 2-letter state code (e.g. IL)",
    ),
    min_confidence: int = Query(
        60,
        ge=0,
        le=100,
        description="Minimum confidence score",
    ),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Beacon partner data sync endpoint."""
    service = BeaconSyncService(session, min_confidence=min_confidence)
    try:
        result = await service.sync(
            page_size=page_size,
            cursor=cursor,
            updated_since=updated_since,
            state_filter=state.upper() if state else None,
        )
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e))

    etag = result["meta"]["etag"]

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304)

    response_model = BeaconSyncResponse(**result)

    return JSONResponse(
        content=response_model.model_dump(mode="json"),
        headers={
            "etag": etag,
            "cache-control": "private, max-age=300",
        },
    )


@router.get(
    "/redirects",
    response_model=BeaconRedirectsResponse,
    summary="Dead-URL -> surviving-canonical map for beacon redirects",
    description=(
        "Returns soft-deleted (deduplicated) location ids mapped to their "
        "surviving canonical location's address components. Beacon uses this to "
        "publish 301 redirects for URLs whose pages it has deleted. Only "
        "redirects with a live canonical survivor are returned; the transitive "
        "survivor chain is followed to its terminal. Read-only; returns an empty "
        "list when no dedup audit history exists."
    ),
)
async def beacon_redirects(
    cursor: Optional[str] = Query(
        None, description="Pagination cursor (last dead_id) from previous response"
    ),
    page_size: int = Query(
        5000, ge=1, le=10000, description="Records per page (max 10000)"
    ),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Beacon dead-URL redirect map endpoint."""
    service = BeaconRedirectService(session)
    result = await service.redirects(page_size=page_size, cursor=cursor)
    response_model = BeaconRedirectsResponse(**result)
    return JSONResponse(
        content=response_model.model_dump(mode="json"),
        headers={"cache-control": "private, max-age=300"},
    )
