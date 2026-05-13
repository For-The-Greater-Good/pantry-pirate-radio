"""SQL queries for PTF /locations.

Single query per request. The list and detail queries both LEFT JOIN
to `feeding_america_zip_coverage` so FA enrichment travels in the same
SELECT — no N+1.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST

_MIN_LIMIT = 1
_MAX_LIMIT = 200


def clamp_limit(value: int) -> int:
    return max(_MIN_LIMIT, min(_MAX_LIMIT, value))


def clamp_offset(value: int) -> int:
    return max(0, value)


# Both queries below share the same tie-break invariants:
#  1. DISTINCT ON (l.id) collapses multi-address/multi-phone rows in the
#     list query; LIMIT 1 with the same ORDER BY does the same for detail.
#  2. Physical address wins via `address_type = 'physical'` filter on the
#     JOIN (rather than ORDER BY, so seq scans are smaller).
#  3. For multiple eligible FA crosswalk rows for one ZIP, lowest
#     `fa_org_id` wins (deterministic).
#  4. For multi-phone rows, lowest `phone.id` wins (deterministic — picks
#     the row that was inserted first).
#  5. Plentiful filters out Null Island (lat=0,lng=0); we mirror that.
#
# `qualifying_source` CTE: a location is FANO-qualifying iff it has at
# least one location_source row whose scraper_id is in the FANO allowlist
# AND whose source_type is NOT 'submarine' (submarine is enrichment, not
# discovery). The CASE-gate on fa_org_id/fa_org_name means a ZIP-only
# match (no qualifying source) yields NULL FA columns so the transformer
# does not emit a `feeding_america_food_bank` block — but `affiliations`
# (driven by `has_qualifying_source` alone) still gets "FANO" if a
# qualifying source exists, regardless of ZIP match.
#
# The CTE is inlined into both _LIST_SQL and _DETAIL_SQL rather than
# string-concatenated so bandit's B608 (hardcoded_sql_expressions) heuristic
# stays clean. Allowlist values are bound via SQLAlchemy `expanding=True`
# (see `_bind_allowlist`); no scraper IDs are interpolated into SQL text.
_LIST_SQL = """
WITH qualifying_source AS (
    SELECT location_id,
           BOOL_OR(true) AS has_qualifying_source
    FROM location_source
    WHERE scraper_id IN :allowlist
      AND (source_type IS NULL OR source_type != 'submarine')
    GROUP BY location_id
)
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
    CASE WHEN COALESCE(qs.has_qualifying_source, false)
         THEN fa.fa_org_id END AS fa_org_id,
    CASE WHEN COALESCE(qs.has_qualifying_source, false)
         THEN fa.fa_org_name END AS fa_org_name,
    COALESCE(qs.has_qualifying_source, false) AS has_qualifying_source,
    (fa.fa_org_id IS NOT NULL) AS zip_matched_fa
FROM location l
LEFT JOIN organization o ON l.organization_id = o.id
LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical'
LEFT JOIN phone p ON p.location_id = l.id
LEFT JOIN feeding_america_zip_coverage fa
       ON fa.zip = SUBSTR(a.postal_code, 1, 5)
LEFT JOIN qualifying_source qs ON qs.location_id = l.id
WHERE (l.validation_status != 'rejected' OR l.validation_status IS NULL)
  AND l.latitude IS NOT NULL
  AND l.longitude IS NOT NULL
  AND NOT (l.latitude = 0 AND l.longitude = 0)
  AND (l.name IS NOT NULL OR o.name IS NOT NULL)
  -- Require at least one piece of contact info OR a schedule. A location
  -- with neither is unreachable by the consuming app and shouldn't appear
  -- in the PTF feed. Empty strings count as missing (some scrapers store
  -- '' rather than NULL for absent values). Phone uses an explicit EXISTS
  -- rather than `p.id IS NOT NULL` from the LEFT JOIN above so the filter
  -- doesn't depend on which phone row the JOIN happens to pick — if any
  -- phone row has a real number, the location qualifies. Schedule existence
  -- uses schedule_location_id_idx (partial, WHERE location_id IS NOT NULL).
  AND (
      EXISTS (
          SELECT 1 FROM phone
          WHERE location_id = l.id
            AND number IS NOT NULL AND number != ''
      )
      OR (o.email IS NOT NULL AND o.email != '')
      OR (o.website IS NOT NULL AND o.website != '')
      OR EXISTS (SELECT 1 FROM schedule s WHERE s.location_id = l.id)
  )
  {bbox}
  {qfilter}
