"""Database queries for the beacon static site generator.

Uses sync psycopg2 (same pattern as ppr-write-api) to query PostgreSQL
via RDS Proxy. All queries filter on the beacon quality gate.
"""

from __future__ import annotations

from typing import Any

import psycopg2
import structlog

from .config import BeaconConfig
from .models import (
    Accessibility,
    CitySummary,
    Language,
    LocationDetail,
    LocationSummary,
    OrgDetail,
    Phone,
    Schedule,
    StateSummary,
)
from .slug import (
    city_slug,
    location_slug,
    org_slug,
    state_full_name,
    state_slug,
)

log = structlog.get_logger()

# Quality gate: only human-verified locations with high confidence
_QUALITY_GATE = (
    "l.verified_by IN ('admin', 'source') AND l.confidence_score >= %s"
)


def get_connection(config: BeaconConfig) -> Any:
    """Create a database connection."""
    return psycopg2.connect(config.dsn)


def get_eligible_locations(conn: Any, config: BeaconConfig) -> list[dict[str, Any]]:
    """Get all location IDs passing the quality gate."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT l.id, l.name, a.city, a.state_province "  # noqa: S608
            f"FROM location l "
            f"LEFT JOIN address a ON a.location_id = l.id "
            f"AND a.address_type = 'physical' "
            f"WHERE {_QUALITY_GATE} "
            f"ORDER BY a.state_province, a.city, l.name",
            (config.min_confidence,),
        )
        return [
            {"id": r[0], "name": r[1], "city": r[2], "state": r[3]}
            for r in cur.fetchall()
        ]


def get_location_detail(
    conn: Any, location_id: str, config: BeaconConfig
) -> LocationDetail | None:
    """Fetch full location with all sub-entities for rendering."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT l.id, l.name, l.description, l.latitude, l.longitude, "
            "l.transportation, l.url, l.confidence_score, l.validation_status, "
            "l.verified_by, l.verified_at, "
            "o.id, o.name, o.email, o.website, "
            "a.address_1, a.address_2, a.city, a.state_province, a.postal_code "
            "FROM location l "
            "LEFT JOIN organization o ON l.organization_id = o.id "
            "LEFT JOIN address a ON a.location_id = l.id "
            "AND a.address_type = 'physical' "
            "WHERE l.id = %s",
            (location_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        # Phone
        cur.execute(
            "SELECT number, type, extension FROM phone "
            "WHERE location_id = %s ORDER BY type",
            (location_id,),
        )
        phones = [Phone(number=r[0], type=r[1], extension=r[2]) for r in cur.fetchall()]

        # Schedule
        cur.execute(
            "SELECT opens_at, closes_at, byday, freq, description, notes "
            "FROM schedule WHERE location_id = %s "
            "ORDER BY byday, opens_at",
            (location_id,),
        )
        schedules = [
            Schedule(
                opens_at=r[0], closes_at=r[1], byday=r[2],
                freq=r[3], description=r[4], notes=r[5],
            )
            for r in cur.fetchall()
        ]

        # Language
        cur.execute(
            "SELECT name, code FROM language WHERE location_id = %s",
            (location_id,),
        )
        languages = [Language(name=r[0], code=r[1]) for r in cur.fetchall()]

        # Accessibility
        cur.execute(
            "SELECT description, details, url FROM accessibility "
            "WHERE location_id = %s LIMIT 1",
            (location_id,),
        )
        acc_row = cur.fetchone()
        accessibility = (
            Accessibility(description=acc_row[0], details=acc_row[1], url=acc_row[2])
            if acc_row
            else None
        )

        state = row[18] or ""
        city = row[17] or ""
        name = row[1] or ""
        slug = location_slug(name, location_id)
        base_url = config.base_url.rstrip("/")

        return LocationDetail(
            id=row[0],
            name=name,
            description=row[2],
            latitude=float(row[3]) if row[3] else None,
            longitude=float(row[4]) if row[4] else None,
            transportation=row[5],
            website=row[6],
            confidence_score=row[7] or 0,
            validation_status=row[8],
            verified_by=row[9],
            verified_at=str(row[10]) if row[10] else None,
            organization_id=row[11],
            organization_name=row[12],
            email=row[13],
            phone=phones[0].number if phones else None,
            address_1=row[15],
            address_2=row[16],
            city=city,
            state=state,
            postal_code=row[19],
            schedules=schedules,
            phones=phones,
            languages=languages,
            accessibility=accessibility,
            slug=slug,
            url=f"{base_url}/{state_slug(state)}/{city_slug(city)}/{slug}",
        )


def get_all_states(conn: Any, config: BeaconConfig) -> list[StateSummary]:
    """Get all states with location counts for the homepage."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT a.state_province, "  # noqa: S608
            f"COUNT(DISTINCT l.id), "
            f"COUNT(DISTINCT a.city) "
            f"FROM location l "
            f"JOIN address a ON a.location_id = l.id "
            f"AND a.address_type = 'physical' "
            f"WHERE {_QUALITY_GATE} "
            f"AND a.state_province IS NOT NULL "
            f"GROUP BY a.state_province "
            f"ORDER BY a.state_province",
            (config.min_confidence,),
        )
        return [
            StateSummary(
                state=r[0],
                state_full=state_full_name(r[0]),
                slug=state_slug(r[0]),
                location_count=r[1],
                city_count=r[2],
            )
            for r in cur.fetchall()
        ]


def get_cities_in_state(
    conn: Any, state: str, config: BeaconConfig
) -> list[CitySummary]:
    """Get all cities in a state with location counts."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT a.city, COUNT(DISTINCT l.id) "  # noqa: S608
            f"FROM location l "
            f"JOIN address a ON a.location_id = l.id "
            f"AND a.address_type = 'physical' "
            f"WHERE {_QUALITY_GATE} "
            f"AND a.state_province = %s "
            f"AND a.city IS NOT NULL "
            f"GROUP BY a.city "
            f"ORDER BY a.city",
            (config.min_confidence, state),
        )
        return [
            CitySummary(
                city=r[0],
                state=state,
                slug=city_slug(r[0]),
                location_count=r[1],
            )
            for r in cur.fetchall()
        ]


