"""End-to-end integration tests for PTF /locations endpoints.

These tests seed real rows in `location`, `organization`, `address`,
and `feeding_america_zip_coverage`, then call PtfLocationsQuery and the
transformer against the live test DB. This exercises the real SQL
JOIN (including the SUBSTR-on-postal_code → fa.zip path) which the
mocked router/transformer unit tests can't catch.

Note: we drive `PtfLocationsQuery` directly rather than through the
HTTP TestClient. The sync `fastapi.TestClient` runs requests on a
separate event loop from the pytest-asyncio `db_session` fixture, so
mixing them yields the well-known "Future attached to a different
loop" error. Our HTTP-layer behaviour (request shape, status codes,
no-auth posture, dependency wiring) is unit-tested in
`test_ptf_locations_router.py`; here we focus on the real DB path.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery
from app.api.v1.partners.ptf.locations_transformer import (
    FA_CATALOGUE,
    to_detail,
    to_list_item,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """Insert organization, location, address, FA zip rows.

    The location at zip 07102 maps to FA org 58 ("Community Foodbank of
    New Jersey") in the real crosswalk. A second Alaska location at zip
    99701 has no FA mapping and exercises the null branch.
    """
    org_id = str(uuid.uuid4())
    loc_fa_id = str(uuid.uuid4())
    loc_no_fa_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            """
            INSERT INTO organization (id, name, description, email, website)
            VALUES (:id, :name, :desc, :email, :website)
            """
        ),
        {
            "id": org_id,
            "name": "Newark Pantries Inc",
            "desc": "Org for integration test",
            "email": "integration@example.org",
            "website": "https://example.org",
        },
    )

    await db_session.execute(
        text(
            """
            INSERT INTO location (
                id, organization_id, name, description,
                latitude, longitude, location_type,
                validation_status, confidence_score
            )
            VALUES (
                :id, :org_id, :name, :desc,
                :lat, :lng, 'physical',
                'verified', 75
            )
            """
        ),
        {
            "id": loc_fa_id,
            "org_id": org_id,
            "name": "Newark FA-Mapped Pantry",
            "desc": "Has a FA zip match",
            "lat": 40.7357,
            "lng": -74.1723,
        },
    )

    await db_session.execute(
        text(
            """
            INSERT INTO location (
                id, organization_id, name,
                latitude, longitude, location_type,
                validation_status
            )
            VALUES (
                :id, :org_id, :name,
                :lat, :lng, 'physical', NULL
            )
            """
        ),
        {
            "id": loc_no_fa_id,
            "org_id": org_id,
            "name": "Unmapped Far-North Pantry",
            "lat": 64.8378,
            "lng": -147.7164,
        },
    )

    await db_session.execute(
        text(
            """
            INSERT INTO address (
                id, location_id, address_1, city,
                state_province, postal_code, country, address_type
            )
            VALUES (
                :id, :loc_id, :addr1, :city,
                :state, :zip, 'US', 'physical'
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "loc_id": loc_fa_id,
            "addr1": "100 Market St",
            "city": "Newark",
            "state": "NJ",
            "zip": "07102",
        },
    )

    await db_session.execute(
        text(
            """
            INSERT INTO address (
                id, location_id, address_1, city,
                state_province, postal_code, country, address_type
            )
            VALUES (
                :id, :loc_id, :addr1, :city,
                :state, :zip, 'US', 'physical'
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "loc_id": loc_no_fa_id,
            "addr1": "1 Cold St",
            "city": "Fairbanks",
            "state": "AK",
            "zip": "99701",
        },
    )

    # Ensure the FA crosswalk has the row we expect (idempotent — the
    # production load may already cover this zip).
    await db_session.execute(
        text(
            """
            INSERT INTO feeding_america_zip_coverage (zip, fa_org_id, fa_org_name)
            VALUES (:zip, :fa_org_id, :fa_org_name)
            ON CONFLICT (zip, fa_org_id) DO UPDATE
            SET fa_org_name = EXCLUDED.fa_org_name
            """
        ),
        {
            "zip": "07102",
            "fa_org_id": 58,
            "fa_org_name": "Community Foodbank of New Jersey",
        },
    )

    # Seed an allowlist scraper source so the FANO `qualifying_source` CTE
    # treats both seeded locations as qualifying. `vivery_api` is the
    # fa-spine entry in the allowlist (covers ~14k locations in real data).
    # Without this row, the CASE-gate in queries.py suppresses fa_org_id
    # and the FA enrichment tests would fail in a confusing way.
    for loc_id, lat, lng in (
        (loc_fa_id, 40.7357, -74.1723),
        (loc_no_fa_id, 64.8378, -147.7164),
    ):
        await db_session.execute(
            text(
                """
                INSERT INTO location_source (
                    id, location_id, scraper_id, name, latitude, longitude
                )
                VALUES (:id, :loc_id, :scraper_id, :name, :lat, :lng)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "loc_id": loc_id,
                "scraper_id": "vivery_api",
                "name": "Seeded by vivery_api (integration test)",
                "lat": lat,
                "lng": lng,
            },
        )

    await db_session.flush()
    return {
        "org_id": org_id,
        "loc_fa_id": loc_fa_id,
        "loc_no_fa_id": loc_no_fa_id,
    }


