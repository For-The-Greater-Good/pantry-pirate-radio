"""PTF partner sync endpoint — pre-formatted data for Plentiful integration."""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.models import PtfSyncResponse
from app.api.v1.partners.ptf.services import PtfSyncService
from app.core.db import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/partners/ptf", tags=["partners"])


@router.get(
    "/sync",
    response_model=PtfSyncResponse,
    summary="Sync locations for PTF partner",
    description=(
        "Returns all qualified locations pre-formatted for PTF's Organization model. "
        "Supports cursor-based pagination and incremental sync via updated_since. "
        "Includes ETag support for cache validation (If-None-Match header)."
    ),
)
async def ptf_sync(
    request: Request,
    cursor: Optional[str] = Query(
        None, description="Pagination cursor from previous response"
    ),
    page_size: int = Query(
        1000, ge=1, le=1000, description="Records per page (max 1000)"
    ),
    updated_since: Optional[datetime] = Query(
        None,
        description="ISO 8601 datetime for incremental sync",
    ),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """PTF partner data sync endpoint."""
    service = PtfSyncService(session)
    try:
        result = await service.sync(
            page_size=page_size, cursor=cursor, updated_since=updated_since
        )
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e))

    etag = result["meta"]["etag"]

    # ETag-based 304
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304)

    # Serialize via Pydantic for validation
    response_model = PtfSyncResponse(**result)

    return JSONResponse(
        content=response_model.model_dump(mode="json"),
        headers={
            "etag": etag,
            "cache-control": "private, max-age=3600",
        },
    )
