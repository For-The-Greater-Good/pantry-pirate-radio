"""Beacon partner sync service — full location data for static site generation.

Similar to PTF sync but returns structured sub-entities (schedules, phones,
languages, accessibility) instead of flattened strings.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from collections.abc import Sequence
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.beacon.models import (
    BeaconAccessibility,
    BeaconLanguage,
    BeaconLocation,
    BeaconPhone,
    BeaconSchedule,
)
from app.api.v1.partners.ptf.formatters import humanize_scraper_id

logger = structlog.get_logger(__name__)


def _encode_cursor(confidence_score: int, location_id: str) -> str:
    payload = json.dumps({"c": confidence_score, "i": location_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    if not cursor:
        return None, None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor))
        return payload["c"], payload["i"]
    except Exception as e:
        raise ValueError(f"Malformed pagination cursor: {e}") from e


# Minimum quality: has coordinates, not rejected, has address,
# AND is the canonical row (Tier-3 dedupe soft-deletes duplicates by
# flipping `is_canonical` to FALSE — those rows must never appear in
# beacon's sync output. Previously this was filtered as a side-effect
# of the address-repoint making `a.city IS NULL`; we make it explicit
# here so a future maintenance change can't silently leak soft-deleted
# rows back into the build).
_BASE_WHERE = """
    l.is_canonical = TRUE
    AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL
    AND l.confidence_score >= :min_confidence
    AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
    AND a.city IS NOT NULL AND a.state_province IS NOT NULL
