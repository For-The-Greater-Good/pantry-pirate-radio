"""PTF partner sync service — queries, transforms, and paginates location data."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from collections.abc import Sequence
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.formatters import (
    build_additional_info,
    filter_website,
    format_schedule,
    humanize_scraper_id,
    normalize_phone,
    parse_zip_code,
    state_to_timezone,
)

logger = structlog.get_logger(__name__)


def _encode_cursor(confidence_score: int, location_id: str) -> str:
    """Encode pagination cursor as base64 JSON."""
    payload = json.dumps({"c": confidence_score, "i": location_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """Decode pagination cursor. Returns (confidence_score, location_id) or (None, None)."""
    if not cursor:
        return None, None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor))
        return payload["c"], payload["i"]
    except Exception:
        return None, None


class PtfSyncService:
    """Orchestrates PTF sync: SQL queries + batch lookups + formatting."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def sync(
        self,
        page_size: int = 1000,
        cursor: Optional[str] = None,
        updated_since: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Execute sync and return formatted response dict."""
        log = logger.bind(
            page_size=page_size,
            has_cursor=cursor is not None,
            updated_since=str(updated_since) if updated_since else None,
        )
        log.info("ptf_sync_request")

        cursor_conf, cursor_id = _decode_cursor(cursor)

        # 1. Get ETag material
        etag = await self._compute_etag(updated_since)

        # 2. Get total count
        total = await self._count_qualified(updated_since)

        # 3. Main query — filtered, deduped, paginated
        locations = await self._query_locations(
            page_size=page_size,
            cursor_conf=cursor_conf,
            cursor_id=cursor_id,
            updated_since=updated_since,
        )

        if not locations:
            return self._build_response([], total, etag, page_size)

        # 4. Batch queries for related data
        location_ids = [row.id for row in locations]
        org_ids = [row.organization_id for row in locations if row.organization_id]

        phones, schedules, services, sources = await self._batch_lookups(
            location_ids, org_ids
        )

        # 5. Transform to output shape
        organizations = []
        for loc in locations:
            org = self._transform_location(loc, phones, schedules, services, sources)
            organizations.append(org)

        log.info("ptf_sync_complete", returned=len(organizations), total=total)
        return self._build_response(organizations, total, etag, page_size)

    async def _compute_etag(self, updated_since: Optional[datetime]) -> str:
        """Compute ETag from max(updated_at) and count."""
        since_clause = ""
        params: dict[str, Any] = {}
        if updated_since:
            since_clause = "AND l.updated_at > :updated_since"
            params["updated_since"] = updated_since

        sql = """
            SELECT MAX(l.updated_at) as max_updated, COUNT(*) as total
            FROM location l
            WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
              AND l.confidence_score >= 10
              AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
        """
        query = text(sql + since_clause)  # nosec B608
        result = await self._session.execute(query, params)
        row = result.fetchone()

        max_updated = row.max_updated if row else None
        total = row.total if row else 0
        raw = f"{max_updated}:{total}"
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    def _build_qualified_cte(self, since_clause: str) -> str:
        """Build the qualified+deduped+winners CTE SQL fragment."""
        qualified = """
            WITH qualified AS (
                SELECT l.id FROM location l
                LEFT JOIN organization o ON l.organization_id = o.id
                LEFT JOIN address a ON a.location_id = l.id
                    AND a.address_type = 'physical'
                WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
                  AND l.confidence_score >= 10
                  AND (l.validation_status IS NULL
                       OR l.validation_status != 'rejected')
                  AND NOT (
                      EXISTS (SELECT 1 FROM location_source ls
                              WHERE ls.location_id = l.id
                              AND ls.scraper_id = 'plentiful')
                      AND NOT EXISTS (SELECT 1 FROM location_source ls
                                      WHERE ls.location_id = l.id
                                      AND ls.scraper_id != 'plentiful')
                  )
                  AND (
                      EXISTS (SELECT 1 FROM phone p
                              WHERE p.location_id = l.id)
                      OR o.email IS NOT NULL
                      OR o.website IS NOT NULL
                  )
                  AND NOT (a.state_province = 'NY' AND UPPER(TRIM(a.city)) IN
                    ('NEW YORK','BROOKLYN','BRONX','QUEENS',
                     'STATEN ISLAND','MANHATTAN'))
        """
        dedup = """
            ),
            deduped AS (
                SELECT l.id, l.confidence_score,
                  ST_ClusterDBSCAN(
                    ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326),
                    eps := 0.0005, minpoints := 1
                  ) OVER() as cluster_id
                FROM location l WHERE l.id IN (SELECT id FROM qualified)
            ),
            winners AS (
                SELECT DISTINCT ON (cluster_id) id
                FROM deduped
                ORDER BY cluster_id, confidence_score DESC NULLS LAST, id
            )
        """
        return qualified + since_clause + dedup  # nosec B608

    async def _count_qualified(self, updated_since: Optional[datetime]) -> int:
        """Count total qualified locations (for pagination metadata)."""
        since_clause = ""
        params: dict[str, Any] = {}
        if updated_since:
            since_clause = "AND l.updated_at > :updated_since"
            params["updated_since"] = updated_since

        cte = self._build_qualified_cte(since_clause)
        query = text(cte + " SELECT COUNT(*) FROM winners")  # nosec B608
        result = await self._session.execute(query, params)
        return result.scalar_one()

    async def _query_locations(
        self,
        page_size: int,
        cursor_conf: Optional[int],
        cursor_id: Optional[str],
        updated_since: Optional[datetime],
    ) -> Sequence[Any]:
        """Main CTE query: filter, dedup, paginate."""
        since_clause = ""
        cursor_clause = ""
        params: dict[str, Any] = {"page_size": page_size}

        if updated_since:
            since_clause = "AND l.updated_at > :updated_since"
            params["updated_since"] = updated_since

        if cursor_conf is not None and cursor_id is not None:
            cursor_clause = (
                "WHERE (w_loc.confidence_score, w_loc.id) "
                "< (:cursor_conf, :cursor_id)"
            )
            params["cursor_conf"] = cursor_conf
            params["cursor_id"] = cursor_id

        cte = self._build_qualified_cte(since_clause)
        select_sql = """
            SELECT w_loc.id, w_loc.name, w_loc.description,
                   w_loc.latitude, w_loc.longitude,
                   w_loc.confidence_score, w_loc.updated_at,
                   w_loc.organization_id,
                   o.name as org_name, o.description as org_description,
                   o.email, o.website as org_website,
                   a.address_1, a.address_2, a.city,
                   a.state_province, a.postal_code
            FROM winners w
            JOIN location w_loc ON w_loc.id = w.id
            LEFT JOIN organization o ON o.id = w_loc.organization_id
            LEFT JOIN address a ON a.location_id = w_loc.id
                AND a.address_type = 'physical'
        """
        order_sql = """
            ORDER BY w_loc.confidence_score DESC, w_loc.id DESC
            LIMIT :page_size
        """
        full_sql = cte + select_sql + cursor_clause + order_sql  # nosec B608
        query = text(full_sql)

        result = await self._session.execute(query, params)
        return result.fetchall()

    async def _batch_lookups(
        self, location_ids: list[str], org_ids: list[str]
    ) -> tuple[dict, dict, dict, dict]:
        """Run batch queries for phones, schedules, services, sources."""
        phones = await self._query_phones(location_ids, org_ids)
        schedules = await self._query_schedules(location_ids)
        services = await self._query_services(location_ids)
        sources = await self._query_sources(location_ids)
        return phones, schedules, services, sources

    async def _query_phones(
        self, location_ids: list[str], org_ids: list[str]
    ) -> dict[str, list[Any]]:
        """Batch query phones for all locations."""
        query = text(
            """
            SELECT p.location_id, p.organization_id, p.number,
                   p.type, p.extension, p.description
            FROM phone p
            WHERE p.location_id = ANY(:loc_ids)
               OR p.organization_id = ANY(:org_ids)
            ORDER BY p.type
        """
        )
        result = await self._session.execute(
            query, {"loc_ids": location_ids, "org_ids": org_ids}
        )
        phones: dict[str, list[Any]] = {}
        for row in result.fetchall():
            # Key by location_id; fall back to org_id for org-level phones
            key = row.location_id or row.organization_id
            if key not in phones:
                phones[key] = []
            phones[key].append(row)
        return phones

    async def _query_schedules(self, location_ids: list[str]) -> dict[str, list[Any]]:
        """Batch query schedules for all locations."""
        query = text(
            """
            SELECT COALESCE(s.location_id, sal.location_id) as location_id,
                   s.freq, s.byday, s.opens_at, s.closes_at, s.description
            FROM schedule s
            LEFT JOIN service_at_location sal
                ON s.service_at_location_id = sal.id
            WHERE s.location_id = ANY(:ids)
               OR sal.location_id = ANY(:ids)
            ORDER BY s.opens_at
        """
        )
        result = await self._session.execute(query, {"ids": location_ids})
        schedules: dict[str, list[Any]] = {}
        for row in result.fetchall():
            lid = row.location_id
            if lid not in schedules:
                schedules[lid] = []
            schedules[lid].append(row)
        return schedules

    async def _query_services(self, location_ids: list[str]) -> dict[str, list[str]]:
        """Batch query service names for all locations."""
        query = text(
            """
            SELECT sal.location_id, sv.name
            FROM service_at_location sal
            JOIN service sv ON sal.service_id = sv.id
            WHERE sal.location_id = ANY(:ids)
            ORDER BY sv.name
        """
        )
        result = await self._session.execute(query, {"ids": location_ids})
        services: dict[str, list[str]] = {}
        for row in result.fetchall():
            if row.location_id not in services:
                services[row.location_id] = []
            services[row.location_id].append(row.name)
        return services

    async def _query_sources(self, location_ids: list[str]) -> dict[str, list[str]]:
        """Batch query data sources for all locations."""
        query = text(
            """
            SELECT ls.location_id, ls.scraper_id
            FROM location_source ls
            WHERE ls.location_id = ANY(:ids)
        """
        )
        result = await self._session.execute(query, {"ids": location_ids})
        sources: dict[str, list[str]] = {}
        for row in result.fetchall():
            if row.location_id not in sources:
                sources[row.location_id] = []
            sources[row.location_id].append(row.scraper_id)
        return sources

    def _transform_location(
        self,
        loc: Any,
        phones: dict[str, list[Any]],
        schedules: dict[str, list[Any]],
        services: dict[str, list[str]],
        sources: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Transform a location row + batch data into PTF organization dict."""
        loc_id = loc.id

        # Phone: pick first valid, collect extras
        loc_phones = phones.get(loc_id, [])
        org_phones = phones.get(loc.organization_id, []) if loc.organization_id else []
        all_phones = loc_phones + org_phones
        primary_phone = None
        extra_phones: list[int] = []
        for p in all_phones:
            normalized = normalize_phone(p.number)
            if normalized is None:
                continue
            if primary_phone is None:
                primary_phone = normalized
            else:
                extra_phones.append(normalized)

        # Schedule
        sched_rows = schedules.get(loc_id, [])
        schedule_str = format_schedule(sched_rows)

        # Services
        service_names = services.get(loc_id, [])

        # Sources
        raw_sources = sources.get(loc_id, [])
        data_sources = []
        for s in raw_sources:
            humanized = humanize_scraper_id(s)
            if humanized:
                data_sources.append(humanized)

        # Website filtering
        website = filter_website(loc.org_website)

        # Timezone
        tz = state_to_timezone(loc.state_province) if loc.state_province else None

        # Additional info
        additional_info = build_additional_info(
            description=loc.description or loc.org_description,
            services=service_names if service_names else None,
            extra_phones=extra_phones if extra_phones else None,
        )

        return {
            "ppr_location_id": loc_id,
            "name": loc.name or loc.org_name or "Unknown",
            "latitude": float(loc.latitude),
            "longitude": float(loc.longitude),
            "address_street_1": loc.address_1 or "",
            "address_street_2": loc.address_2 or "",
            "city": loc.city or "",
            "state": loc.state_province or "",
            "zip_code": parse_zip_code(loc.postal_code),
            "phone": primary_phone,
            "website": website,
            "email": loc.email,
            "additional_info": additional_info,
            "schedule": schedule_str,
            "timezone": tz,
            "hide": 0,
            "boundless_id": None,
            "data_sources": data_sources,
            "confidence_score": loc.confidence_score or 0,
            "updated_at": loc.updated_at,
        }

    def _build_response(
        self,
        organizations: list[dict[str, Any]],
        total: int,
        etag: str,
        page_size: int,
    ) -> dict[str, Any]:
        """Build final response dict with meta."""
        has_more = len(organizations) == page_size
        cursor = None
        if has_more and organizations:
            last = organizations[-1]
            cursor = _encode_cursor(last["confidence_score"], last["ppr_location_id"])

        return {
            "meta": {
                "total_available": total,
                "returned": len(organizations),
                "cursor": cursor,
                "has_more": has_more,
                "generated_at": datetime.now(UTC),
                "etag": etag,
                "data_version": "1.0",
            },
            "organizations": organizations,
        }