class TestListQueryAgainstRealDB:
    @pytest.mark.asyncio
    async def test_returns_seeded_location_with_fa_enrichment(self, db_session, seeded):
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(40.0, -75.0, 41.0, -74.0),  # bbox over Newark only
        )

        match = next((r for r in rows if str(r.id) == seeded["loc_fa_id"]), None)
        assert match is not None, "Seeded location not returned by query"

        # The JOIN populated FA from the real crosswalk row.
        assert match.fa_org_id == 58
        assert "New Jersey" in match.fa_org_name

        # Transformer hands back a complete list-item shape end-to-end.
        item = to_list_item(match)
        assert item.id == seeded["loc_fa_id"]
        assert item.zip_code == 7102
        assert item.state == "NJ"
        assert item.pantry_timezone == "America/New_York"
        assert item.pantry_id < 0
        assert item.has_plentiful_pantry is False
        assert item.feeding_america_food_bank is not None
        assert item.feeding_america_food_bank.id == 58

    @pytest.mark.asyncio
    async def test_returns_null_fa_for_unmapped_zip(self, db_session, seeded):
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(60.0, -150.0, 70.0, -145.0),  # Alaska only
        )

        ak = next(
            (r for r in rows if str(r.id) == seeded["loc_no_fa_id"]),
            None,
        )
        assert ak is not None
        assert ak.fa_org_id is None
        assert ak.fa_org_name is None

        item = to_list_item(ak)
        assert item.feeding_america_food_bank is None

    @pytest.mark.asyncio
    async def test_bbox_excludes_locations_outside(self, db_session, seeded):
        # Box well east of both seeded locations
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(40.0, 0.0, 41.0, 1.0),  # somewhere in Europe
        )
        ids = {str(r.id) for r in rows}
        assert seeded["loc_fa_id"] not in ids
        assert seeded["loc_no_fa_id"] not in ids

    @pytest.mark.asyncio
    async def test_q_text_search_case_insensitive(self, db_session, seeded):
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(limit=200, offset=0, q="fa-mapped")
        ids = {str(r.id) for r in rows}
        assert seeded["loc_fa_id"] in ids

    @pytest.mark.asyncio
    async def test_limit_caps_results(self, db_session, seeded):
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(limit=1, offset=0)
        assert len(rows) <= 1


