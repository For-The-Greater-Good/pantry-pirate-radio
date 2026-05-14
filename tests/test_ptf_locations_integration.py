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

    @pytest.mark.asyncio
    async def test_empty_string_contact_fields_dont_count(
        self, db_session: AsyncSession
    ):
        """Some scrapers store '' rather than NULL for absent values. The
        filter must treat empty strings as missing — a location with only
        empty-string email/website and an empty-string phone number must
        be filtered out the same as one with NULLs.
        """
        org_id = str(uuid.uuid4())
        loc_id = str(uuid.uuid4())

        # Org with empty-string email and website.
        await db_session.execute(
            text(
                """
                INSERT INTO organization (id, name, description, email, website)
                VALUES (:id, 'Empty-String Org', 'desc', '', '')
                """
            ),
            {"id": org_id},
        )
        await db_session.execute(
            text(
                """
                INSERT INTO location (
                    id, organization_id, name,
                    latitude, longitude, location_type,
                    validation_status, confidence_score
                )
                VALUES (:id, :org, 'Empty-String Pantry',
                        45.0, -65.0, 'physical', 'verified', 75)
                """
            ),
            {"id": loc_id, "org": org_id},
        )
        # Phone row with an empty number — should also be ignored.
        await db_session.execute(
            text(
                """
                INSERT INTO phone (id, location_id, number, type)
                VALUES (:id, :loc, '', 'voice')
                """
            ),
            {"id": str(uuid.uuid4()), "loc": loc_id},
        )
        await db_session.flush()

        query = PtfLocationsQuery(db_session)
        # Detail must 404 — neither contact info nor schedule.
        assert await query.get_location(loc_id) is None
        # And the list must not include it.
        rows = await query.list_locations(
            limit=200, offset=0, bbox=(44.9, -65.5, 45.1, -64.5)
        )
        assert loc_id not in {str(r.id) for r in rows}


