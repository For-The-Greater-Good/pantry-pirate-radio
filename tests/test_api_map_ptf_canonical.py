"""API-2/3 regression guard: map + PTF serve paths hide non-canonical/rejected.

The audit found the map LIST (`get_locations_for_map`), the map detail
(`/map/locations/{id}`), and the PTF list/detail queries did not filter
`is_canonical`, so soft-deleted duplicate pantries (and, for the detail paths,
rejected rows) were served — and the PTF serve-time cluster-dedup could even
pick a non-canonical row as the surviving pin. In production 6,699
non-canonical rows passed every other PTF/map gate.

These tests lock in `is_canonical = TRUE` (plus the rejected filter on the
detail paths) on those four query paths.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.locations_queries import (
    _DETAIL_SQL,
    _LIST_SQL,
    PtfLocationsQuery,
)

pytestmark = pytest.mark.integration


def test_ptf_list_sql_filters_canonical():
    assert "l.is_canonical = TRUE" in _LIST_SQL


def test_ptf_detail_sql_filters_canonical_and_rejected():
    assert "l.is_canonical = TRUE" in _DETAIL_SQL
    assert "validation_status" in _DETAIL_SQL


@pytest_asyncio.fixture
async def visibility_graph(db_session: AsyncSession):
    """Seed one canonical + one non-canonical + one rejected location.

    All three carry an org website (so they clear the PTF contact-info gate)
    and a location_source row (so they clear the map LIST inner join), leaving
    canonicality/validation as the only thing that can hide them.
    """
    org_id = str(uuid.uuid4())
    visible_id = str(uuid.uuid4())
    duplicate_id = str(uuid.uuid4())
    rejected_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            """
            INSERT INTO organization (id, name, description, website)
            VALUES (:id, :name, :desc, :website)
            """
        ),
        {
            "id": org_id,
            "name": "Visibility Test Org",
            "desc": "API-2/3 seed",
            "website": "https://example.org",
        },
    )

    # lat/lng tightly clustered so a single small bbox covers all three.
    seed = [
        (visible_id, "Visible Pantry", "needs_review", True, 38.9000, -77.0000),
        (duplicate_id, "Soft-deleted Dup", "needs_review", False, 38.9001, -77.0001),
        (rejected_id, "Rejected Pantry", "rejected", True, 38.9002, -77.0002),
    ]
    for loc_id, name, status, canonical, lat, lng in seed:
        await db_session.execute(
            text(
                """
                INSERT INTO location (
                    id, organization_id, name, latitude, longitude,
                    location_type, validation_status, confidence_score,
                    is_canonical
                )
                VALUES (
                    :id, :org, :name, :lat, :lng,
                    'physical', :status, 70, :canonical
                )
                """
            ),
            {
                "id": loc_id,
                "org": org_id,
                "name": name,
                "lat": lat,
                "lng": lng,
                "status": status,
                "canonical": canonical,
            },
        )
        # location_source row (non-submarine) so the map LIST inner join keeps it.
        await db_session.execute(
            text(
                """
                INSERT INTO location_source (
                    id, location_id, scraper_id, name, latitude, longitude
                )
                VALUES (:id, :loc, 'no_fa_scraper', :name, :lat, :lng)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "loc": loc_id,
                "name": name,
                "lat": lat,
                "lng": lng,
            },
        )
    await db_session.flush()

    return {
        "visible_id": visible_id,
        "duplicate_id": duplicate_id,
        "rejected_id": rejected_id,
        "bbox": (38.89, -77.01, 38.91, -76.99),
    }


@pytest.mark.asyncio
async def test_ptf_list_excludes_noncanonical_and_rejected(
    db_session, visibility_graph
):
    query = PtfLocationsQuery(db_session)
    rows = await query.list_locations(
        limit=200, offset=0, bbox=visibility_graph["bbox"]
    )
    ids = {str(r.id) for r in rows}
    assert visibility_graph["visible_id"] in ids
    assert visibility_graph["duplicate_id"] not in ids
    assert visibility_graph["rejected_id"] not in ids


@pytest.mark.asyncio
async def test_ptf_detail_404s_for_noncanonical_and_rejected(
    db_session, visibility_graph
):
    query = PtfLocationsQuery(db_session)
    assert await query.get_location(visibility_graph["visible_id"]) is not None
    assert await query.get_location(visibility_graph["duplicate_id"]) is None
    assert await query.get_location(visibility_graph["rejected_id"]) is None


@pytest.mark.asyncio
async def test_map_list_excludes_noncanonical_and_rejected(
    db_session, visibility_graph
):
    from app.api.v1.map.services import MapDataService

    service = MapDataService(db_session)
    locations, _meta = await service.get_locations_for_map(
        bbox=visibility_graph["bbox"]
    )
    ids = {str(loc["id"]) for loc in locations}
    assert visibility_graph["visible_id"] in ids
    assert visibility_graph["duplicate_id"] not in ids
    assert visibility_graph["rejected_id"] not in ids
