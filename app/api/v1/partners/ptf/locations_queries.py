"""SQL queries for PTF /locations.

Single query per request. The list and detail queries both LEFT JOIN
to `feeding_america_zip_coverage` so FA enrichment travels in the same
SELECT — no N+1.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_MIN_LIMIT = 1
_MAX_LIMIT = 200


def clamp_limit(value: int) -> int:
    return max(_MIN_LIMIT, min(_MAX_LIMIT, value))


def clamp_offset(value: int) -> int:
    return max(0, value)


# DISTINCT ON (l.id) collapses multi-address locations to one row.
# Physical address wins via ORDER BY address_type. FA join is via
# address.postal_code → feeding_america_zip_coverage.zip; for locations
# with multiple eligible FA matches, lowest fa_org_id wins (deterministic).
_LIST_SQL = """
SELECT DISTINCT ON (l.id)
    l.id,
    l.name,
    l.alternate_name AS short_name,
    l.description,
    l.latitude,
    l.longitude,
    l.organization_id,
    o.name AS org_name,
    o.description AS org_description,
    o.email AS org_email,
    o.website AS org_website,
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    p.number AS phone_number,
    fa.fa_org_id,
    fa.fa_org_name
FROM location l
LEFT JOIN organization o ON l.organization_id = o.id
LEFT JOIN address a ON a.location_id = l.id
LEFT JOIN phone p ON p.location_id = l.id
LEFT JOIN feeding_america_zip_coverage fa
       ON fa.zip = SUBSTR(a.postal_code, 1, 5)
WHERE (l.validation_status != 'rejected' OR l.validation_status IS NULL)
  AND l.latitude IS NOT NULL
  AND l.longitude IS NOT NULL
  {bbox}
  {qfilter}
ORDER BY l.id,
         CASE WHEN a.address_type = 'physical' THEN 0 ELSE 1 END,
         fa.fa_org_id NULLS LAST
LIMIT :limit OFFSET :offset
"""

_DETAIL_SQL = """
SELECT
    l.id,
    l.name,
    l.alternate_name AS short_name,
    l.description,
    l.latitude,
    l.longitude,
    l.organization_id,
    o.name AS org_name,
    o.description AS org_description,
    o.email AS org_email,
    o.website AS org_website,
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    p.number AS phone_number,
    fa.fa_org_id,
    fa.fa_org_name
FROM location l
LEFT JOIN organization o ON l.organization_id = o.id
LEFT JOIN address a ON a.location_id = l.id
LEFT JOIN phone p ON p.location_id = l.id
LEFT JOIN feeding_america_zip_coverage fa
       ON fa.zip = SUBSTR(a.postal_code, 1, 5)
WHERE l.id = :location_id
ORDER BY CASE WHEN a.address_type = 'physical' THEN 0 ELSE 1 END,
         fa.fa_org_id NULLS LAST
LIMIT 1
"""

_SCHEDULES_SQL = """
SELECT freq, byday, bymonthday, opens_at, closes_at, description
FROM schedule
WHERE location_id = :location_id
   OR service_id IN (
       SELECT service_id FROM service_at_location
       WHERE location_id = :location_id
   )
ORDER BY opens_at
"""


class PtfLocationsQuery:
    """All SQL for the PTF /locations endpoints in one place."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_locations(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        bbox: Optional[tuple[float, float, float, float]] = None,
        q: Optional[str] = None,
    ) -> Sequence[Any]:
        params: dict[str, Any] = {
            "limit": clamp_limit(limit),
            "offset": clamp_offset(offset),
        }
        bbox_clause = ""
        if bbox is not None:
            lat_min, lng_min, lat_max, lng_max = bbox
            bbox_clause = (
                "AND l.latitude BETWEEN :lat_min AND :lat_max "
                "AND l.longitude BETWEEN :lng_min AND :lng_max"
            )
            params.update(
                lat_min=lat_min,
                lng_min=lng_min,
                lat_max=lat_max,
                lng_max=lng_max,
            )

        q_clause = ""
        if q:
            pattern = f"%{q.lower()}%"
            q_clause = (
                "AND (LOWER(COALESCE(l.name, '')) ILIKE :q "
                "OR LOWER(COALESCE(l.alternate_name, '')) ILIKE :q)"
            )
            params["q"] = pattern

        sql = _LIST_SQL.format(bbox=bbox_clause, qfilter=q_clause)
        result = await self._session.execute(text(sql), params)
        return result.fetchall()

    async def get_location(self, location_id: str) -> Optional[Any]:
        result = await self._session.execute(
            text(_DETAIL_SQL), {"location_id": location_id}
        )
        return result.fetchone()

    async def get_schedules(self, location_id: str) -> Sequence[Any]:
        result = await self._session.execute(
            text(_SCHEDULES_SQL), {"location_id": location_id}
        )
        return result.fetchall()