class TestDetailQueryAgainstRealDB:
    @pytest.mark.asyncio
    async def test_detail_returns_seeded_location_with_fa(self, db_session, seeded):
        query = PtfLocationsQuery(db_session)
        row = await query.get_location(seeded["loc_fa_id"])
        assert row is not None
        assert row.fa_org_id == 58

        detail = to_detail(row, schedules=[])
        assert detail.id == seeded["loc_fa_id"]
        assert detail.zip_code == 7102
        assert "100 Market St" in detail.address
        assert "Newark" in detail.address
        assert detail.feeding_america_food_bank is not None
        assert detail.feeding_america_food_bank.id == 58

    @pytest.mark.asyncio
    async def test_detail_returns_none_for_unknown_uuid(self, db_session, seeded):
        query = PtfLocationsQuery(db_session)
        row = await query.get_location("00000000-0000-0000-0000-000000000000")
        assert row is None

    @pytest.mark.asyncio
    async def test_detail_for_unmapped_location_returns_null_fa(
        self, db_session, seeded
    ):
        query = PtfLocationsQuery(db_session)
        row = await query.get_location(seeded["loc_no_fa_id"])
        assert row is not None
        assert row.fa_org_id is None
        detail = to_detail(row, schedules=[])
        assert detail.feeding_america_food_bank is None


