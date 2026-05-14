"""Tests for scripts/dedupe_near_duplicate_locations.py.

Two layers:
  * Module-shape tests (no DB) that lock the detection SQL contract and
    the survivor-pick contract.
  * Real-DB integration tests that seed clusters and assert the script
    behaves as advertised: merges fuzzy near-duplicates, exempts
    human-curated rows, refuses to merge >200m apart, etc.

Mirrors the test set for the reconciler Tier 3 path (`test_dedup.py`
+ Tier 3 cases in `test_location_creator.py`) so the prevent-on-
ingest path and the drain-the-backlog path stay symmetric.
"""

from __future__ import annotations

import uuid
from typing import Generator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

# Top-level tests/conftest.py provides an ASYNC `db_session` fixture
# (used by the PTF integration tests). The script under test is sync —
# pull the sync session fixture explicitly so the seed helper can do
# straight `db.execute(...)` without `await`.
from tests.fixtures.db import db_session_sync as db_session  # noqa: F401

# Module under test. Import side-effect free; the script's main() is
# only invoked from tests that drive a real DB.
import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).parent.parent / "scripts" / "dedupe_near_duplicate_locations.py"
)
_spec = importlib.util.spec_from_file_location(
    "dedupe_near_duplicate_locations", _SCRIPT_PATH
)
assert _spec is not None and _spec.loader is not None
dedupe_near = importlib.util.module_from_spec(_spec)
sys.modules["dedupe_near_duplicate_locations"] = dedupe_near
_spec.loader.exec_module(dedupe_near)


# ---------------------------------------------------------------------------
# Module-shape tests (no DB) — lock the SQL and survivor contracts so a
# refactor can't silently widen or narrow the cleanup.
# ---------------------------------------------------------------------------


class TestDetectionSQL:
    """The detection query is the load-bearing piece of the backfill.
    These tests lock its semantics without hitting a DB."""

    def test_uses_dedup_module_constants(self) -> None:
        # Constants must come from app.reconciler.dedup (the same module
        # the reconciler Tier 3 uses) so the prevent-on-ingest and
        # drain-backlog paths can't drift.
        from app.reconciler import dedup as dedup_mod

        assert (
            dedupe_near._DEDUP_LOOSE_DEG  # type: ignore[attr-defined]
            == dedup_mod._DEDUP_LOOSE_DEG
        )
        assert (
            dedupe_near._NAME_SIM_THRESHOLD  # type: ignore[attr-defined]
            == dedup_mod._NAME_SIM_THRESHOLD
        )
        assert (
            dedupe_near._ADDR_SIM_THRESHOLD  # type: ignore[attr-defined]
            == dedup_mod._ADDR_SIM_THRESHOLD
        )

    def test_detection_sql_uses_similarity(self) -> None:
        sql = dedupe_near.detection_sql()
        assert "similarity(" in sql, "detection must use pg_trgm similarity()"

    def test_detection_sql_uses_st_dwithin(self) -> None:
        sql = dedupe_near.detection_sql()
        assert "ST_DWithin" in sql

    def test_detection_sql_filters_to_canonical_only(self) -> None:
        sql = dedupe_near.detection_sql()
        # Both sides of the pair must be is_canonical=TRUE. Otherwise
        # we'd "rediscover" already-soft-deleted rows and shuffle FK
        # children around for no reason.
        assert sql.count("is_canonical = TRUE") >= 2

    def test_detection_sql_exempts_human_verified_rows(self) -> None:
        sql = dedupe_near.detection_sql()
        # Principle VI: never merge into an admin/source/claimed row.
        assert "'admin'" in sql
        assert "'source'" in sql
        assert "'claimed'" in sql

    def test_detection_sql_address_gate_requires_zip5_agreement(self) -> None:
        sql = dedupe_near.detection_sql()
        # Address-only similarity is too easy to coincidentally match
        # ("100 Main St" exists in every town); ZIP gate is the proximity
        # constraint that keeps the address match honest.
        assert "SUBSTR" in sql.upper()
        # The two SUBSTRs are compared for equality.
        assert "= SUBSTR" in sql or "SUBSTR(addr_a.postal_code, 1, 5) = SUBSTR(" in sql

    def test_detection_sql_strict_pair_ordering(self) -> None:
        # `a.id < b.id` so each undirected pair appears exactly once.
        # Without this we'd union-find over duplicate edges and waste
        # work, and counts in the diagnostic query would double.
        sql = dedupe_near.detection_sql()
        assert "a.id < b.id" in sql

    def test_detection_sql_name_and_addr_gates_are_or_ed(self) -> None:
        # Same invariant as the reconciler Tier 3 — a regression to AND
        # would silently miss many real dupes where one signal is strong
        # and the other is missing.
        sql = dedupe_near.detection_sql()
        first_sim = sql.find("similarity(")
        second_sim = sql.find("similarity(", first_sim + 1)
        assert first_sim != -1 and second_sim != -1
        between = sql[first_sim:second_sim]
        assert " OR " in between