ORDER BY l.id,
         fa.fa_org_id NULLS LAST,
         p.id NULLS LAST
LIMIT :limit OFFSET :offset
"""

_DETAIL_SQL = """
WITH qualifying_source AS (
    SELECT location_id,
           BOOL_OR(true) AS has_qualifying_source
    FROM location_source
    WHERE scraper_id IN :allowlist
      AND (source_type IS NULL OR source_type != 'submarine')
    GROUP BY location_id
)
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
    CASE WHEN COALESCE(qs.has_qualifying_source, false)
         THEN fa.fa_org_id END AS fa_org_id,
    CASE WHEN COALESCE(qs.has_qualifying_source, false)
         THEN fa.fa_org_name END AS fa_org_name,
    COALESCE(qs.has_qualifying_source, false) AS has_qualifying_source,
    (fa.fa_org_id IS NOT NULL) AS zip_matched_fa
FROM location l
LEFT JOIN organization o ON l.organization_id = o.id
LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical'
LEFT JOIN phone p ON p.location_id = l.id
LEFT JOIN feeding_america_zip_coverage fa
       ON fa.zip = SUBSTR(a.postal_code, 1, 5)
LEFT JOIN qualifying_source qs ON qs.location_id = l.id
WHERE l.id = :location_id
  -- Mirror the list-query filter (including the empty-string check). A
  -- location with no contact info AND no schedule is not reachable and
  -- shouldn't be served. Returning empty here means the router responds
  -- 404, same as a truly-missing location.
  AND (
      EXISTS (
          SELECT 1 FROM phone
          WHERE location_id = l.id
            AND number IS NOT NULL AND number != ''
      )
      OR (o.email IS NOT NULL AND o.email != '')
      OR (o.website IS NOT NULL AND o.website != '')
      OR EXISTS (SELECT 1 FROM schedule s WHERE s.location_id = l.id)
  )
ORDER BY fa.fa_org_id NULLS LAST,
         p.id NULLS LAST
LIMIT 1
"""

# Tuple form for the `expanding=True` bindparam below. Tuple (not set/list)
# so SQLAlchemy expands it into a positional IN clause without re-hashing
# at bind time (frozenset iteration order is fine here — Postgres treats
# all permutations identically).
_FANO_ALLOWLIST_TUPLE: tuple[str, ...] = tuple(FANO_ALLOWLIST)


def _bind_allowlist(stmt: Any) -> Any:
    """Attach the `expanding=True` bind for the allowlist tuple.

    Required because SQLAlchemy 2 will not expand a Python sequence into
    an `IN (...)` clause unless the bindparam is declared with
    `expanding=True` (Constitution VII: parameterized queries, no string
    interpolation of allowlist members).
    """
    return stmt.bindparams(bindparam("allowlist", expanding=True))


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
            "allowlist": _FANO_ALLOWLIST_TUPLE,
        }
        bbox_clause = ""
        if bbox is not None:
            lat_min, lng_min, lat_max, lng_max = bbox
            # Use the GIST index `idx_location_coords` (init-scripts/
            # 02-spatial-index.sql). The expression below MUST match
            # the index's indexed expression exactly so the planner
            # uses it; the && (bbox overlap) operator on geometry is
            # what GIST is good at.
            bbox_clause = (
                "AND st_setsrid(st_makepoint("
                "CAST(l.longitude AS float8), CAST(l.latitude AS float8)"
                "), 4326) "
                "&& ST_MakeEnvelope(:lng_min, :lat_min, :lng_max, :lat_max, 4326)"
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
        result = await self._session.execute(_bind_allowlist(text(sql)), params)
        return result.fetchall()

    async def get_location(self, location_id: str) -> Optional[Any]:
        result = await self._session.execute(
            _bind_allowlist(text(_DETAIL_SQL)),
            {
                "location_id": location_id,
                "allowlist": _FANO_ALLOWLIST_TUPLE,
            },
        )
        return result.fetchone()

    async def get_schedules(self, location_id: str) -> Sequence[Any]:
        result = await self._session.execute(
            text(_SCHEDULES_SQL), {"location_id": location_id}
        )
        return result.fetchall()
