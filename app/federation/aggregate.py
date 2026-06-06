"""HSDS federation §8.2 Location aggregate serializer.

``build_location_aggregate(session, location_id)`` builds the HSDS Location
object that becomes the ``object`` field of a federation activity envelope
(``app/federation/envelope.py::build_preimage(obj=...)``). It is called at the
reconciler commit hook (PR-C) and from the offline dedup scripts — both of which
hold a plain *sync* ``sqlalchemy.orm.Session`` — so this module is sync-only.

HSDS 3.1.1-curated field set (DELIBERATE — Principle II, NON-NEGOTIABLE)
-----------------------------------------------------------------------
The returned dict carries EXACTLY the fields modeled by the unmodified
``app/models/hsds/response.py::LocationResponse`` and validates against it by
construction. That model is HSDS-3.1.1-curated and carries ONLY (including the
``id`` / ``last_modified`` inherited from ``HSDSBaseModel``):

    id, last_modified, name, alternate_name, description, latitude, longitude,
    transportation, external_identifier, external_identifier_type,
    location_type, services (list[ServiceResponse]), sources (list[SourceInfo]),
    source_count, schedules (list[ScheduleInfo]).

It has **NO** top-level ``phones`` / ``addresses`` / ``languages`` /
``accessibility`` fields. Design §8.2 sketches a fuller "embed
phones/addresses/languages/accessibility" object — that assumes the HSDS **3.2**
model, which Task -1 (owner-confirmed) DEFERRED. The 3.1.1 pin binds here. We do
NOT emit those top-level fields: ``HSDSBaseModel`` is configured ``extra="forbid"``,
so emitting an unmodeled top-level field would make validation RAISE (not silently
drop). Keeping the object to the curated set preserves round-trip fidelity. This
is a deliberate scope decision, not an omission: when the models advance to 3.2,
this serializer (and its tests) must be revisited to embed the richer sub-objects.

Envelope-only identity fields (``federation_id`` / ``attributedTo`` / ``origin``
/ ``license``) are NEVER placed inside this object — they live at the envelope
top level (design m1). The object is data, not provenance.

Schedules
---------
Schedules are read from the RAW ``schedule`` table by ``location_id`` — NOT the
``location_master`` view, which collapses distinct schedule windows (the historic
``DISTINCT ON`` bug, spike Proof 2). Two distinct rows (e.g. Mon 9-12 and Thu
13-17) MUST survive as two ``ScheduleInfo`` entries.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.hsds.response import (
    LocationResponse,
    ScheduleInfo,
    SourceInfo,
)

logger = structlog.get_logger(__name__)

# Raw location scalar fields that map 1:1 onto LocationResponse.
_LOCATION_SQL = text(
    """
    SELECT
        id,
        name,
        alternate_name,
        description,
        latitude,
        longitude,
        transportation,
        external_identifier,
        external_identifier_type,
        location_type
    FROM location
    WHERE id = :location_id
    """
)

# Per-scraper source rows -> SourceInfo. Phone/email/website/address are
# enrichment satellites (SourceInfo models them). They are location-level (not
# per-scraper) so they MUST be pulled via scalar correlated subqueries: a plain
# LEFT JOIN to `address`/`phone` cartesian-multiplies the source rows (a location
# with 2 addresses + 2 phones would emit 4 SourceInfo per scraper) and inflate
# the SIGNED source_count. One deterministic representative satellite per
# location (ORDER BY id), NULLIF-wrapped so an all-absent address is NULL (and
# omitted by exclude_none), never an empty string in the signed bytes.
_SOURCES_SQL = text(
    """
    SELECT
        ls.scraper_id,
        ls.name,
        ls.created_at AS first_seen,
        ls.updated_at AS last_updated,
        (
            SELECT p.number FROM phone p
            WHERE p.location_id = ls.location_id
            ORDER BY p.id LIMIT 1
        ) AS phone,
        o.website AS website,
        o.email AS email,
        (
            SELECT NULLIF(CONCAT_WS(', ',
                NULLIF(a.address_1, ''),
                NULLIF(a.city, ''),
                NULLIF(a.state_province, ''),
                NULLIF(a.postal_code, '')
            ), '')
            FROM address a
            WHERE a.location_id = ls.location_id
            ORDER BY a.id LIMIT 1
        ) AS address,
        l.confidence_score
    FROM location_source ls
    LEFT JOIN location l ON l.id = ls.location_id
    LEFT JOIN organization o ON o.id = l.organization_id
    WHERE ls.location_id = :location_id
    ORDER BY ls.scraper_id
    """
)

# Schedules from the RAW schedule table by location_id ONLY (never the view, and
# never the service-attached union — the aggregate is the location's own object).
# One row per distinct schedule window; distinct windows must NOT collapse.
_SCHEDULES_SQL = text(
    """
    SELECT
        opens_at,
        closes_at,
        byday,
        bymonthday,
        freq,
        description,
        valid_from,
        valid_to,
        notes
    FROM schedule
    WHERE location_id = :location_id
    ORDER BY id
    """
)


def _build_sources(session: Session, location_id: str) -> list[SourceInfo]:
    """Assemble per-scraper ``SourceInfo`` rows for a location."""
    rows = session.execute(_SOURCES_SQL, {"location_id": location_id}).fetchall()
    sources: list[SourceInfo] = []
    for row in rows:
        sources.append(
            SourceInfo(
                scraper=row.scraper_id,
                name=row.name,
                phone=row.phone,
                email=row.email,
                website=row.website,
                address=row.address,
                confidence_score=row.confidence_score or 50,
                first_seen=row.first_seen.isoformat() if row.first_seen else None,
                last_updated=(
                    row.last_updated.isoformat() if row.last_updated else None
                ),
            )
        )
    return sources


def _build_schedules(session: Session, location_id: str) -> list[ScheduleInfo]:
    """Assemble distinct ``ScheduleInfo`` windows from the raw schedule table.

    Fail-soft per row: ``ScheduleInfo``'s byday/bymonthday validators RAISE on a
    value the RFC 5545 normalizer cannot parse. A single corrupt row (written by
    a path that bypassed normalization) must not abort the whole aggregate — skip
    it and log, mirroring the HSDS read path and the reconciler/submarine
    fail-soft posture (Principle XI).
    """
    rows = session.execute(_SCHEDULES_SQL, {"location_id": location_id}).fetchall()
    schedules: list[ScheduleInfo] = []
    for row in rows:
        try:
            schedules.append(
                ScheduleInfo(
                    opens_at=str(row.opens_at) if row.opens_at else None,
                    closes_at=str(row.closes_at) if row.closes_at else None,
                    byday=row.byday,
                    bymonthday=row.bymonthday,
                    freq=row.freq,
                    description=row.description,
                    valid_from=row.valid_from.isoformat() if row.valid_from else None,
                    valid_to=row.valid_to.isoformat() if row.valid_to else None,
                    notes=row.notes,
                )
            )
        except (ValidationError, ValueError, TypeError) as exc:
            logger.warning(
                "federation_aggregate_schedule_dropped_invalid",
                location_id=location_id,
                byday=row.byday,
                bymonthday=row.bymonthday,
                freq=row.freq,
                error=str(exc),
            )
            continue
    return schedules


def build_location_aggregate(session: Session, location_id: str) -> dict[str, Any]:
    """Build the HSDS Location object for a federation activity envelope.

    Returns a JSON-ready dict that validates against the unmodified HSDS 3.1.1
    ``LocationResponse`` by construction (see module docstring for the curated
    field-set rationale). Conformance is guaranteed by assembling a
    ``LocationResponse`` and dumping it (``model_dump(mode="json")``), so callers
    get the same shape the read API serves.

    Args:
        session: a *sync* SQLAlchemy ``Session`` (reconciler / dedup scripts).
        location_id: the canonical location id.

    Returns:
        The HSDS Location dict (the ``object`` for ``build_preimage(obj=...)``).

    Raises:
        ValueError: if no location row exists for ``location_id`` — the
            documented contract. Callers (reconciler commit hook, dedup scripts)
            always pass an id they just wrote, so a miss is a real error, not an
            expected empty result.
    """
    row = session.execute(_LOCATION_SQL, {"location_id": location_id}).fetchone()
    if row is None:
        raise ValueError(f"location not found: {location_id!r}")

    sources = _build_sources(session, location_id)
    schedules = _build_schedules(session, location_id)
    # source_count = number of DISTINCT scrapers (matches the read/export paths),
    # not len(sources): never inflated by satellite rows. Falls back to the model
    # default (1) when there are no sources — the read API's "at least itself".
    source_count = len({s.scraper for s in sources}) or 1

    try:
        location = LocationResponse(
            id=row.id,
            name=row.name,
            alternate_name=row.alternate_name,
            description=row.description,
            latitude=float(row.latitude) if row.latitude is not None else None,
            longitude=float(row.longitude) if row.longitude is not None else None,
            transportation=row.transportation,
            external_identifier=row.external_identifier,
            external_identifier_type=row.external_identifier_type,
            location_type=row.location_type,
            sources=sources,
            source_count=source_count,
            schedules=schedules,
        )
    except ValidationError as exc:
        # Surface the documented ValueError contract instead of leaking a raw
        # pydantic ValidationError. The most common trigger is a non-UUID-shaped
        # location id (the `location.id` column is TEXT, the HSDS model requires a
        # UUID) — a real data-integrity problem the caller must handle, not an
        # expected empty result.
        raise ValueError(
            f"location {location_id!r} failed HSDS conformance: {exc}"
        ) from exc
    # Dump as JSON-mode so the result is envelope-ready (str timestamps, floats);
    # exclude_none keeps the object tight and drops the HTTP-response-only fields
    # left unset here (``distance`` = radius-search artifact, ``metadata`` =
    # pagination). NOTE: ``services`` is intentionally NOT assembled in this v1
    # aggregate — the federation unit is the Location + its own schedules +
    # sources (design §9: "Unit = the Location aggregate; schedules are embedded
    # read-only aggregate data"; standalone Organization/Service federation is
    # deferred). Embedding services-at-location is a documented follow-up, not a
    # silent omission.
    return location.model_dump(mode="json", exclude_none=True)