class TestNearDuplicateCollapse:
    """Defense-in-depth: when the reconciler leaves multiple `location`
    rows for the same physical pantry (different scrapers, different
    names, no shared org), the endpoint must collapse them to one row
    via the tiered cluster-dedup so Plentiful's map doesn't show three
    pins on top of each other.

    Scenario mirrors the real Beaverton Adventist Church (SDA) case
    that triggered this work: three slightly-different names at the
    same lat/lng, only one of which has a FANO-allowlisted scraper
    source. The survivor must be the FANO row so the
    `feeding_america_food_bank` enrichment block isn't silently dropped.
    """

    @pytest_asyncio.fixture
    async def beaverton_triple(self, db_session: AsyncSession):
        # Three independent orgs — mirrors the reconciler-can't-merge
        # case where same-name and same-org tier-2 dedup both fail.
        org_ids = [str(uuid.uuid4()) for _ in range(3)]
        loc_ids = [str(uuid.uuid4()) for _ in range(3)]

        for oid, name in zip(
            org_ids,
            (
                "Beaverton Adventist (Org A)",
                "Oregon Food Bank Affiliate (Org B)",
                "Beaverton SDA Org (Org C)",
            ),
            strict=True,
        ):
            await db_session.execute(
                text(
                    """
                    INSERT INTO organization (id, name, description, email, website)
                    VALUES (:id, :name, 'beaverton-triple test org',
                            NULL, 'https://example.org')
                    """
                ),
                {"id": oid, "name": name},
            )

        # Three locations, all within ~30m at 14645 SW Davis Rd.
        # Latitude ~45.4869, longitude ~-122.8331 (real Beaverton coords).
        # 0.0001 deg ≈ 11m, so 0.0002 deg ≈ 22m — well inside the
        # 0.00045-deg (~50m) tight-tier epsilon used by the query.
        seeds = [
            (
                loc_ids[0],
                org_ids[0],
                "Beaverton Adventist Church (SDA)",
                45.4869,
                -122.8331,
                70,
                "no_fa_scraper",  # NOT in FANO allowlist
            ),
            (
                loc_ids[1],
                org_ids[1],
                "Beaverton Adventist Church (SDA)",
                45.4870,
                -122.8332,
                65,
                "vivery_api",  # FANO-allowlisted
            ),
            (
                loc_ids[2],
                org_ids[2],
                "Beaverton Seventh Day Adventist",
                45.4871,
                -122.8330,
                80,  # Highest confidence — but still must lose to FANO row.
                "no_fa_scraper",
            ),
        ]

        for loc_id, org_id, name, lat, lng, conf, scraper in seeds:
            await db_session.execute(
                text(
                    """
                    INSERT INTO location (
                        id, organization_id, name, latitude, longitude,
                        location_type, validation_status, confidence_score
                    )
                    VALUES (:id, :org, :name, :lat, :lng,
                            'physical', 'verified', :conf)
                    """
                ),
                {
                    "id": loc_id,
                    "org": org_id,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                    "conf": conf,
                },
            )
            await db_session.execute(
                text(
                    """
                    INSERT INTO address (
                        id, location_id, address_1, city,
                        state_province, postal_code, country, address_type
                    )
                    VALUES (:id, :loc, :addr, 'Beaverton',
                            'OR', :zip, 'US', 'physical')
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "loc": loc_id,
                    "addr": "14645 SW Davis Rd",
                    # 97007 must NOT exist in feeding_america_zip_coverage
                    # for this scenario so the only FA-block driver is the
                    # qualifying_source CTE — keeps the assertions about
                    # survivor pick clean. The fa_org_id stays NULL on the
                    # row but `has_qualifying_source` still flips per the
                    # CASE-gate.
                    "zip": "97007",
                },
            )
            await db_session.execute(
                text(
                    """
                    INSERT INTO location_source (
                        id, location_id, scraper_id, name, latitude, longitude
                    )
                    VALUES (:id, :loc, :scraper, :name, :lat, :lng)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "loc": loc_id,
                    "scraper": scraper,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                },
            )
            # Each location needs one piece of contact info to pass the
            # "must be reachable" filter. Org website is set above.

        await db_session.flush()
        return {
            "loc_ids": loc_ids,
            "fano_loc_id": loc_ids[1],
            "highest_conf_loc_id": loc_ids[2],
        }

    @pytest.mark.asyncio
    async def test_three_close_rows_collapse_to_one(self, db_session, beaverton_triple):
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(45.48, -122.84, 45.49, -122.82),  # tight on Beaverton seeds
        )
        seeded_ids = set(beaverton_triple["loc_ids"])
        returned = {str(r.id) for r in rows if str(r.id) in seeded_ids}
        assert (
            len(returned) == 1
        ), f"expected exactly one survivor from triple, got {len(returned)}: {returned}"

    @pytest.mark.asyncio
    async def test_survivor_is_fano_qualifying_row(self, db_session, beaverton_triple):
        """Even though the FANO row has the LOWEST confidence_score (65)
        of the three, it must win — Plentiful's only reason to call this
        endpoint is the FA enrichment block, so dropping it in favor of
        a higher-confidence sibling is a regression we never tolerate.
        """
        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(45.48, -122.84, 45.49, -122.82),
        )
        seeded_ids = set(beaverton_triple["loc_ids"])
        survivors = [r for r in rows if str(r.id) in seeded_ids]
        assert len(survivors) == 1
        winner = survivors[0]
        assert str(winner.id) == beaverton_triple["fano_loc_id"], (
            f"survivor should be the FANO-allowlisted row, "
            f"got {winner.id} (expected {beaverton_triple['fano_loc_id']})"
        )
        assert winner.has_qualifying_source is True

    @pytest.mark.asyncio
    async def test_loose_tier_merges_same_name_within_200m(
        self, db_session: AsyncSession
    ):
        """Two rows ~120m apart with the same normalized name must
        merge via the loose tier (50-200m, name-gated). This is the
        primary motivating case — strip-mall / parking-lot pantries
        that the tight 50m tier alone misses."""
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())
        loc_near = str(uuid.uuid4())
        loc_far_ish = str(uuid.uuid4())

        for oid in (org_a, org_b):
            await db_session.execute(
                text(
                    """
                    INSERT INTO organization (id, name, description, website)
                    VALUES (:id, 'Loose Tier Org', 'loose tier test',
                            'https://example.org')
                    """
                ),
                {"id": oid},
            )

        # ~120m apart on the lat axis (0.0011 deg lat ≈ 122m). Same
        # normalized name → loose-tier name gate fires → merged.
        for loc_id, org_id, lat, lng, name in (
            (loc_near, org_a, 42.5000, -71.0000, "Greater Boston Food Pantry"),
            (loc_far_ish, org_b, 42.5011, -71.0000, "Greater Boston Food Pantry"),
        ):
            await db_session.execute(
                text(
                    """
                    INSERT INTO location (
                        id, organization_id, name, latitude, longitude,
                        location_type, validation_status, confidence_score
                    )
                    VALUES (:id, :org, :name, :lat, :lng,
                            'physical', 'verified', 70)
                    """
                ),
                {
                    "id": loc_id,
                    "org": org_id,
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

        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(42.49, -71.01, 42.51, -70.99),
        )
        returned = {str(r.id) for r in rows if str(r.id) in {loc_near, loc_far_ish}}
        assert (
            len(returned) == 1
        ), f"loose-tier name gate must merge ~120m same-name rows, got {returned}"

    @pytest.mark.asyncio
    async def test_loose_tier_merges_same_address_within_200m(
        self, db_session: AsyncSession
    ):
        """~150m apart, different names but identical normalized address
        + ZIP. The address gate (>0.7 similarity, ZIP match) must merge
        them. Realistic case: two scrapers describing the same building
        with different naming conventions ('St. John Pantry' vs 'Saint
        John's Outreach')."""
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())
        loc_a = str(uuid.uuid4())
        loc_b = str(uuid.uuid4())

        for oid in (org_a, org_b):
            await db_session.execute(
                text(
                    """
                    INSERT INTO organization (id, name, description, website)
                    VALUES (:id, 'Addr Tier Org', 'addr tier test',
                            'https://example.org')
                    """
                ),
                {"id": oid},
            )

        # ~145m apart (0.0013 deg lng ≈ 110m at this lat) — well inside
        # the 200m loose tier, well outside the 50m tight tier.
        for loc_id, org_id, lat, lng, name in (
            (loc_a, org_a, 33.7500, -84.3900, "St. John Food Pantry"),
            (loc_b, org_b, 33.7500, -84.3915, "Saint John's Outreach Center"),
        ):
            await db_session.execute(
                text(
                    """
                    INSERT INTO location (
                        id, organization_id, name, latitude, longitude,
                        location_type, validation_status, confidence_score
                    )
                    VALUES (:id, :org, :name, :lat, :lng,
                            'physical', 'verified', 70)
                    """
                ),
                {
                    "id": loc_id,
                    "org": org_id,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                },
            )
            await db_session.execute(
                text(
                    """
                    INSERT INTO address (
                        id, location_id, address_1, city,
                        state_province, postal_code, country, address_type
                    )
                    VALUES (:id, :loc, '215 Peachtree St NE', 'Atlanta',
                            'GA', '30303', 'US', 'physical')
                    """
                ),
                {"id": str(uuid.uuid4()), "loc": loc_id},
            )
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

        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(33.74, -84.40, 33.76, -84.38),
        )
        returned = {str(r.id) for r in rows if str(r.id) in {loc_a, loc_b}}
        assert (
            len(returned) == 1
        ), f"loose-tier address gate must merge same-address rows, got {returned}"

    @pytest.mark.asyncio
    async def test_loose_tier_does_not_merge_distinct_neighbors(
        self, db_session: AsyncSession
    ):
        """Two pantries ~120m apart with genuinely different names AND
        addresses must NOT merge — they're real neighbors on a dense
        block, not duplicates. This is the false-positive guard for the
        widened loose tier."""
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())
        loc_a = str(uuid.uuid4())
        loc_b = str(uuid.uuid4())

        for oid in (org_a, org_b):
            await db_session.execute(
                text(
                    """
                    INSERT INTO organization (id, name, description, website)
                    VALUES (:id, 'Distinct Neighbor Org',
                            'distinct neighbor test',
                            'https://example.org')
                    """
                ),
                {"id": oid},
            )

        for loc_id, org_id, lat, lng, name, addr in (
            (
                loc_a,
                org_a,
                42.0000,
                -75.0000,
                "Riverside Community Kitchen",
                "100 Riverside Ave",
            ),
            (
                loc_b,
                org_b,
                42.0011,
                -75.0000,
                "Hillcrest Methodist Pantry",
                "215 Hill St",
            ),
        ):
            await db_session.execute(
                text(
                    """
                    INSERT INTO location (
                        id, organization_id, name, latitude, longitude,
                        location_type, validation_status, confidence_score
                    )
                    VALUES (:id, :org, :name, :lat, :lng,
                            'physical', 'verified', 70)
                    """
                ),
                {
                    "id": loc_id,
                    "org": org_id,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                },
            )
            await db_session.execute(
                text(
                    """
                    INSERT INTO address (
                        id, location_id, address_1, city,
                        state_province, postal_code, country, address_type
                    )
                    VALUES (:id, :loc, :addr, 'Anywhere',
                            'NY', '13901', 'US', 'physical')
                    """
                ),
                {"id": str(uuid.uuid4()), "loc": loc_id, "addr": addr},
            )
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

        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(41.99, -75.01, 42.01, -74.99),
        )
        returned = {str(r.id) for r in rows if str(r.id) in {loc_a, loc_b}}
        assert returned == {
            loc_a,
            loc_b,
        }, "distinct neighbors must NOT merge under the loose tier gate"

    @pytest.mark.asyncio
    async def test_far_apart_rows_are_not_merged(self, db_session: AsyncSession):
        """Self-loops in `edges_both` guarantee every candidate ends
        up in its own component when no inter-row edges fire. Two rows
        >200m apart must both come back."""
        org_id = str(uuid.uuid4())
        far_a = str(uuid.uuid4())
        far_b = str(uuid.uuid4())

        await db_session.execute(
            text(
                """
                INSERT INTO organization (id, name, description, website)
                VALUES (:id, 'Far Org', 'far-apart test org',
                        'https://example.org')
                """
            ),
            {"id": org_id},
        )
        # ~0.01 deg apart (~1.1km) — well outside the 0.00180 (~200m)
        # loose-tier ceiling, so no dedup edge can form.
        for loc_id, lat, lng, name in (
            (far_a, 38.0, -77.0, "Far Pantry A"),
            (far_b, 38.01, -77.01, "Far Pantry B"),
        ):
            await db_session.execute(
                text(
                    """
                    INSERT INTO location (
                        id, organization_id, name, latitude, longitude,
                        location_type, validation_status, confidence_score
                    )
                    VALUES (:id, :org, :name, :lat, :lng,
                            'physical', 'verified', 75)
                    """
                ),
                {"id": loc_id, "org": org_id, "name": name, "lat": lat, "lng": lng},
            )
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

        query = PtfLocationsQuery(db_session)
        rows = await query.list_locations(
            limit=200,
            offset=0,
            bbox=(37.9, -77.1, 38.1, -76.9),
        )
        ids = {str(r.id) for r in rows}
        assert far_a in ids
        assert far_b in ids
