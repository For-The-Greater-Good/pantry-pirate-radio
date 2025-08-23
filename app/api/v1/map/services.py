"""Service layer for map data aggregation and processing."""

import logging
from datetime import datetime, UTC
from math import radians, cos, sin, asin, sqrt
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.map.models import (
    MapLocation,
    MapSource,
    MapSchedule,
    MapMetadata,
    StateInfo,
)
from app.core.state_mapping import normalize_state_to_code, VALID_STATE_CODES

logger = logging.getLogger(__name__)


class MapDataService:
    """Service for fetching and aggregating map data."""

    def __init__(self, session: AsyncSession, grouping_radius_meters: int = 150):
        self.session = session
        self.grouping_radius_meters = grouping_radius_meters

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great circle distance between two points in meters."""
        # Radius of earth in meters
        R = 6371000

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        return R * c

    async def get_locations_for_map(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        state: Optional[str] = None,
        confidence_min: Optional[int] = None,
        validation_status: Optional[str] = None,
        limit: int = 10000,
    ) -> Tuple[List[Dict[str, Any]], MapMetadata]:
        """Fetch locations for map display with optional filters."""

        # Build the query
        query = """
            WITH location_phones AS (
                SELECT
                    COALESCE(p.location_id, p.organization_id) as ref_id,
                    p.location_id,
                    p.organization_id,
                    MIN(p.number || COALESCE(' x' || p.extension, '')) as phone_number
                FROM phone p
                GROUP BY p.location_id, p.organization_id
            ),
            location_services AS (
                SELECT
                    sal.location_id,
                    STRING_AGG(DISTINCT s.name, ', ' ORDER BY s.name) as services
                FROM service_at_location sal
                JOIN service s ON s.id = sal.service_id
                GROUP BY sal.location_id
            ),
            location_languages AS (
                SELECT
                    l.location_id,
                    STRING_AGG(DISTINCT l.name, ', ' ORDER BY l.name) as languages
                FROM language l
                WHERE l.location_id IS NOT NULL
                GROUP BY l.location_id
            ),
            location_schedules AS (
                SELECT DISTINCT ON (sal.location_id)
                    sal.location_id,
                    s.opens_at,
                    s.closes_at,
                    s.byday,
                    s.description as schedule_description
                FROM schedule s
                JOIN service_at_location sal ON s.service_id = sal.service_id
                WHERE sal.location_id IS NOT NULL
                  AND (s.opens_at IS NOT NULL OR s.closes_at IS NOT NULL OR s.description IS NOT NULL)
                ORDER BY sal.location_id, s.opens_at, s.closes_at
            )
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
                lp.phone_number as phone,
                -- Source information
                ls.scraper_id,
                ls.created_at as first_seen,
                ls.updated_at as last_updated,
                -- Additional data
                lsrv.services,
                llang.languages,
                lsch.opens_at,
                lsch.closes_at,
                lsch.byday,
                lsch.schedule_description,
                -- Validation data
                l.confidence_score,
                l.validation_status,
                l.validation_notes,
                l.geocoding_source,
                l.location_type,
                l.is_canonical
            FROM location l
            JOIN location_source ls ON ls.location_id = l.id
            LEFT JOIN address a ON a.location_id = l.id
            LEFT JOIN organization o ON o.id = l.organization_id
            LEFT JOIN location_phones lp ON (lp.location_id = l.id OR (lp.location_id IS NULL AND lp.organization_id = o.id))
            LEFT JOIN location_services lsrv ON lsrv.location_id = l.id
            LEFT JOIN location_languages llang ON llang.location_id = l.id
            LEFT JOIN location_schedules lsch ON lsch.location_id = l.id
            WHERE l.latitude IS NOT NULL
              AND l.longitude IS NOT NULL
              AND l.latitude BETWEEN -90 AND 90
              AND l.longitude BETWEEN -180 AND 180
              AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
        """

        # Add filters
        conditions = []
        params: Dict[str, Any] = {}

        if bbox:
            min_lat, min_lng, max_lat, max_lng = bbox
            conditions.append("l.latitude BETWEEN :min_lat AND :max_lat")
            conditions.append("l.longitude BETWEEN :min_lng AND :max_lng")
            params.update(
                {
                    "min_lat": min_lat,
                    "max_lat": max_lat,
                    "min_lng": min_lng,
                    "max_lng": max_lng,
                }
            )

        if state:
            conditions.append("a.state_province = :state")
            params["state"] = state.upper()

        if confidence_min is not None:
            conditions.append("l.confidence_score >= :confidence_min")
            params["confidence_min"] = confidence_min

        if validation_status:
            conditions.append("l.validation_status = :validation_status")
            params["validation_status"] = validation_status

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += f" ORDER BY l.latitude, l.longitude, ls.scraper_id LIMIT {limit}"

        # Execute query
        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        # Process and group locations
        locations_dict: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            location_id = str(row.id)

            if location_id not in locations_dict:
                locations_dict[location_id] = {"row": row, "sources": []}

            # Add source information
            if row.scraper_id:
                schedule = None
                if row.opens_at or row.closes_at or row.schedule_description:
                    schedule = {
                        "opens_at": str(row.opens_at) if row.opens_at else None,
                        "closes_at": str(row.closes_at) if row.closes_at else None,
                        "byday": row.byday or "",
                        "description": row.schedule_description or "",
                    }

                source = {
                    "scraper": row.scraper_id,
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
                        row.first_seen.isoformat() if row.first_seen else None
                    ),
                    "last_updated": (
                        row.last_updated.isoformat() if row.last_updated else None
                    ),
                    "confidence_score": row.confidence_score or 50,
                }

                # Avoid duplicate sources
                if not any(
                    s["scraper"] == source["scraper"]
                    for s in locations_dict[location_id]["sources"]
                ):
                    locations_dict[location_id]["sources"].append(source)

        # Create aggregated locations
        locations = []
        for loc_data in locations_dict.values():
            row = loc_data["row"]

            # Validate state code
            state_value = row.state or ""
            if len(state_value) > 2:
                if len(state_value) >= 2 and state_value[:2].isalpha():
                    state_value = state_value[:2].upper()
                else:
                    state_value = ""

            location = {
                "id": str(row.id),
                "lat": float(row.lat),
                "lng": float(row.lng),
                "name": row.location_name or row.org_name or "Food Assistance Location",
                "org": row.org_name or "",
                "address": row.address or "",
                "city": row.city or "",
                "state": state_value,
                "zip": row.zip or "",
                "phone": row.phone or "",
                "website": row.website or "",
                "email": row.email or "",
                "description": row.description or "",
                "source_count": len(loc_data["sources"]),
                "sources": loc_data["sources"],
                "confidence_score": row.confidence_score or 50,
                "validation_status": row.validation_status or "needs_review",
                "geocoding_source": row.geocoding_source or "",
                "location_type": row.location_type or "",
            }
            locations.append(location)

        # Generate metadata
        states = set(loc["state"] for loc in locations if loc["state"])
        total_sources = sum(int(loc["source_count"]) for loc in locations)
        multi_source = sum(1 for loc in locations if int(loc["source_count"]) > 1)

        metadata = MapMetadata(
            generated=datetime.now(UTC).isoformat(),
            total_locations=len(locations),
            total_source_records=total_sources,
            multi_source_locations=multi_source,
            states_covered=len(states),
            coverage=f"{len(states)} US states/territories",
            source="Pantry Pirate Radio HSDS API",
            format_version="4.0",
            export_method="API Query",
            aggregation_radius_meters=self.grouping_radius_meters,
        )

        return locations, metadata

    async def get_states_coverage(self) -> List[StateInfo]:
        """Get coverage information for all states."""

        query = """
            SELECT
                a.state_province as state_code,
                COUNT(DISTINCT l.id) as location_count,
                MIN(l.latitude) as min_lat,
                MAX(l.latitude) as max_lat,
                MIN(l.longitude) as min_lng,
                MAX(l.longitude) as max_lng,
                MAX(l.updated_at) as last_updated
            FROM location l
            LEFT JOIN address a ON a.location_id = l.id
            WHERE l.latitude IS NOT NULL
              AND l.longitude IS NOT NULL
              AND l.is_canonical = true
              AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
              AND a.state_province IS NOT NULL
              AND a.state_province != ''
            GROUP BY a.state_province
            ORDER BY location_count DESC
        """

        result = await self.session.execute(text(query))
        rows = result.fetchall()

        states = []
        state_names = {
            "AL": "Alabama",
            "AK": "Alaska",
            "AZ": "Arizona",
            "AR": "Arkansas",
            "CA": "California",
            "CO": "Colorado",
            "CT": "Connecticut",
            "DE": "Delaware",
            "FL": "Florida",
            "GA": "Georgia",
            "HI": "Hawaii",
            "ID": "Idaho",
            "IL": "Illinois",
            "IN": "Indiana",
            "IA": "Iowa",
            "KS": "Kansas",
            "KY": "Kentucky",
            "LA": "Louisiana",
            "ME": "Maine",
            "MD": "Maryland",
            "MA": "Massachusetts",
            "MI": "Michigan",
            "MN": "Minnesota",
            "MS": "Mississippi",
            "MO": "Missouri",
            "MT": "Montana",
            "NE": "Nebraska",
            "NV": "Nevada",
            "NH": "New Hampshire",
            "NJ": "New Jersey",
            "NM": "New Mexico",
            "NY": "New York",
            "NC": "North Carolina",
            "ND": "North Dakota",
            "OH": "Ohio",
            "OK": "Oklahoma",
            "OR": "Oregon",
            "PA": "Pennsylvania",
            "RI": "Rhode Island",
            "SC": "South Carolina",
            "SD": "South Dakota",
            "TN": "Tennessee",
            "TX": "Texas",
            "UT": "Utah",
            "VT": "Vermont",
            "VA": "Virginia",
            "WA": "Washington",
            "WV": "West Virginia",
            "WI": "Wisconsin",
            "WY": "Wyoming",
            "DC": "District of Columbia",
        }

        for row in rows:
            state_code = row.state_code[:2].upper() if row.state_code else ""
            if state_code in VALID_STATE_CODES:
                states.append(
                    StateInfo(
                        state_code=state_code,
                        state_name=state_names.get(state_code, state_code),
                        location_count=row.location_count,
                        bounds=(
                            {
                                "min_lat": row.min_lat,
                                "max_lat": row.max_lat,
                                "min_lng": row.min_lng,
                                "max_lng": row.max_lng,
                            }
                            if all([row.min_lat, row.max_lat, row.min_lng, row.max_lng])
                            else None
                        ),
                        last_updated=row.last_updated,
                    )
                )

        return states
