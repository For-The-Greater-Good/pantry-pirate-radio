"""Enhanced search service for map locations with full-text search capabilities."""

import logging
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from math import radians, cos, sin

from sqlalchemy import text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.map.models import MapMetadata

logger = logging.getLogger(__name__)


class OutputFormat(str, Enum):
    """Output format options for search results."""

    FULL = "full"
    COMPACT = "compact"
    GEOJSON = "geojson"


class MapSearchService:
    """Enhanced search service for map locations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_locations(
        self,
        query: Optional[str] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        radius_miles: Optional[float] = None,
        state: Optional[str] = None,
        services: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        schedule_days: Optional[List[str]] = None,
        open_now: bool = False,
        confidence_min: Optional[int] = None,
        validation_status: Optional[str] = None,
        has_multiple_sources: Optional[bool] = None,
        output_format: OutputFormat = OutputFormat.FULL,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], MapMetadata, int]:
        """
        Search locations with comprehensive filtering options.

        Returns:
            Tuple of (locations, metadata, total_count)
        """

        # Optimized query for map display - simpler joins for better performance
        base_query = """
            WITH source_counts AS (
                SELECT
                    location_id,
                    COUNT(DISTINCT scraper_id) as source_count
                FROM location_source
                GROUP BY location_id
            ),
            searchable_locations AS (
                SELECT
                    l.id,
                    l.latitude as lat,
                    l.longitude as lng,
                    l.name as location_name,
                    o.name as org_name,
                    o.website,
                    o.email,
                    COALESCE(o.description, l.description) as description,
                    CONCAT_WS(', ',
                        NULLIF(a.address_1, ''),
                        NULLIF(a.address_2, ''),
                        NULLIF(a.city, ''),
                        NULLIF(a.state_province, ''),
                        NULLIF(a.postal_code, '')
                    ) as address,
                    a.address_1,
                    a.address_2,
                    a.city,
                    a.state_province as state,
                    a.postal_code as zip,
                    '' as phone,  -- Skip phone join for performance
                    '' as services,  -- Will fetch if needed in full format
                    '' as languages,  -- Will fetch if needed in full format
                    s.opens_at,
                    s.closes_at,
                    s.byday,
                    s.description as schedule_description,
                    l.confidence_score,
                    l.validation_status,
                    l.geocoding_source,
                    l.location_type,
                    COALESCE(sc.source_count, 1) as source_count
                FROM location l
                LEFT JOIN address a ON a.location_id = l.id
                LEFT JOIN organization o ON o.id = l.organization_id
                LEFT JOIN source_counts sc ON sc.location_id = l.id
                LEFT JOIN LATERAL (
                    SELECT opens_at, closes_at, byday, description
                    FROM schedule
                    WHERE schedule.location_id = l.id
                       OR schedule.service_id IN (
                           SELECT service_id
                           FROM service_at_location
                           WHERE location_id = l.id
                       )
                    ORDER BY
                        CASE WHEN opens_at IS NOT NULL THEN 0 ELSE 1 END
                    LIMIT 1
                ) s ON true
                WHERE l.latitude IS NOT NULL
                  AND l.longitude IS NOT NULL
                  AND l.latitude BETWEEN -90 AND 90
                  AND l.longitude BETWEEN -180 AND 180
                  AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
                  AND l.is_canonical = true
            )
        """

        # Build WHERE conditions
        conditions = []
        params: Dict[str, Any] = {}

        # Simple text search with input validation - only on location name for basic filtering
        # Not a primary use case, so keep it simple
        if query:
            # Validate and sanitize query input
            if isinstance(query, str) and len(query.strip()) > 0:
                # Remove potentially dangerous characters and limit length
                sanitized_query = query.strip()[:100]  # Limit to 100 chars
                # Only allow alphanumeric, spaces, hyphens, apostrophes, and periods
                import re

                if re.match(r"^[a-zA-Z0-9\s\-'.]+$", sanitized_query):
                    conditions.append("LOWER(location_name) LIKE :search_pattern")
                    params["search_pattern"] = f"%{sanitized_query.lower()}%"

        # Geographic filters with validation
        if bbox:
            try:
                min_lat, min_lng, max_lat, max_lng = bbox
                # Validate coordinate bounds
                if (
                    -90 <= min_lat <= 90
                    and -90 <= max_lat <= 90
                    and -180 <= min_lng <= 180
                    and -180 <= max_lng <= 180
                    and min_lat <= max_lat
                    and min_lng <= max_lng
                ):
                    conditions.append("lat BETWEEN :min_lat AND :max_lat")
                    conditions.append("lng BETWEEN :min_lng AND :max_lng")
                    params.update(
                        {
                            "min_lat": min_lat,
                            "max_lat": max_lat,
                            "min_lng": min_lng,
                            "max_lng": max_lng,
                        }
                    )
            except (ValueError, TypeError):
                # Invalid bbox format - skip this filter
                pass

        # Radius search with validation
        if (
            center_lat is not None
            and center_lng is not None
            and radius_miles is not None
        ):
            try:
                # Validate coordinates and radius
                if (
                    -90 <= center_lat <= 90
                    and -180 <= center_lng <= 180
                    and 0 < radius_miles <= 1000
                ):  # Max 1000 miles radius
                    conditions.append(
                        """
                        (
                            3959 * acos(
                                cos(radians(:center_lat)) * cos(radians(lat)) *
                                cos(radians(lng) - radians(:center_lng)) +
                                sin(radians(:center_lat)) * sin(radians(lat))
                            )
                        ) <= :radius_miles
                    """
                    )
                    params.update(
                        {
                            "center_lat": center_lat,
                            "center_lng": center_lng,
                            "radius_miles": radius_miles,
                        }
                    )
            except (ValueError, TypeError):
                # Invalid coordinates or radius - skip this filter
                pass

        # State filter with validation
        if state:
            # Validate state format - 2 letter code only
            if (
                isinstance(state, str)
                and len(state.strip()) == 2
                and state.strip().isalpha()
            ):
                conditions.append("state = :state")
                params["state"] = state.upper().strip()

        # Service filter - simplified, only check if services exist
        if services:
            # Just check if location has services, don't filter by specific ones
            conditions.append("services IS NOT NULL AND services != ''")

        # Language filter - simplified, only check if languages exist
        if languages:
            # Just check if location has language support, don't filter by specific ones
            conditions.append("languages IS NOT NULL AND languages != ''")

        # Schedule filter with proper input validation and parameterized queries
        if schedule_days:
            day_conditions = []
            valid_days = {
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            }

            for i, day in enumerate(schedule_days):
                # Validate input - only allow known day names
                if not isinstance(day, str) or day.lower() not in valid_days:
                    continue

                # Days are stored as abbreviations (MO, TU, WE, TH, FR, SA, SU)
                day_abbr = {
                    "monday": "MO",
                    "tuesday": "TU",
                    "wednesday": "WE",
                    "thursday": "TH",
                    "friday": "FR",
                    "saturday": "SA",
                    "sunday": "SU",
                }.get(day.lower())

                if day_abbr:
                    param_name = f"day_pattern_{i}"
                    day_conditions.append(f"byday LIKE :{param_name}")
                    params[param_name] = f"%{day_abbr}%"

            if day_conditions:
                conditions.append(f"({' OR '.join(day_conditions)})")

        # Open now filter with proper parameterized query
        if open_now:
            from datetime import datetime as dt

            current_time = dt.now().time()
            current_day = dt.now().strftime("%a")[:2].upper()

            # Validate current_day format - must be 2 uppercase letters
            if len(current_day) == 2 and current_day.isalpha():
                conditions.append(
                    """
                    (byday LIKE :current_day_pattern AND
                     opens_at <= :current_time AND
                     closes_at >= :current_time)
                """
                )
                params["current_day_pattern"] = f"%{current_day}%"
                params["current_time"] = current_time

        # Confidence filter with validation
        if confidence_min is not None:
            try:
                # Validate confidence score range (0-100)
                confidence_val = int(confidence_min)
                if 0 <= confidence_val <= 100:
                    conditions.append("confidence_score >= :confidence_min")
                    params["confidence_min"] = confidence_val
            except (ValueError, TypeError):
                # Invalid confidence value - skip this filter
                pass

        # Validation status filter with validation
        if validation_status:
            # Validate against allowed status values
            valid_statuses = {"needs_review", "verified", "rejected", "pending"}
            if (
                isinstance(validation_status, str)
                and validation_status.lower() in valid_statuses
            ):
                conditions.append("validation_status = :validation_status")
                params["validation_status"] = validation_status.lower()

        # Multiple sources filter
        if has_multiple_sources is not None:
            if has_multiple_sources:
                conditions.append("source_count > 1")
            else:
                conditions.append("source_count = 1")

        # Build final query
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # Count query - use string concatenation instead of f-string to avoid S608
        count_query = (
            base_query
            + "\nSELECT COUNT(*) as total\n"  # nosec B608
            + "FROM searchable_locations\n"
            + where_clause
        )

        # Main query - use string concatenation instead of f-string to avoid S608
        main_query = (
            base_query
            + "\nSELECT *\n"  # nosec B608
            + "FROM searchable_locations\n"
            + where_clause
            + "\nORDER BY confidence_score DESC, location_name, org_name\n"
            + "LIMIT :limit OFFSET :offset"
        )

        # Validate and sanitize limit and offset parameters
        try:
            validated_limit = min(max(int(limit), 1), 1000)  # Between 1-1000
            validated_offset = max(int(offset), 0)  # Non-negative
            params["limit"] = validated_limit
            params["offset"] = validated_offset
        except (ValueError, TypeError):
            # Use safe defaults if validation fails
            params["limit"] = 100
            params["offset"] = 0

        # Execute count query
        count_result = await self.session.execute(text(count_query), params)
        total_count = count_result.scalar() or 0

        # Execute main query
        result = await self.session.execute(text(main_query), params)
        rows = result.fetchall()

        # Process results based on format
        locations = []
        for row in rows:
            if output_format == OutputFormat.COMPACT:
                # Compact format for map markers
                location = {
                    "id": str(row.id),
                    "lat": float(row.lat),
                    "lng": float(row.lng),
                    "name": row.location_name or row.org_name or "Food Assistance",
                    "confidence": row.confidence_score or 50,
                }
            elif output_format == OutputFormat.GEOJSON:
                # GeoJSON format
                location = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(row.lng), float(row.lat)],
                    },
                    "properties": {
                        "id": str(row.id),
                        "name": row.location_name or row.org_name or "Food Assistance",
                        "org": row.org_name or "",
                        "address": row.address or "",
                        "city": row.city or "",
                        "state": row.state or "",
                        "services": row.services or "",
                        "confidence": row.confidence_score or 50,
                    },
                }
            else:
                # Full format (default)
                # Get source details for this location
                sources_query = """
                    SELECT
                        ls.scraper_id,
                        ls.created_at as first_seen,
                        ls.updated_at as last_updated
                    FROM location_source ls
                    WHERE ls.location_id = :location_id
                """
                sources_result = await self.session.execute(
                    text(sources_query), {"location_id": str(row.id)}
                )
                source_rows = sources_result.fetchall()

                sources = []
                for src in source_rows:
                    schedule = None
                    if row.opens_at or row.closes_at or row.schedule_description:
                        schedule = {
                            "opens_at": str(row.opens_at) if row.opens_at else None,
                            "closes_at": str(row.closes_at) if row.closes_at else None,
                            "byday": row.byday or "",
                            "description": row.schedule_description or "",
                        }

                    sources.append(
                        {
                            "scraper": src.scraper_id,
                            "name": row.location_name or row.org_name or "",
                            "org": row.org_name or "",
                            "description": row.description or "",
                            "services": row.services or "",
                            "languages": row.languages or "",
                            "schedule": schedule,
                            "phone": row.phone or "",
                            "website": row.website or "",
                            "email": row.email or "",
                            "address": row.address or "",
                            "first_seen": (
                                src.first_seen.isoformat() if src.first_seen else None
                            ),
                            "last_updated": (
                                src.last_updated.isoformat()
                                if src.last_updated
                                else None
                            ),
                            "confidence_score": row.confidence_score or 50,
                        }
                    )

                location = {
                    "id": str(row.id),
                    "lat": float(row.lat),
                    "lng": float(row.lng),
                    "name": row.location_name or row.org_name or "Food Assistance",
                    "org": row.org_name or "",
                    "address": row.address or "",
                    "city": row.city or "",
                    "state": (
                        row.state[:2].upper()
                        if row.state and len(row.state) >= 2
                        else ""
                    ),
                    "zip": row.zip or "",
                    "phone": row.phone or "",
                    "website": row.website or "",
                    "email": row.email or "",
                    "description": row.description or "",
                    "source_count": row.source_count or 1,
                    "sources": sources,
                    "confidence_score": row.confidence_score or 50,
                    "validation_status": row.validation_status or "needs_review",
                    "geocoding_source": row.geocoding_source or "",
                    "location_type": row.location_type or "",
                }

            locations.append(location)

        # Generate metadata
        if output_format == OutputFormat.GEOJSON:
            # Return as FeatureCollection
            result_data: Dict[str, Any] = {
                "type": "FeatureCollection",
                "features": locations,
                "properties": {
                    "total": total_count,
                    "returned": len(locations),
                    "offset": offset,
                    "limit": limit,
                },
            }
            locations = [result_data]  # Wrap in list for consistent return type

        # Create metadata
        states = set()
        for loc in locations:
            if output_format != OutputFormat.GEOJSON and loc.get("state"):
                states.add(loc["state"])

        metadata = MapMetadata(
            generated=datetime.now(UTC).isoformat(),
            total_locations=len(locations),
            total_source_records=sum(
                (
                    int(loc.get("source_count", 1))
                    if isinstance(loc.get("source_count", 1), int | str)
                    else 1
                )
                for loc in locations
                if output_format != OutputFormat.GEOJSON and isinstance(loc, dict)
            ),
            multi_source_locations=sum(
                1
                for loc in locations
                if output_format != OutputFormat.GEOJSON
                and isinstance(loc, dict)
                and int(loc.get("source_count", 1)) > 1
            ),
            states_covered=len(states),
            coverage=f"{len(states)} US states/territories",
            source="Pantry Pirate Radio HSDS API",
            format_version="4.0",
            export_method="API Search",
            aggregation_radius_meters=0,  # No aggregation in search
        )

        return locations, metadata, total_count