class TestFeedingAmericaJoinSemantics:
    @pytest.mark.asyncio
    async def test_join_uses_substr_first_5_of_postal_code(self, db_session, seeded):
        """The SQL uses SUBSTR(a.postal_code, 1, 5) so a zip+4 in the
        address column still resolves to the FA org."""
        plus4_loc = str(uuid.uuid4())
        await db_session.execute(
            text(
                """
                INSERT INTO location (
                    id, organization_id, name,
                    latitude, longitude, location_type, validation_status
                )
                VALUES (:id, :org_id, :name, :lat, :lng, 'physical', NULL)
                """
            ),
            {
                "id": plus4_loc,
                "org_id": seeded["org_id"],
                "name": "Zip Plus-Four Pantry",
                "lat": 40.7400,
                "lng": -74.1700,
            },
        )
        await db_session.execute(
            text(
                """
                INSERT INTO address (
                    id, location_id, address_1, city,
                    state_province, postal_code, country, address_type
                )
                VALUES (:id, :loc_id, '5 Pine St', 'Newark', 'NJ',
                        :zip, 'US', 'physical')
                """
            ),
            {"id": str(uuid.uuid4()), "loc_id": plus4_loc, "zip": "07102-4567"},
        )
        # Need an allowlist source so the FANO qualifying_source CTE flips
        # has_qualifying_source -> true and the CASE-gate keeps fa_org_id.
        await db_session.execute(
            text(
                """
                INSERT INTO location_source (
                    id, location_id, scraper_id, name, latitude, longitude
                )
                VALUES (:id, :loc_id, 'vivery_api', 'plus4 seed',
                        :lat, :lng)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "loc_id": plus4_loc,
                "lat": 40.7400,
                "lng": -74.1700,
            },
        )
        await db_session.flush()

        query = PtfLocationsQuery(db_session)
        row = await query.get_location(plus4_loc)
        assert row is not None
        # SUBSTR(07102-4567, 1, 5) → '07102' → fa_org_id 58
        assert row.fa_org_id == 58


class TestFaCatalogueLoadedAtModuleImport:
    """Sanity: the snapshot JSON shipped with the code is non-empty."""

    def test_catalogue_has_entries(self):
        assert (
            len(FA_CATALOGUE) > 100
        ), f"FA catalogue should have ~198 entries, got {len(FA_CATALOGUE)}"

    def test_catalogue_entry_has_required_fields(self):
        # Pick any entry — every entry must validate against the FA schema.
        first_id = next(iter(FA_CATALOGUE))
        entry = FA_CATALOGUE[first_id]
        assert "id" in entry
        assert "name" in entry

    def test_known_org_58_present(self):
        """Org 58 backs many NJ zips in the production crosswalk. If this
        ever breaks, regenerate via scripts/build_ptf_fa_catalogue.py."""
        assert 58 in FA_CATALOGUE or "58" in {str(k) for k in FA_CATALOGUE}


class TestContactOrScheduleFilter:
    """A location must have at least one of {phone, email, website, schedule}
    to appear in the PTF feed. Locations with none of those are unreachable
    by the consuming app and should be filtered out by both the list and
    detail queries.
    """

    @pytest_asyncio.fixture
    async def trio(self, db_session: AsyncSession):
        """Seed three locations under a no-contact org:
        - `bare_id`: nothing — should be filtered out
        - `phone_id`: only a phone row
        - `sched_id`: only a schedule row
        Plus the `vivery_api` source on each so the FANO qualifying-source
        CTE still considers them (matches the existing fixture pattern).
        """
        bare_org_id = str(uuid.uuid4())
        bare_id = str(uuid.uuid4())
        phone_id = str(uuid.uuid4())
        sched_id = str(uuid.uuid4())

        # Org with NO email, NO website.
        await db_session.execute(
            text(
                """
                INSERT INTO organization (id, name, description, email, website)
                VALUES (:id, :name, 'no-contact org', NULL, NULL)
                """
            ),
            {"id": bare_org_id, "name": "No-Contact Pantries Inc"},
        )

        # Three locations under the bare org, far from any other test data.
        # Use a distinct bbox region (somewhere in the Atlantic) so they
        # don't get pulled in by other tests' bbox queries.
        for loc_id, name, lat, lng in (
            (bare_id, "Bare Location (filter-out)", 35.0, -60.0),
            (phone_id, "Phone-Only Location", 35.001, -60.001),
            (sched_id, "Schedule-Only Location", 35.002, -60.002),
        ):
            await db_session.execute(
                text(
                    """
                    INSERT INTO location (
                        id, organization_id, name,
                        latitude, longitude, location_type,
                        validation_status, confidence_score
                    )
                    VALUES (:id, :org_id, :name, :lat, :lng,
                            'physical', 'verified', 75)
                    """
                ),
                {
                    "id": loc_id,
                    "org_id": bare_org_id,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                },
            )
            await db_session.execute(
                text(
                    """
                    INSERT INTO location_source (
                        id, location_id, scraper_id, name, latitude, longitude
                    )
                    VALUES (:id, :loc_id, 'vivery_api', :name, :lat, :lng)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "loc_id": loc_id,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                },
            )

        # Phone-only: attach one phone row.
        await db_session.execute(
            text(
                """
                INSERT INTO phone (id, location_id, number, type)
                VALUES (:id, :loc_id, '5551234567', 'voice')
                """
            ),
            {"id": str(uuid.uuid4()), "loc_id": phone_id},
        )

        # Schedule-only: attach one schedule row.
        await db_session.execute(
            text(
                """
                INSERT INTO schedule (id, location_id, opens_at, closes_at, byday, freq)
                VALUES (:id, :loc_id, '09:00', '12:00', 'TU', 'WEEKLY')
                """
            ),
            {"id": str(uuid.uuid4()), "loc_id": sched_id},
        )

        await db_session.flush()
        return {"bare_id": bare_id, "phone_id": phone_id, "sched_id": sched_id}

    @pytest.mark.asyncio
    async def test_list_excludes_location_with_no_contact_or_schedule(
        self, db_session, trio
    ):
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(34.9, -60.5, 35.1, -59.5),  # the three seeded locations only
        )
        ids = {str(r.id) for r in rows}
        assert trio["bare_id"] not in ids, "bare location should be filtered out"
        assert trio["phone_id"] in ids, "phone-only location should pass"
        assert trio["sched_id"] in ids, "schedule-only location should pass"

    @pytest.mark.asyncio
    async def test_detail_404s_for_location_with_no_contact_or_schedule(
        self, db_session, trio
    ):
        query = PtfLocationsQuery(db_session)
        # bare location: filter rejects -> get_location returns None (router 404s)
        assert await query.get_location(trio["bare_id"]) is None
        # phone-only and schedule-only both pass
        assert await query.get_location(trio["phone_id"]) is not None
        assert await query.get_location(trio["sched_id"]) is not None