def get_locations_in_city(
    conn: Any, state: str, city: str, config: BeaconConfig
) -> list[LocationSummary]:
    """Get all eligible locations in a city."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT l.id, l.name, o.name, "  # noqa: S608
            f"a.address_1, a.city, a.state_province, a.postal_code, "
            f"l.confidence_score, l.verified_by, "
            f"(SELECT number FROM phone WHERE location_id = l.id LIMIT 1) "
            f"FROM location l "
            f"LEFT JOIN organization o ON l.organization_id = o.id "
            f"JOIN address a ON a.location_id = l.id "
            f"AND a.address_type = 'physical' "
            f"WHERE {_QUALITY_GATE} "
            f"AND a.state_province = %s AND a.city = %s "
            f"ORDER BY l.name",
            (config.min_confidence, state, city),
        )
        base_url = config.base_url.rstrip("/")
        results = []
        for r in cur.fetchall():
            s = location_slug(r[1] or "", r[0])
            results.append(
                LocationSummary(
                    id=r[0],
                    name=r[1] or "",
                    organization_name=r[2],
                    address_1=r[3],
                    city=r[4] or "",
                    state=r[5] or "",
                    postal_code=r[6],
                    confidence_score=r[7] or 0,
                    verified_by=r[8],
                    phone=r[9],
                    slug=s,
                    url=f"{base_url}/{state_slug(r[5] or '')}/{city_slug(r[4] or '')}/{s}",
                )
            )
        return results


def get_org_detail(
    conn: Any, org_id: str, config: BeaconConfig
) -> OrgDetail | None:
    """Get organization with all its eligible locations."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, email, website "
            "FROM organization WHERE id = %s",
            (org_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        base_url = config.base_url.rstrip("/")
        slug = org_slug(row[1] or "")
        locations = get_locations_by_org(conn, org_id, config)

        return OrgDetail(
            id=row[0],
            name=row[1] or "",
            description=row[2],
            email=row[3],
            website=row[4],
            slug=slug,
            url=f"{base_url}/org/{slug}",
            locations=locations,
        )


def get_locations_by_org(
    conn: Any, org_id: str, config: BeaconConfig
) -> list[LocationSummary]:
    """Get all eligible locations for an organization."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT l.id, l.name, o.name, "  # noqa: S608
            f"a.address_1, a.city, a.state_province, a.postal_code, "
            f"l.confidence_score, l.verified_by, "
            f"(SELECT number FROM phone WHERE location_id = l.id LIMIT 1) "
            f"FROM location l "
            f"LEFT JOIN organization o ON l.organization_id = o.id "
            f"LEFT JOIN address a ON a.location_id = l.id "
            f"AND a.address_type = 'physical' "
            f"WHERE {_QUALITY_GATE} "
            f"AND l.organization_id = %s "
            f"ORDER BY a.state_province, a.city, l.name",
            (config.min_confidence, org_id),
        )
        base_url = config.base_url.rstrip("/")
        results = []
        for r in cur.fetchall():
            s = location_slug(r[1] or "", r[0])
            results.append(
                LocationSummary(
                    id=r[0],
                    name=r[1] or "",
                    organization_name=r[2],
                    address_1=r[3],
                    city=r[4] or "",
                    state=r[5] or "",
                    postal_code=r[6],
                    confidence_score=r[7] or 0,
                    verified_by=r[8],
                    phone=r[9],
                    slug=s,
                    url=f"{base_url}/{state_slug(r[5] or '')}/{city_slug(r[4] or '')}/{s}",
                )
            )
        return results
