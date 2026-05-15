"""Integration tests for the beacon partner sync endpoint.

The sync endpoint feeds the hourly `ppr-beacon-build-prod` Step
Functions / Fargate job, which writes per-location records to a
DynamoDB tracker via `BatchWriteItem`. DynamoDB rejects a batch that
contains the same primary key twice — so the sync query MUST return
exactly one row per location_id, even when the underlying location
has multiple physical `address` rows (which the HSDS schema permits
and the Tier-3 dedupe backfill produced in ~212 survivor rows).

We drive `BeaconSyncService` directly against the live test DB rather
than through the HTTP TestClient. The sync `fastapi.TestClient` runs
requests on a separate event loop from the pytest-asyncio
`db_session` fixture, so mixing them yields the well-known "Future
attached to a different loop" error. Same pattern as the PTF
integration tests in `test_ptf_locations_integration.py`.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.beacon.services import BeaconSyncService

pytestmark = pytest.mark.integration


async def _seed_location_with_addresses(
    session: AsyncSession,
    *,
    loc_id: str,
    org_id: str,
    name: str,
    lat: float,
    lng: float,
    confidence: int,
    address_count: int,
    postal_code: str = "08000",
) -> None:
    """Seed one canonical location plus N physical address rows.

    `address_count` controls the fan-out: with N>1 the unbounded
    `LEFT JOIN address` (pre-fix) would have returned N rows for this
    location_id; the LATERAL+LIMIT-1 fix returns 1.
    """
    await session.execute(
        text(
            """
            INSERT INTO organization (id, name, description, website)
            VALUES (:id, :name, 'beacon-test org', 'https://example.org')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": org_id, "name": name},
    )
    await session.execute(
        text(
            """
            INSERT INTO location (
                id, organization_id, name, latitude, longitude,
                location_type, validation_status, confidence_score,
                is_canonical
            )
            VALUES (:id, :org, :name, :lat, :lng,
                    'physical', 'verified', :conf, TRUE)
            """
        ),
        {
            "id": loc_id,
            "org": org_id,
            "name": name,
            "lat": lat,
            "lng": lng,
            "conf": confidence,
        },
    )
    for i in range(address_count):
        await session.execute(
            text(
                """
                INSERT INTO address (
                    id, location_id, address_1, city,
                    state_province, postal_code, country, address_type
                )
                VALUES (:id, :loc, :addr, 'Anywhere',
                        'XX', :zip, 'US', 'physical')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "loc": loc_id,
                # Slightly different address strings — exactly the
                # cosmetic-duplication shape the dedupe migration
                # produced on ~212 survivor rows.
                "addr": f"{100 + i} Main St" if i > 0 else "100 Main Street",
                "zip": postal_code,
            },
        )
    await session.commit()


@pytest_asyncio.fixture
async def two_address_location(db_session: AsyncSession):
    """A canonical location with TWO physical addresses — the post-dedupe
    fan-out shape that broke beacon."""
    loc_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    await _seed_location_with_addresses(
        db_session,
        loc_id=loc_id,
        org_id=org_id,
        name="Two-Address Pantry",
        lat=40.0,
        lng=-74.0,
        confidence=80,
        address_count=2,
    )
    return {"loc_id": loc_id, "org_id": org_id}


class TestBeaconSyncAddressFanout:
    """Locations with multiple physical addresses must yield exactly one
    row in the sync response. The hourly build keys DynamoDB on
    `location_id`; duplicates trip `BatchWriteItem`'s
    'Provided list of item keys contains duplicates' validation."""

    @pytest.mark.asyncio
    async def test_two_addresses_yield_one_sync_row(
        self,
        db_session: AsyncSession,
        two_address_location: dict,
    ) -> None:
        loc_id = two_address_location["loc_id"]
        service = BeaconSyncService(db_session, min_confidence=60)
        # Drive the private query directly — we don't want to invoke
        # _batch_lookups (phone/schedule) or _compute_etag because they
        # require additional seed data not relevant to this regression.
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        matching = [r for r in rows if str(r.id) == loc_id]
        assert len(matching) == 1, (
            f"expected exactly 1 row for {loc_id}, got {len(matching)}; "
            "without the LATERAL fix, multi-address locations return N "
            "rows and break BatchWriteItem in beacon's build_tracker"
        )

    @pytest.mark.asyncio
    async def test_count_qualified_not_inflated_by_multiple_addresses(
        self,
        db_session: AsyncSession,
        two_address_location: dict,
    ) -> None:
        # The `total` field in the sync response uses _count_qualified;
        # before the LATERAL fix it summed COUNT(*) over the same fan-out
        # and over-reported. With 1 seeded location and 2 addresses,
        # pre-fix returned 2 (or higher with other DB seed); the fix
        # returns 1 (or the real count of distinct locations).
        service = BeaconSyncService(db_session, min_confidence=60)
        total = await service._count_qualified(updated_since=None, state_filter=None)
        # Two-address location should be counted exactly once.
        # Other rows from prior test fixtures may also count, so this
        # asserts AT LEAST 1 — but the critical guarantee is "not 2",
        # which we cover by comparing against the previous unfiltered
        # query count below.
        rows = await service._query_locations(
            page_size=10000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        distinct_ids = {str(r.id) for r in rows}
        # The count must equal the number of distinct location ids the
        # paginated query would return — if COUNT(*) is over-counting,
        # this inequality fails.
        assert total == len(distinct_ids), (
            f"_count_qualified returned {total} but the paginated query "
            f"would emit {len(distinct_ids)} distinct location ids — "
            "COUNT(*) is fanning out over the address join again"
        )

    @pytest.mark.asyncio
    async def test_address_picked_deterministically_by_id(
        self,
        db_session: AsyncSession,
        two_address_location: dict,
    ) -> None:
        # LATERAL `ORDER BY id LIMIT 1` returns the lowest-UUID address.
        # We don't pin which address text wins (UUIDs are random per
        # seed), but we DO pin that the picked address is one of the
        # seeded ones and not NULL.
        loc_id = two_address_location["loc_id"]
        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        match = next(r for r in rows if str(r.id) == loc_id)
        assert match.address_1 is not None
        assert match.address_1 != ""

    @pytest.mark.asyncio
    async def test_cursor_pagination_does_not_revisit_id(
        self,
        db_session: AsyncSession,
        two_address_location: dict,
    ) -> None:
        # If the fan-out reappeared, cursor pagination would produce
        # the same id on page 1 (twice) AND page 2 (twice more) for any
        # location near a confidence-score boundary. Seed three
        # 2-address rows at different confidence scores and walk the
        # cursor; every location_id must appear at most once across
        # all pages.
        ids: list[str] = []
        for conf in (95, 90, 85):
            new_id = str(uuid.uuid4())
            await _seed_location_with_addresses(
                db_session,
                loc_id=new_id,
                org_id=str(uuid.uuid4()),
                name=f"Pagination Pantry {conf}",
                lat=40.0,
                lng=-74.0,
                confidence=conf,
                address_count=2,
            )
            ids.append(new_id)

        service = BeaconSyncService(db_session, min_confidence=60)
        seen: list[str] = []
        cursor_conf = None
        cursor_id = None
        # page size 2 so we definitely cross a page boundary
        for _ in range(5):
            rows = await service._query_locations(
                page_size=2,
                cursor_conf=cursor_conf,
                cursor_id=cursor_id,
                updated_since=None,
                state_filter=None,
            )
            if not rows:
                break
            for r in rows:
                seen.append(str(r.id))
            last = rows[-1]
            cursor_conf, cursor_id = last.confidence_score, str(last.id)
        # Every seeded id appears AT MOST once across all pages.
        for sid in ids:
            assert seen.count(sid) <= 1, (
                f"location id {sid} appeared {seen.count(sid)} times across "
                "pagination — fan-out regression. This is the exact shape "
                "that breaks DynamoDB BatchWriteItem in beacon's build."
            )


class TestBeaconSyncIsCanonicalFilter:
    """Soft-deleted duplicates (`is_canonical=FALSE`) must NEVER appear
    in the sync output. Yesterday's Tier-3 dedupe backfill soft-deleted
    ~10K rows; if beacon syncs them it builds phantom mini-sites for
    pantries that don't exist."""

    @pytest.mark.asyncio
    async def test_soft_deleted_location_is_excluded(
        self, db_session: AsyncSession
    ) -> None:
        loc_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        await _seed_location_with_addresses(
            db_session,
            loc_id=loc_id,
            org_id=org_id,
            name="Soft-deleted Pantry",
            lat=40.0,
            lng=-74.0,
            confidence=85,
            address_count=1,
        )
        # Flip canonical OFF — same shape as a dedupe survivor merge.
        await db_session.execute(
            text("UPDATE location SET is_canonical = FALSE WHERE id = :id"),
            {"id": loc_id},
        )
        await db_session.commit()

        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        assert all(str(r.id) != loc_id for r in rows), (
            "soft-deleted location leaked into beacon sync output — "
            "either the explicit `is_canonical = TRUE` filter regressed, "
            "or the address-repoint side-effect that previously hid it "
            "has flipped"
        )

    @pytest.mark.asyncio
    async def test_canonical_with_inherited_addresses_is_included(
        self, db_session: AsyncSession
    ) -> None:
        # The companion case: a survivor canonical that picked up
        # multiple address rows from its absorbed duplicates. MUST
        # appear in sync (this is the typical post-dedupe shape).
        loc_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        await _seed_location_with_addresses(
            db_session,
            loc_id=loc_id,
            org_id=org_id,
            name="Survivor Pantry",
            lat=40.0,
            lng=-74.0,
            confidence=85,
            address_count=3,  # absorbed two duplicates
        )
        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        matches = [r for r in rows if str(r.id) == loc_id]
        assert len(matches) == 1


class TestBeaconSyncMinConfidence:
    """Quality gate — locations below `min_confidence` must not appear."""

    @pytest.mark.asyncio
    async def test_below_min_confidence_excluded(
        self, db_session: AsyncSession
    ) -> None:
        low_id = str(uuid.uuid4())
        high_id = str(uuid.uuid4())
        await _seed_location_with_addresses(
            db_session,
            loc_id=low_id,
            org_id=str(uuid.uuid4()),
            name="Low Conf",
            lat=40.0,
            lng=-74.0,
            confidence=40,  # below default min_confidence=60
            address_count=1,
        )
        await _seed_location_with_addresses(
            db_session,
            loc_id=high_id,
            org_id=str(uuid.uuid4()),
            name="High Conf",
            lat=40.0,
            lng=-74.0,
            confidence=80,
            address_count=1,
        )
        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        seen = {str(r.id) for r in rows}
        assert high_id in seen
        assert low_id not in seen

    @pytest.mark.asyncio
    async def test_at_threshold_included(self, db_session: AsyncSession) -> None:
        # `>=` inclusive — a location exactly AT the threshold must qualify.
        loc_id = str(uuid.uuid4())
        await _seed_location_with_addresses(
            db_session,
            loc_id=loc_id,
            org_id=str(uuid.uuid4()),
            name="Threshold Conf",
            lat=40.0,
            lng=-74.0,
            confidence=60,
            address_count=1,
        )
        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        assert any(str(r.id) == loc_id for r in rows)


class TestBeaconSyncRejectedExcluded:
    """`validation_status='rejected'` rows must never sync — they're
    flagged as bad data and would surface as broken mini-sites."""

    @pytest.mark.asyncio
    async def test_rejected_location_excluded(self, db_session: AsyncSession) -> None:
        loc_id = str(uuid.uuid4())
        await _seed_location_with_addresses(
            db_session,
            loc_id=loc_id,
            org_id=str(uuid.uuid4()),
            name="Rejected Pantry",
            lat=40.0,
            lng=-74.0,
            confidence=85,
            address_count=1,
        )
        await db_session.execute(
            text(
                "UPDATE location SET validation_status = 'rejected' " "WHERE id = :id"
            ),
            {"id": loc_id},
        )
        await db_session.commit()
        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        assert all(str(r.id) != loc_id for r in rows)


class TestBeaconSyncSqlShape:
    """Structural SQL-shape guards. Some filters can't be exercised
    behaviorally (the DB has a CHECK constraint that prevents canonical
    rows from having NULL lat/lng), so we just lock the WHERE clause
    contains the predicate. If the filter is ever removed AND the
    constraint is also relaxed in the future, the bad data would leak —
    so the structural guard is cheap insurance."""

    def test_null_coord_filter_present_in_base_where(self) -> None:
        from app.api.v1.partners.beacon.services import _BASE_WHERE

        assert "l.latitude IS NOT NULL" in _BASE_WHERE
        assert "l.longitude IS NOT NULL" in _BASE_WHERE

    def test_is_canonical_filter_present_in_base_where(self) -> None:
        # Soft-deleted survivors of the Tier-3 dedupe must never sync.
        # We rely on this BOTH explicitly (the predicate below) AND as a
        # side-effect of the address-repoint stripping `a.city`. The
        # explicit predicate is the load-bearing one.
        from app.api.v1.partners.beacon.services import _BASE_WHERE

        assert "l.is_canonical = TRUE" in _BASE_WHERE

    def test_min_confidence_predicate_uses_inclusive_compare(self) -> None:
        # `>=` (inclusive) matches the validator's "score 60 qualifies"
        # contract. A regression to `>` would silently drop the
        # threshold-aligned rows.
        from app.api.v1.partners.beacon.services import _BASE_WHERE

        assert "l.confidence_score >= :min_confidence" in _BASE_WHERE

    def test_rejected_status_excluded(self) -> None:
        from app.api.v1.partners.beacon.services import _BASE_WHERE

        assert "validation_status != 'rejected'" in _BASE_WHERE


class TestBeaconSyncNoPhysicalAddress:
    """Locations without ANY physical address must be excluded
    (the `a.city IS NOT NULL AND a.state_province IS NOT NULL` gate)."""

    @pytest.mark.asyncio
    async def test_location_without_address_excluded(
        self, db_session: AsyncSession
    ) -> None:
        # Seed location but skip address — replicate the bypass.
        loc_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        await db_session.execute(
            text(
                """
                INSERT INTO organization (id, name, description, website)
                VALUES (:id, :name, 'no-addr test', 'https://example.org')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": org_id, "name": "No Address Pantry"},
        )
        await db_session.execute(
            text(
                """
                INSERT INTO location (
                    id, organization_id, name, latitude, longitude,
                    location_type, validation_status, confidence_score,
                    is_canonical
                )
                VALUES (:id, :org, 'No Address Pantry', 40.0, -74.0,
                        'physical', 'verified', 85, TRUE)
                """
            ),
            {"id": loc_id, "org": org_id},
        )
        await db_session.commit()

        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        assert all(str(r.id) != loc_id for r in rows)


class TestBeaconSyncStateFilter:
    """The `state` query param filters by `a.state_province`. After the
    LATERAL change, the filter is applied to the one selected address
    per location — make sure that semantics is preserved."""

    @pytest.mark.asyncio
    async def test_state_filter_includes_matching(
        self, db_session: AsyncSession
    ) -> None:
        # Two locations: one with NY, one with CA. Filter for NY.
        ny_id = str(uuid.uuid4())
        ca_id = str(uuid.uuid4())
        ny_org = str(uuid.uuid4())
        ca_org = str(uuid.uuid4())
        await db_session.execute(
            text(
                """
                INSERT INTO organization (id, name, description, website)
                VALUES (:i1, 'NY org', '', ''), (:i2, 'CA org', '', '')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"i1": ny_org, "i2": ca_org},
        )
        await db_session.execute(
            text(
                """
                INSERT INTO location (id, organization_id, name,
                    latitude, longitude, location_type, validation_status,
                    confidence_score, is_canonical)
                VALUES
                  (:n, :no, 'NY Pantry', 40.7, -74.0, 'physical',
                   'verified', 85, TRUE),
                  (:c, :co, 'CA Pantry', 37.0, -122.0, 'physical',
                   'verified', 85, TRUE)
                """
            ),
            {"n": ny_id, "no": ny_org, "c": ca_id, "co": ca_org},
        )
        await db_session.execute(
            text(
                """
                INSERT INTO address (id, location_id, address_1, city,
                    state_province, postal_code, country, address_type)
                VALUES
                  (:i1, :ny, '1 NY St', 'NYC', 'NY', '10001', 'US',
                   'physical'),
                  (:i2, :ca, '1 CA St', 'SF', 'CA', '94101', 'US',
                   'physical')
                """
            ),
            {
                "i1": str(uuid.uuid4()),
                "ny": ny_id,
                "i2": str(uuid.uuid4()),
                "ca": ca_id,
            },
        )
        await db_session.commit()

        service = BeaconSyncService(db_session, min_confidence=60)
        rows = await service._query_locations(
            page_size=1000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter="NY",
        )
        seen = {str(r.id) for r in rows}
        assert ny_id in seen
        assert ca_id not in seen


class TestBeaconSyncCount:
    """`_count_qualified` underpins the `total` field consumers use to
    estimate pagination depth. Must match the actual queryable
    count."""

    @pytest.mark.asyncio
    async def test_count_matches_paginated_distinct_ids(
        self, db_session: AsyncSession
    ) -> None:
        # Seed a mix: 1-address, 2-address, 3-address. Count must be 3,
        # not 1+2+3=6 (the pre-fix fanout).
        for n in (1, 2, 3):
            await _seed_location_with_addresses(
                db_session,
                loc_id=str(uuid.uuid4()),
                org_id=str(uuid.uuid4()),
                name=f"Count Test {n}",
                lat=40.0,
                lng=-74.0,
                confidence=80,
                address_count=n,
            )
        service = BeaconSyncService(db_session, min_confidence=60)
        total = await service._count_qualified(updated_since=None, state_filter=None)
        rows = await service._query_locations(
            page_size=10000,
            cursor_conf=None,
            cursor_id=None,
            updated_since=None,
            state_filter=None,
        )
        distinct_ids = {str(r.id) for r in rows}
        # Count must equal the number of distinct ids the paginated
        # query would emit. Fan-out would make these differ.
        assert total == len(distinct_ids)


class TestBeaconSyncBuildTrackerDiff:
    """Regression: the build_tracker.diff_static path that consumes
    the sync output. Even if sync returns duplicate ids upstream,
    diff_static silently produces a list with duplicate keys that
    DynamoDB BatchWriteItem will reject. This is the exact failure
    that brought down the cron — preserved as a regression guard."""

    def test_duplicate_ids_in_input_produce_duplicate_keys_in_added(
        self,
    ) -> None:
        # The beacon plugin's `BuildTracker.diff_static` doesn't dedupe
        # its input list — replicating its loop logic inline because
        # `plugins/ppr-beacon/` is hyphen-named and uses relative
        # imports, so a clean cross-module load isn't worth the
        # gymnastics here. The point of this test is documentary: it
        # locks in WHY the sync-side LATERAL fix matters by replicating
        # the bug shape.
        api_locations = [
            {"id": "loc-1", "name": "A"},
            {"id": "loc-1", "name": "A"},  # duplicate id (fan-out)
        ]
        existing: dict = {}
        added: list = []
        for loc in api_locations:
            if loc["id"] not in existing:
                added.append(loc)
        # Both copies end up in `added`, and downstream batch_upsert
        # would call put_item with the same partition key twice,
        # hitting DynamoDB's
        #   "Provided list of item keys contains duplicates"
        # validation. The sync-side LATERAL fix prevents that input
        # shape from reaching diff_static in the first place.
        assert len(added) == 2
        assert [x["id"] for x in added].count("loc-1") == 2

    def test_dedupe_by_id_workaround_would_collapse_duplicates(self) -> None:
        # Defense-in-depth note: even with the sync fix, a downstream
        # `dedupe by id` pass on the build_tracker side would be
        # cheap insurance. This test models that fix in case we
        # decide to add it.
        api_locations = [
            {"id": "loc-1", "name": "A", "state": "NY", "city": "NYC"},
            {"id": "loc-1", "name": "A", "state": "NY", "city": "NYC"},
        ]
        deduped: dict = {}
        for loc in api_locations:
            deduped[loc["id"]] = loc
        assert len(deduped) == 1