class TestSurvivorPick:
    """`pick_canonical` must mirror the PTF API survivor rule exactly,
    so the API's serve-time view of a cluster and the backfill's pick
    of the same cluster converge on the same row."""

    def test_pick_canonical_orders_by_has_qualifying_source_first(self) -> None:
        # A FANO-allowlist scraper on one of the cluster members must
        # beat all non-FANO members regardless of confidence — so the
        # FANO signal must appear in ORDER BY *before* confidence_score
        # and id.
        sql = dedupe_near.pick_canonical_sql()
        norm = " ".join(sql.split()).lower()
        assert "order by" in norm
        idx_order = norm.find("order by")
        order_clause = norm[idx_order:]
        idx_has_qs = order_clause.find("has_qualifying_source")
        idx_conf = order_clause.find("confidence_score")
        idx_id_asc = order_clause.find("id asc")
        assert idx_has_qs != -1, "ORDER BY must reference has_qualifying_source"
        assert idx_conf != -1, "ORDER BY must reference confidence_score"
        assert idx_id_asc != -1, "ORDER BY must end with id ASC"
        assert idx_has_qs < idx_conf < idx_id_asc, (
            f"ORDER BY priority must be has_qualifying_source < confidence_score "
            f"< id (got positions {idx_has_qs}, {idx_conf}, {idx_id_asc})"
        )

    def test_pick_canonical_uses_confidence_score_nulls_last(self) -> None:
        # NULL confidence must lose to any non-NULL confidence —
        # otherwise an unscored row with id=1 wins over a 95-confidence
        # row with id=2.
        sql = dedupe_near.pick_canonical_sql()
        assert "NULLS LAST" in sql.upper()

    def test_pick_canonical_uses_fano_allowlist(self) -> None:
        # The qualifying-source CTE must filter on the FANO allowlist
        # tuple from the PTF API package — single source of truth.
        sql = dedupe_near.pick_canonical_sql()
        assert "scraper_id IN" in sql

    def test_pick_canonical_excludes_submarine_source_type(self) -> None:
        # Submarine source_type is enrichment, not discovery — its
        # presence on a row must not mark the row as FANO-qualifying.
        sql = dedupe_near.pick_canonical_sql()
        assert "submarine" in sql


# ---------------------------------------------------------------------------
# Real-DB integration tests — seed clusters, run the script's pure
# functions, assert observable behaviour.
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_dedup_tables(
    db_session: Session,  # noqa: F811 — pytest resolves fixture by param name, not via the top-level import alias
) -> Generator[Session, None, None]:
    """Wipe location-related tables before each test so seed clusters
    don't bleed across cases."""
    db_session.execute(text("TRUNCATE TABLE record_version CASCADE"))
    db_session.execute(text("TRUNCATE TABLE location CASCADE"))
    db_session.execute(text("TRUNCATE TABLE organization CASCADE"))
    db_session.commit()
    yield db_session


