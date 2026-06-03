"""Tests for the beacon redirects endpoint (dead-URL -> surviving canonical).

When dedup soft-deletes a duplicate location (is_canonical=FALSE), beacon
deletes that location's S3 pages and the previously-indexed URLs 404. This
endpoint supplies the survivor side (from dedup_run_audit + the live location
table) so beacon can publish a 301 to its CloudFront redirect KeyValueStore.

Driven directly against the live test DB, same pattern as test_beacon_sync.py.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.beacon.services import BeaconRedirectService

# Minimal idempotent DDL — mirrors scripts/dedupe_near_duplicate_locations.py's
# lazily-created audit table so these tests are self-contained.
_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS dedup_run_audit (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    cluster_id TEXT NOT NULL,
    survivor_id UUID NOT NULL,
    duplicate_id UUID,
    table_name TEXT NOT NULL,
    row_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('repoint', 'delete', 'soft_delete')),
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


# --------------------------------------------------------------------------- #
# Pure unit tests for the transitive survivor resolution (no DB).
# --------------------------------------------------------------------------- #
class TestResolveTerminal:
    def _svc(self) -> BeaconRedirectService:
        return BeaconRedirectService(session=None)  # type: ignore[arg-type]

    def test_direct_survivor(self):
        chain = {"a": "b"}
        assert self._svc()._resolve_terminal("a", chain) == "b"

    def test_two_hop_chain_resolves_to_terminal(self):
        # a merged into b, b later merged into c (still canonical) -> c
        chain = {"a": "b", "b": "c"}
        assert self._svc()._resolve_terminal("a", chain) == "c"
        assert self._svc()._resolve_terminal("b", chain) == "c"

    def test_cycle_returns_none(self):
        # a -> b -> a : no terminal; caller falls back to parent/410
        chain = {"a": "b", "b": "a"}
        assert self._svc()._resolve_terminal("a", chain) is None

    def test_self_cycle_returns_none(self):
        chain = {"a": "a"}
        assert self._svc()._resolve_terminal("a", chain) is None

    def test_excessive_depth_returns_none(self):
        # 30-long chain exceeds the 25-hop guard.
        chain = {str(i): str(i + 1) for i in range(30)}
        assert self._svc()._resolve_terminal("0", chain) is None


# --------------------------------------------------------------------------- #
# Integration tests against the live test DB.
# --------------------------------------------------------------------------- #
pytestmark = pytest.mark.integration


async def _seed_location(
    session: AsyncSession,
    *,
    loc_id: str,
    name: str,
    is_canonical: bool,
    city: str = "Springfield",
    state: str = "IL",
    postal_code: str = "62701",
) -> None:
    org_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO organization (id, name, description, website) "
            "VALUES (:id, :name, 'redirect-test', '') ON CONFLICT (id) DO NOTHING"
        ),
        {"id": org_id, "name": name},
    )
    await session.execute(
        text(
            """
            INSERT INTO location (id, organization_id, name, latitude, longitude,
                location_type, validation_status, confidence_score, is_canonical)
            VALUES (:id, :org, :name, 40.0, -74.0, 'physical', 'verified', 90, :canon)
            """
        ),
        {"id": loc_id, "org": org_id, "name": name, "canon": is_canonical},
    )
    await session.execute(
        text(
            """
            INSERT INTO address (id, location_id, address_1, city, state_province,
                postal_code, country, address_type)
            VALUES (:id, :loc, '1 Main St', :city, :state, :zip, 'US', 'physical')
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "loc": loc_id,
            "city": city,
            "state": state,
            "zip": postal_code,
        },
    )


async def _seed_soft_delete(
    session: AsyncSession, *, dead_id: str, survivor_id: str
) -> None:
    await session.execute(text(_AUDIT_DDL))
    await session.execute(
        text(
            """
            INSERT INTO dedup_run_audit (run_id, cluster_id, survivor_id,
                duplicate_id, table_name, row_id, action)
            VALUES (gen_random_uuid(), 'test-cluster', :survivor, :dead_uuid,
                    'location', :dead_text, 'soft_delete')
            """
        ),
        {"survivor": survivor_id, "dead_uuid": dead_id, "dead_text": dead_id},
    )


async def _redirects_for(session: AsyncSession, dead_id: str):
    """Return the redirect entry for dead_id, or None."""
    result = await BeaconRedirectService(session).redirects(page_size=10000)
    return next((r for r in result["redirects"] if r["dead_id"] == dead_id), None)


class TestBeaconRedirects:
    @pytest.mark.asyncio
    async def test_soft_deleted_maps_to_canonical_survivor(
        self, db_session: AsyncSession
    ) -> None:
        survivor_id = str(uuid.uuid4())
        dead_id = str(uuid.uuid4())
        await _seed_location(
            db_session,
            loc_id=survivor_id,
            name="Survivor Pantry",
            is_canonical=True,
            city="Chicago",
            state="IL",
            postal_code="60601",
        )
        await _seed_location(
            db_session, loc_id=dead_id, name="Dead Pantry", is_canonical=False
        )
        await _seed_soft_delete(db_session, dead_id=dead_id, survivor_id=survivor_id)
        await db_session.commit()

        entry = await _redirects_for(db_session, dead_id)
        assert entry is not None
        assert entry["survivor"]["id"] == survivor_id
        assert entry["survivor"]["city"] == "Chicago"
        assert entry["survivor"]["state"] == "IL"
        assert entry["survivor"]["postal_code"] == "60601"

    @pytest.mark.asyncio
    async def test_transitive_chain_resolves_to_terminal(
        self, db_session: AsyncSession
    ) -> None:
        # a -> b -> c, c canonical. a and b both redirect to c.
        a, b, c = (str(uuid.uuid4()) for _ in range(3))
        await _seed_location(db_session, loc_id=c, name="Terminal", is_canonical=True)
        await _seed_location(db_session, loc_id=b, name="Mid", is_canonical=False)
        await _seed_location(db_session, loc_id=a, name="Start", is_canonical=False)
        await _seed_soft_delete(db_session, dead_id=a, survivor_id=b)
        await _seed_soft_delete(db_session, dead_id=b, survivor_id=c)
        await db_session.commit()

        ea = await _redirects_for(db_session, a)
        eb = await _redirects_for(db_session, b)
        assert ea is not None and ea["survivor"]["id"] == c
        assert eb is not None and eb["survivor"]["id"] == c

    @pytest.mark.asyncio
    async def test_non_canonical_survivor_excluded(
        self, db_session: AsyncSession
    ) -> None:
        # Survivor was itself soft-deleted with no onward survivor recorded ->
        # no live canonical terminal -> dead id is omitted (beacon parent/410s it).
        dead_id = str(uuid.uuid4())
        dead_survivor = str(uuid.uuid4())
        await _seed_location(
            db_session, loc_id=dead_survivor, name="Also Dead", is_canonical=False
        )
        await _seed_location(
            db_session, loc_id=dead_id, name="Dead", is_canonical=False
        )
        await _seed_soft_delete(db_session, dead_id=dead_id, survivor_id=dead_survivor)
        await db_session.commit()

        assert await _redirects_for(db_session, dead_id) is None

    @pytest.mark.asyncio
    async def test_returned_matches_meta(self, db_session: AsyncSession) -> None:
        result = await BeaconRedirectService(db_session).redirects(page_size=10000)
        assert result["meta"]["returned"] == len(result["redirects"])