"""


class BeaconSyncService:
    """Queries and transforms location data for beacon static site generation."""

    def __init__(self, session: AsyncSession, min_confidence: int = 60):
        self._session = session
        self._min_confidence = min_confidence

    async def sync(
        self,
        page_size: int = 1000,
        cursor: Optional[str] = None,
        updated_since: Optional[datetime] = None,
        state_filter: Optional[str] = None,
    ) -> dict[str, Any]:
        log = logger.bind(page_size=page_size, state_filter=state_filter)
        log.info("beacon_sync_request")

        cursor_conf, cursor_id = _decode_cursor(cursor)
        etag = await self._compute_etag(updated_since, state_filter)
        total = await self._count_qualified(updated_since, state_filter)

        rows = await self._query_locations(
            page_size=page_size,
            cursor_conf=cursor_conf,
            cursor_id=cursor_id,
            updated_since=updated_since,
            state_filter=state_filter,
        )

        if not rows:
            return self._build_response([], total, etag, page_size)

        location_ids = [r.id for r in rows]
        org_ids = [r.organization_id for r in rows if r.organization_id]

        phones, schedules, languages, accessibility, sources = (
            await self._batch_lookups(location_ids, org_ids)
        )

        locations: list[BeaconLocation] = []
        for row in rows:
            try:
                loc = self._transform(
                    row, phones, schedules, languages, accessibility, sources
                )
                locations.append(loc)
            except Exception as e:
                logger.error(
                    "beacon_transform_failed",
                    location_id=getattr(row, "id", None),
                    error=str(e),
                )

        log.info("beacon_sync_complete", returned=len(locations), total=total)
        return self._build_response(locations, total, etag, page_size)

    async def _compute_etag(
        self,
        updated_since: Optional[datetime],
        state_filter: Optional[str],
    ) -> str:
        params: dict[str, Any] = {"min_confidence": self._min_confidence}
        clauses = _BASE_WHERE
        if updated_since:
            clauses += " AND l.updated_at > :updated_since"
            params["updated_since"] = updated_since
        if state_filter:
            clauses += " AND a.state_province = :state_filter"
            params["state_filter"] = state_filter

        sql = f"""
            SELECT MAX(l.updated_at), COUNT(*)
            FROM location l
            LEFT JOIN address a ON a.location_id = l.id
                AND a.address_type = 'physical'
            WHERE {clauses}
        """  # nosec B608  # noqa: S608
        result = await self._session.execute(text(sql), params)
        row = result.fetchone()
        raw = f"{row[0]}:{row[1]}" if row else "none:0"
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    async def _count_qualified(
        self,
        updated_since: Optional[datetime],
        state_filter: Optional[str],
    ) -> int:
        params: dict[str, Any] = {"min_confidence": self._min_confidence}
        clauses = _BASE_WHERE
        if updated_since:
            clauses += " AND l.updated_at > :updated_since"
            params["updated_since"] = updated_since
        if state_filter:
            clauses += " AND a.state_province = :state_filter"
            params["state_filter"] = state_filter

        # HSDS schema allows multiple physical addresses per location;
        # after the Tier-3 dedupe backfill several hundred survivors have
        # 2+ rows. A plain LEFT JOIN would fan out and inflate this count
        # — pin to one address row per location via LATERAL + LIMIT 1
        # (lowest UUID, deterministic).
        # LATERAL subquery must select every address column referenced
        # by `_BASE_WHERE` and any optional filter clauses — currently
        # `city` and `state_province`. Missing a column makes its `IS
        # NOT NULL` predicate evaluate against NULL and drops the row.
        sql = f"""
            SELECT COUNT(*) FROM location l
            LEFT JOIN LATERAL (
                SELECT city, state_province
                FROM address
                WHERE location_id = l.id AND address_type = 'physical'
                ORDER BY id
                LIMIT 1
            ) a ON TRUE
            WHERE {clauses}
        """  # nosec B608  # noqa: S608
        result = await self._session.execute(text(sql), params)
        return result.scalar_one()

    async def _query_locations(
        self,
        page_size: int,
        cursor_conf: Optional[int],
        cursor_id: Optional[str],
        updated_since: Optional[datetime],
        state_filter: Optional[str],
    ) -> Sequence[Any]:
        params: dict[str, Any] = {
            "min_confidence": self._min_confidence,
            "page_size": page_size,
        }
        clauses = _BASE_WHERE
        if updated_since:
            clauses += " AND l.updated_at > :updated_since"
            params["updated_since"] = updated_since
        if state_filter:
            clauses += " AND a.state_province = :state_filter"
            params["state_filter"] = state_filter

        cursor_clause = ""
        if cursor_conf is not None and cursor_id is not None:
            cursor_clause = (
                "AND (l.confidence_score, l.id) < (:cursor_conf, :cursor_id)"
            )
            params["cursor_conf"] = cursor_conf
            params["cursor_id"] = cursor_id

        # Address join MUST be one row per location, otherwise the
        # cursor-paginated downstream (`beacon` build) sees duplicate
        # `l.id` values across the page list and `BatchWriteItem` on
        # DynamoDB rejects them. Several hundred survivors have 2+
        # physical addresses after the Tier-3 dedupe backfill. LATERAL
        # + ORDER BY id LIMIT 1 picks the lowest-UUID address
        # deterministically.
        sql = f"""
            SELECT l.id, l.name, l.description, l.latitude, l.longitude,
                   l.transportation, l.url, l.confidence_score,
                   l.validation_status, l.verified_by, l.verified_at,
                   l.updated_at, l.organization_id,
                   o.name as org_name, o.email as org_email,
                   o.website as org_website,
                   a.address_1, a.address_2, a.city,
                   a.state_province, a.postal_code
            FROM location l
            LEFT JOIN organization o ON l.organization_id = o.id
            LEFT JOIN LATERAL (
                SELECT address_1, address_2, city, state_province, postal_code
                FROM address
                WHERE location_id = l.id AND address_type = 'physical'
                ORDER BY id
                LIMIT 1
            ) a ON TRUE
            WHERE {clauses} {cursor_clause}
            ORDER BY l.confidence_score DESC, l.id DESC
            LIMIT :page_size
        """  # nosec B608  # noqa: S608
        result = await self._session.execute(text(sql), params)
        return result.fetchall()

    async def _batch_lookups(
        self,
        location_ids: list[str],
        org_ids: list[str],
    ) -> tuple[dict, dict, dict, dict, dict]:
        phones: dict[str, list[Any]] = {}
        schedules: dict[str, list[Any]] = {}
        languages: dict[str, list[Any]] = {}
        accessibility: dict[str, Any] = {}
        sources: dict[str, list[str]] = {}

        for name, coro in [
            ("phones", self._q_phones(location_ids)),
            ("schedules", self._q_schedules(location_ids)),
            ("languages", self._q_languages(location_ids)),
            ("accessibility", self._q_accessibility(location_ids)),
            ("sources", self._q_sources(location_ids)),
        ]:
            try:
                result = await coro
                if name == "phones":
                    phones = result
                elif name == "schedules":
                    schedules = result
                elif name == "languages":
                    languages = result
                elif name == "accessibility":
                    accessibility = result
                elif name == "sources":
                    sources = result
            except Exception as e:
                logger.error("beacon_batch_failed", lookup=name, error=str(e))

        return phones, schedules, languages, accessibility, sources

    async def _q_phones(self, ids: list[str]) -> dict[str, list[Any]]:
        r = await self._session.execute(
            text(
                "SELECT location_id, number, type, extension "
                "FROM phone WHERE location_id = ANY(:ids) ORDER BY type"
            ),
            {"ids": ids},
        )
        out: dict[str, list[Any]] = {}
        for row in r.fetchall():
            out.setdefault(row.location_id, []).append(row)
        return out

    async def _q_schedules(self, ids: list[str]) -> dict[str, list[Any]]:
        r = await self._session.execute(
            text(
                "SELECT location_id, opens_at, closes_at, byday, freq, "
                "description, notes "
                "FROM schedule WHERE location_id = ANY(:ids) "
                "ORDER BY byday, opens_at"
            ),
            {"ids": ids},
        )
        out: dict[str, list[Any]] = {}
        for row in r.fetchall():
            out.setdefault(row.location_id, []).append(row)
        return out

    async def _q_languages(self, ids: list[str]) -> dict[str, list[Any]]:
        r = await self._session.execute(
            text(
                "SELECT location_id, name, code "
                "FROM language WHERE location_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
        out: dict[str, list[Any]] = {}
        for row in r.fetchall():
            out.setdefault(row.location_id, []).append(row)
        return out

    async def _q_accessibility(self, ids: list[str]) -> dict[str, Any]:
        r = await self._session.execute(
            text(
                "SELECT location_id, description, details, url "
                "FROM accessibility WHERE location_id = ANY(:ids) LIMIT 1"
            ),
            {"ids": ids},
        )
        out: dict[str, Any] = {}
        for row in r.fetchall():
            out[row.location_id] = row
        return out

    async def _q_sources(self, ids: list[str]) -> dict[str, list[str]]:
        r = await self._session.execute(
            text(
                "SELECT location_id, scraper_id "
                "FROM location_source WHERE location_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
        out: dict[str, list[str]] = {}
        for row in r.fetchall():
            out.setdefault(row.location_id, []).append(row.scraper_id)
        return out

    def _transform(
        self,
        loc: Any,
        phones: dict,
        schedules: dict,
        languages: dict,
        accessibility: dict,
        sources: dict,
    ) -> BeaconLocation:
        lid = loc.id

        # `phone.extension` is NUMERIC but BeaconPhone.extension is the
        # declared Optional[str]; coerce so a numeric extension doesn't raise
        # in Pydantic and drop the whole location via the except handler.
        phone_list = [
            BeaconPhone(
                number=p.number,
                type=p.type,
                extension=str(p.extension) if p.extension is not None else None,
            )
            for p in phones.get(lid, [])
        ]
        sched_list = [
            BeaconSchedule(
                opens_at=str(s.opens_at) if s.opens_at else None,
                closes_at=str(s.closes_at) if s.closes_at else None,
                byday=s.byday,
                freq=s.freq,
                description=s.description,
                notes=s.notes,
            )
            for s in schedules.get(lid, [])
        ]
        lang_list = [
            BeaconLanguage(name=lang.name, code=lang.code)
            for lang in languages.get(lid, [])
        ]
        acc_row = accessibility.get(lid)
        acc = (
            BeaconAccessibility(
                description=acc_row.description,
                details=acc_row.details,
                url=acc_row.url,
            )
            if acc_row
            else None
        )
        raw_sources = sources.get(lid, [])
        data_sources = [h for s in raw_sources if (h := humanize_scraper_id(s))]

        return BeaconLocation(
            id=lid,
            name=loc.name or "Unknown",
            description=loc.description,
            latitude=float(loc.latitude),
            longitude=float(loc.longitude),
            transportation=loc.transportation,
            website=loc.url,
            confidence_score=loc.confidence_score or 0,
            validation_status=loc.validation_status,
            verified_by=loc.verified_by if hasattr(loc, "verified_by") else None,
            verified_at=(
                str(loc.verified_at)
                if hasattr(loc, "verified_at") and loc.verified_at
                else None
            ),
            organization_id=loc.organization_id,
            organization_name=loc.org_name,
            org_email=loc.org_email,
            org_website=loc.org_website,
            address_1=loc.address_1,
            address_2=loc.address_2,
            city=loc.city,
            state=loc.state_province,
            postal_code=loc.postal_code,
            phones=phone_list,
            schedules=sched_list,
            languages=lang_list,
            accessibility=acc,
            data_sources=data_sources,
            updated_at=loc.updated_at,
        )

    def _build_response(
        self,
        locations: list[BeaconLocation],
        total: int,
        etag: str,
        page_size: int,
    ) -> dict[str, Any]:
        has_more = len(locations) == page_size
        cursor = None
        if has_more and locations:
            last = locations[-1]
            cursor = _encode_cursor(last.confidence_score, last.id)

        return {
            "meta": {
                "total_available": total,
                "returned": len(locations),
                "cursor": cursor,
                "has_more": has_more,
                "generated_at": datetime.now(UTC),
                "etag": etag,
                "data_version": "1.0",
            },
            "locations": locations,
        }


# Guard against pathological audit chains (a survivor soft-deleted into another
# survivor, repeatedly). 25 hops is far beyond any real dedup depth.
_MAX_SURVIVOR_CHAIN_DEPTH = 25


class BeaconRedirectService:
    """Maps dedup-soft-deleted locations to their surviving canonical.

    Beacon deletes a location's S3 pages when dedup soft-deletes it
    (``is_canonical=FALSE``); those previously-indexed URLs then 404. Beacon
    knows the dead URL (from its own DynamoDB build tracker) but not the
    survivor — that lives in ``dedup_run_audit`` + the live ``location`` table,
    which only the API can read. This service returns the survivor side so
    beacon can publish a 301 to the CloudFront redirect KeyValueStore.

    Read-only. Tolerates a missing ``dedup_run_audit`` table (created lazily by
    the dedup scripts) by returning an empty result.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def redirects(
        self,
        page_size: int = 5000,
        cursor: Optional[str] = None,
    ) -> dict[str, Any]:
        log = logger.bind(page_size=page_size)
        log.info("beacon_redirects_request")

        if not await self._audit_table_exists():
            log.info("beacon_redirects_no_audit_table")
            return self._build_response([], page_size)

        chain = await self._load_soft_delete_chain()
        # Resolve each dead id to its terminal (never-soft-deleted) survivor.
        terminal_by_dead: dict[str, str] = {}
        for dead_id in chain:
            terminal = self._resolve_terminal(dead_id, chain)
            if terminal is not None:
                terminal_by_dead[dead_id] = terminal

        survivors = await self._fetch_canonical_survivors(
            set(terminal_by_dead.values())
        )

        # Keep only redirects whose terminal survivor is still a live canonical
        # location. Sorted by dead_id for stable keyset pagination.
        entries = sorted(
            (dead_id, survivors[term])
            for dead_id, term in terminal_by_dead.items()
            if term in survivors
        )
        if cursor:
            entries = [e for e in entries if e[0] > cursor]

        page = entries[:page_size]
        has_more = len(entries) > page_size
        redirects = [
            {"dead_id": dead_id, "survivor": survivor} for dead_id, survivor in page
        ]
        next_cursor = page[-1][0] if (has_more and page) else None

        log.info("beacon_redirects_complete", returned=len(redirects))
        return self._build_response(redirects, page_size, cursor=next_cursor)

    async def _audit_table_exists(self) -> bool:
        result = await self._session.execute(
            text("SELECT to_regclass('public.dedup_run_audit')")
        )
        return result.scalar() is not None

    async def _load_soft_delete_chain(self) -> dict[str, str]:
        """Map each soft-deleted location id -> its recorded survivor id.

        DISTINCT ON keeps the most recent survivor per dead id, in case a row
        was re-deduped across runs.
        """
        result = await self._session.execute(
            text(
                """
                SELECT DISTINCT ON (row_id) row_id, survivor_id
                FROM dedup_run_audit
                WHERE table_name = 'location' AND action = 'soft_delete'
                ORDER BY row_id, created_at DESC
                """
            )
        )
        return {str(r.row_id): str(r.survivor_id) for r in result.fetchall()}

    def _resolve_terminal(self, dead_id: str, chain: dict[str, str]) -> Optional[str]:
        """Follow dead->survivor links until a survivor that was never itself
        soft-deleted. Returns None on a cycle or excessive depth (caller falls
        back to a parent-page redirect / 410)."""
        seen = {dead_id}
        current = chain[dead_id]
        depth = 0
        while current in chain:
            if current in seen or depth >= _MAX_SURVIVOR_CHAIN_DEPTH:
                return None
            seen.add(current)
            current = chain[current]
            depth += 1
        return current

    async def _fetch_canonical_survivors(
        self, ids: set[str]
    ) -> dict[str, dict[str, Any]]:
        """Fetch live address components for survivor ids that are still
        canonical. Non-canonical / missing ids are simply absent from the
        result (their dead URLs fall through to beacon's parent/410 path)."""
        if not ids:
            return {}
        result = await self._session.execute(
            text(
                """
                SELECT l.id, l.name, a.city, a.state_province, a.postal_code
                FROM location l
                LEFT JOIN LATERAL (
                    SELECT city, state_province, postal_code
                    FROM address
                    WHERE location_id = l.id AND address_type = 'physical'
                    ORDER BY id
                    LIMIT 1
                ) a ON TRUE
                WHERE l.id::text = ANY(:ids) AND l.is_canonical = TRUE
                """
            ),
            {"ids": list(ids)},
        )
        out: dict[str, dict[str, Any]] = {}
        for r in result.fetchall():
            out[str(r.id)] = {
                "id": str(r.id),
                "name": r.name,
                "city": r.city,
                "state": r.state_province,
                "postal_code": r.postal_code,
            }
        return out

    def _build_response(
        self,
        redirects: list[dict[str, Any]],
        page_size: int,
        cursor: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "meta": {
                "returned": len(redirects),
                "cursor": cursor,
                "has_more": cursor is not None,
                "generated_at": datetime.now(UTC),
                "data_version": "1.0",
            },
            "redirects": redirects,
        }