def _seed_location(
    db: Session,
    *,
    loc_id: str,
    name: str,
    lat: float,
    lng: float,
    address_1: str,
    postal_code: str,
    confidence: int = 70,
    scraper_id: str = "no_fa_scraper",
    verified_by: str | None = None,
    org_id: str | None = None,
) -> None:
    """Sync sibling of the PTF integration helper. Seeds one canonical
    location plus the supporting rows the detection SQL touches:
    organization (FK), address (gate input), location_source (FANO
    qualifying-source CTE input)."""
    if org_id is None:
        org_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO organization (id, name, description, website)
            VALUES (:id, :name, 'dedup-test org', 'https://example.org')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": org_id, "name": name},
    )
    db.execute(
        text(
            """
            INSERT INTO location (
                id, organization_id, name, latitude, longitude,
                location_type, validation_status, confidence_score,
                is_canonical, verified_by
            )
            VALUES (:id, :org, :name, :lat, :lng,
                    'physical', 'verified', :conf, TRUE, :verified_by)
            """
        ),
        {
            "id": loc_id,
            "org": org_id,
            "name": name,
            "lat": lat,
            "lng": lng,
            "conf": confidence,
            "verified_by": verified_by,
        },
    )
    db.execute(
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
            "addr": address_1,
            "zip": postal_code,
        },
    )
    db.execute(
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
            "scraper": scraper_id,
            "name": name,
            "lat": lat,
            "lng": lng,
        },
    )
    db.commit()


class TestDetectionAgainstRealDB:
    """The detection SQL is run against a seeded DB; we assert it
    returns the right pair set."""

    def test_fuzzy_name_match_finds_pair(self, clean_dedup_tables: Session) -> None:
        # Same physical pantry under slightly different names, ~150m
        # apart, no shared org. The reconciler's Tier 2 misses this.
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="First Baptist Food Pantry",
            lat=40.0000,
            lng=-74.0000,
            address_1="100 Main St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="First Baptist Church Food Pantry",
            lat=40.0011,  # ~120m north
            lng=-74.0000,
            address_1="100 Main Street",
            postal_code="08000",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        pair_ids = {(p["id_a"], p["id_b"]) for p in pairs}
        assert (min(a, b), max(a, b)) in pair_ids

    def test_accent_fold_finds_pair(self, clean_dedup_tables: Session) -> None:
        # "San José" vs "San Jose" must fold to identical strings before
        # similarity, otherwise the diacritic blocks the merge.
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="San José Community Pantry",
            lat=37.3382,
            lng=-121.8863,
            address_1="200 Elm St",
            postal_code="95101",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="San Jose Community Pantry",
            lat=37.3385,  # ~30m north
            lng=-121.8863,
            address_1="200 Elm St",
            postal_code="95101",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert len(pairs) >= 1

    def test_distinct_neighbors_not_merged(self, clean_dedup_tables: Session) -> None:
        # Different names AND different addresses within 200m. This is
        # the false-positive guard — two genuinely separate pantries
        # on the same dense block must NOT merge.
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Trinity Lutheran Food Bank",
            lat=40.7580,
            lng=-73.9858,
            address_1="500 8th Avenue",
            postal_code="10018",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Holy Apostles Soup Kitchen",
            lat=40.7585,  # ~50m north
            lng=-73.9858,
            address_1="296 9th Avenue",
            postal_code="10001",  # different ZIP — address gate disqualified
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert pairs == [], f"expected no pairs, got {pairs!r}"

    def test_distance_cap_blocks_merge(self, clean_dedup_tables: Session) -> None:
        # Identical names but ~300m apart — past the loose-tier ceiling.
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Helping Hands Pantry",
            lat=40.0000,
            lng=-74.0000,
            address_1="1 Oak St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Helping Hands Pantry",
            lat=40.0030,  # ~333m north
            lng=-74.0000,
            address_1="50 Oak St",
            postal_code="08000",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert pairs == [], f"expected no pairs at >200m, got {pairs!r}"

    def test_verified_by_admin_is_exempt(self, clean_dedup_tables: Session) -> None:
        # When the candidate survivor is admin-curated, no detection
        # pair must form — the cleanup script can never silently
        # overwrite human work (Principle VI).
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Mercy Pantry",
            lat=40.0000,
            lng=-74.0000,
            address_1="10 Pine St",
            postal_code="08000",
            verified_by="admin",  # human-curated
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Mercy Pantry",
            lat=40.0008,  # ~89m north — would otherwise merge
            lng=-74.0000,
            address_1="10 Pine St",
            postal_code="08000",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert pairs == [], f"verified_by='admin' must exempt; got {pairs!r}"


