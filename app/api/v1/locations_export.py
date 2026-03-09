"""Locations export API endpoints."""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from app.core.db import get_session

router = APIRouter(prefix="/locations", tags=["locations"])


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

    params: Dict[str, Any] = {}

    # Add state filter with validation
    if state:
        # Validate state format - 2 letter code only
        if (
            isinstance(state, str)
            and len(state.strip()) == 2
            and state.strip().isalpha()
        ):
            sql += " AND a.state_province = :state"
            params["state"] = state.upper().strip()

    # Add confidence filter with validation
    if min_confidence:
        try:
            confidence_val = int(min_confidence)
            if 0 <= confidence_val <= 100:
                sql += " AND COALESCE(l.confidence_score, 50) >= :min_confidence"
                params["min_confidence"] = confidence_val
        except (ValueError, TypeError):
            # Invalid confidence value - skip this filter
            pass

    # Continue building query with parameterized limit
    sql += """
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
        LIMIT :limit
    """

    # Validate and add limit parameter
    try:
        validated_limit = min(max(int(limit), 1), 10000)  # Between 1-10000 for export
        params["limit"] = validated_limit
    except (ValueError, TypeError):
        params["limit"] = 1000  # Safe default for export

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