class TestSurvivorPickAgainstRealDB:
    """`pick_canonical` against a seeded cluster — the survivor must
    match the PTF API's serve-time pick."""

    def test_fano_member_wins_over_higher_confidence_non_fano(
        self, clean_dedup_tables: Session
    ) -> None:
        # The FANO row (lower confidence) must still beat a higher-
        # confidence non-FANO row. Without this, the API would see a
        # different survivor than the backfill produced and the
        # `feeding_america_food_bank` enrichment would silently
        # disappear.
        from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST

        fano_scraper = next(iter(FANO_ALLOWLIST))
        non_fano_winner_by_confidence = str(uuid.uuid4())
        fano_actual_winner = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=non_fano_winner_by_confidence,
            name="Pantry X",
            lat=40.0,
            lng=-74.0,
            address_1="1 X St",
            postal_code="08000",
            confidence=95,
            scraper_id="no_fa_scraper",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=fano_actual_winner,
            name="Pantry X",
            lat=40.0,
            lng=-74.0,
            address_1="1 X St",
            postal_code="08000",
            confidence=70,
            scraper_id=fano_scraper,
        )
        survivor = dedupe_near.pick_canonical(
            clean_dedup_tables,
            cluster={non_fano_winner_by_confidence, fano_actual_winner},
        )
        assert survivor == fano_actual_winner

    def test_higher_confidence_wins_within_same_fano_tier(
        self, clean_dedup_tables: Session
    ) -> None:
        # Both non-FANO; survivor must be the higher-confidence row.
        lo_conf = str(uuid.uuid4())
        hi_conf = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=lo_conf,
            name="Pantry Y",
            lat=40.0,
            lng=-74.0,
            address_1="1 Y St",
            postal_code="08000",
            confidence=60,
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=hi_conf,
            name="Pantry Y",
            lat=40.0,
            lng=-74.0,
            address_1="1 Y St",
            postal_code="08000",
            confidence=85,
        )
        assert (
            dedupe_near.pick_canonical(clean_dedup_tables, cluster={lo_conf, hi_conf})
            == hi_conf
        )


class TestEndToEndMerge:
    """End-to-end: seed cluster, run merge_cluster --apply, observe
    is_canonical flips and child rows repointed."""

    def test_apply_repoints_children_and_soft_deletes_duplicate(
        self, clean_dedup_tables: Session
    ) -> None:
        # Two rows that would merge under Tier 3 fuzzy. After --apply
        # one must remain canonical and the other must have
        # is_canonical=FALSE with all its location_source rows
        # repointed onto the survivor.
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Hope Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="42 Hope Ave",
            postal_code="08000",
            confidence=85,
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Hope Pantry Mission",
            lat=40.0008,
            lng=-74.0,
            address_1="42 Hope Avenue",
            postal_code="08000",
            confidence=70,
            scraper_id="other_scraper",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert len(pairs) == 1
        clusters = dedupe_near.group_into_clusters(pairs)
        assert len(clusters) == 1
        result = dedupe_near.merge_cluster(clean_dedup_tables, clusters[0], apply=True)
        clean_dedup_tables.commit()
        survivor_id = result["canonical_id"]
        duplicate_id = (clusters[0] - {survivor_id}).pop()

        # Survivor still canonical
        row = clean_dedup_tables.execute(
            text("SELECT is_canonical FROM location WHERE id = :id"),
            {"id": survivor_id},
        ).first()
        assert row is not None
        assert row[0] is True

        # Duplicate is soft-deleted
        row = clean_dedup_tables.execute(
            text("SELECT is_canonical FROM location WHERE id = :id"),
            {"id": duplicate_id},
        ).first()
        assert row is not None
        assert row[0] is False

        # Duplicate's location_source rows now point to the survivor
        cnt = clean_dedup_tables.execute(
            text("SELECT COUNT(*) FROM location_source WHERE location_id = :id"),
            {"id": duplicate_id},
        ).scalar()
        assert cnt == 0
        cnt = clean_dedup_tables.execute(
            text("SELECT COUNT(*) FROM location_source WHERE location_id = :id"),
            {"id": survivor_id},
        ).scalar()
        assert cnt == 2  # both scrapers' rows now on the survivor
