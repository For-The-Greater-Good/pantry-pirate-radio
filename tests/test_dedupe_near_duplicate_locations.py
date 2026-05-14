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
from typing import Any, Generator

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


# ---------------------------------------------------------------------------
# Review-driven gap tests. These cover blast-radius behaviors that the
# original 20 tests left unexercised:
#   * UNIQUE-conflict DELETE path (only irreversible action)
#   * Savepoint cluster isolation across multiple clusters
#   * Transitive 3-row cluster collapse via union-find
#   * Dry-run write safety
#   * Idempotence (second run = no-op)
#   * Distance boundary at ~_DEDUP_LOOSE_DEG
#   * Multi-address Cartesian guard (SELECT DISTINCT)
#   * Audit-table population on --apply
#   * `diagnostic_count` behavior
# ---------------------------------------------------------------------------


def _ensure_audit_table(db: Session) -> None:
    """Test helper — create the audit table for tests that need it."""
    dedupe_near.ensure_audit_table(db)
    db.commit()


class TestUniqueConflictDelete:
    """The UNIQUE-conflict DELETE path is the only irreversible code
    path in the script. These tests lock its behavior."""

    def test_same_scraper_id_on_both_sides_deletes_duplicates_row(
        self, clean_dedup_tables: Session
    ) -> None:
        # Both rows have a location_source from the same scraper_id.
        # After merge, the survivor's row stays; the duplicate's row
        # must be DELETEd (not repointed) because of the UNIQUE
        # constraint on (location_id, scraper_id).
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Same Scraper Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 X St",
            postal_code="08000",
            confidence=85,
            scraper_id="shared_scraper",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Same Scraper Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 X St",
            postal_code="08000",
            confidence=70,
            scraper_id="shared_scraper",  # same as a
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        result = dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        survivor = result["canonical_id"]
        # Survivor still has its location_source row; duplicate's was
        # deleted (not repointed) because of the UNIQUE conflict.
        cnt = clean_dedup_tables.execute(
            text(
                "SELECT COUNT(*) FROM location_source "
                "WHERE location_id = :id AND scraper_id = 'shared_scraper'"
            ),
            {"id": survivor},
        ).scalar()
        assert cnt == 1  # exactly one row, NOT two

    def test_unique_conflict_delete_logs_full_row_payload(
        self, clean_dedup_tables: Session
    ) -> None:
        # The killer test: when a row is destroyed, the full payload
        # must be in the audit log so an operator can identify what
        # to restore from PITR.
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Audit Test Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Audit St",
            postal_code="08000",
            scraper_id="conflict_scraper",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Audit Test Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 Audit St",
            postal_code="08000",
            scraper_id="conflict_scraper",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        # Find the delete audit row.
        delete_rows = clean_dedup_tables.execute(
            text(
                "SELECT old_value FROM dedup_run_audit "
                "WHERE run_id = :rid AND action = 'delete'"
            ),
            {"rid": run_id},
        ).fetchall()
        assert len(delete_rows) >= 1
        payload = delete_rows[0][0]
        # The payload is the full row — name and scraper_id must be in it.
        assert payload["name"] == "Audit Test Pantry"
        assert payload["scraper_id"] == "conflict_scraper"


class TestSavepointIsolation:
    """The headline resilience claim — one failing cluster doesn't roll
    back successful ones — has to be tested, not just docstring'd."""

    def test_failing_cluster_does_not_undo_prior_success(
        self, clean_dedup_tables: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _ensure_audit_table(clean_dedup_tables)
        # Seed two independent clusters: A (mergeable) and B (also
        # mergeable). Then monkeypatch `soft_delete_duplicate` to raise
        # an IntegrityError on cluster B's first call.
        a1, a2 = str(uuid.uuid4()), str(uuid.uuid4())
        b1, b2 = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a1,
            name="Alpha Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Alpha St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=a2,
            name="Alpha Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 Alpha St",
            postal_code="08000",
            scraper_id="other_alpha",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b1,
            name="Bravo Pantry",
            lat=41.0,
            lng=-75.0,
            address_1="1 Bravo St",
            postal_code="09000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b2,
            name="Bravo Pantry",
            lat=41.0008,
            lng=-75.0,
            address_1="1 Bravo St",
            postal_code="09000",
            scraper_id="other_bravo",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        assert len(clusters) == 2

        # Process cluster A normally, then poison cluster B.
        run_id = str(uuid.uuid4())
        first = clusters[0]
        second = clusters[1]
        sp1 = clean_dedup_tables.begin_nested()
        dedupe_near.merge_cluster(clean_dedup_tables, first, apply=True, run_id=run_id)
        sp1.commit()

        original_soft = dedupe_near.soft_delete_duplicate

        def boom(*args: Any, **kwargs: Any) -> int:
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("synthetic", {}, Exception("test poison"))

        monkeypatch.setattr(dedupe_near, "soft_delete_duplicate", boom)
        sp2 = clean_dedup_tables.begin_nested()
        try:
            dedupe_near.merge_cluster(
                clean_dedup_tables, second, apply=True, run_id=run_id
            )
        except Exception:
            sp2.rollback()
        else:
            sp2.commit()

        monkeypatch.setattr(dedupe_near, "soft_delete_duplicate", original_soft)
        clean_dedup_tables.commit()

        # Cluster A: one duplicate soft-deleted (the work survived).
        first_dups = sorted(first)
        soft_deleted = clean_dedup_tables.execute(
            text(
                "SELECT id FROM location WHERE id = ANY(:ids) AND is_canonical = FALSE"
            ),
            {"ids": first_dups},
        ).fetchall()
        assert len(soft_deleted) == 1

        # Cluster B: BOTH rows still canonical (rolled back).
        second_dups = sorted(second)
        still_canonical = clean_dedup_tables.execute(
            text(
                "SELECT id FROM location WHERE id = ANY(:ids) AND is_canonical = TRUE"
            ),
            {"ids": second_dups},
        ).fetchall()
        assert len(still_canonical) == 2


class TestTransitiveCluster:
    """A↔B and B↔C similar, A↛C similar → all three should collapse.
    Tests union-find on the pair list."""

    def test_three_row_chain_collapses_to_one(
        self, clean_dedup_tables: Session
    ) -> None:
        _ensure_audit_table(clean_dedup_tables)
        a, b, c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Chain Pantry East",
            lat=40.0000,
            lng=-74.0000,
            address_1="100 Chain Ave",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Chain Pantry Central",
            lat=40.0008,
            lng=-74.0000,
            address_1="100 Chain Ave",
            postal_code="08000",
            scraper_id="other_chain_b",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=c,
            name="Chain Pantry West",
            lat=40.0016,
            lng=-74.0000,
            address_1="100 Chain Ave",
            postal_code="08000",
            scraper_id="other_chain_c",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        # All three are in one cluster via union-find.
        assert len(clusters) == 1
        assert clusters[0] == {a, b, c}

        run_id = str(uuid.uuid4())
        result = dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        # Two of three are now non-canonical.
        canonicals = clean_dedup_tables.execute(
            text(
                "SELECT id FROM location WHERE id = ANY(:ids) AND is_canonical = TRUE"
            ),
            {"ids": sorted({a, b, c})},
        ).fetchall()
        assert len(canonicals) == 1
        assert str(canonicals[0][0]) == result["canonical_id"]


class TestDryRunSafety:
    """Without --apply, no DB state may change."""

    def test_merge_cluster_dry_run_makes_no_writes(
        self, clean_dedup_tables: Session
    ) -> None:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="DryRun Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 DryRun St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="DryRun Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 DryRun St",
            postal_code="08000",
            scraper_id="other_dryrun",
        )
        before_canonical = clean_dedup_tables.execute(
            text("SELECT id FROM location WHERE is_canonical = TRUE ORDER BY id")
        ).fetchall()
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        dedupe_near.merge_cluster(clean_dedup_tables, clusters[0], apply=False)
        # No commit — but defense-in-depth check that no writes were issued.
        after_canonical = clean_dedup_tables.execute(
            text("SELECT id FROM location WHERE is_canonical = TRUE ORDER BY id")
        ).fetchall()
        assert before_canonical == after_canonical


class TestIdempotence:
    """Re-running --apply against an already-merged DB must be a no-op."""

    def test_second_apply_finds_no_pairs(self, clean_dedup_tables: Session) -> None:
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Idem Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Idem St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Idem Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 Idem St",
            postal_code="08000",
            scraper_id="other_idem",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        # Second pass: detection should now return zero pairs because
        # the duplicate is soft-deleted (`is_canonical = FALSE`).
        pairs_again = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert pairs_again == []


class TestDistanceBoundary:
    """Lock the ~200m loose-tier ceiling against accidental widening
    via a refactor."""

    def test_inside_boundary_merges(self, clean_dedup_tables: Session) -> None:
        # 0.0017 deg lat ≈ 189m — inside the 200m loose ceiling.
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Boundary Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Edge St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Boundary Pantry",
            lat=40.0017,
            lng=-74.0,
            address_1="1 Edge St",
            postal_code="08000",
            scraper_id="other_b",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert len(pairs) == 1, "pair within 200m must be detected"

    def test_outside_boundary_no_merge(self, clean_dedup_tables: Session) -> None:
        # 0.0020 deg lat ≈ 222m — outside the 200m loose ceiling.
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Boundary Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Edge St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Boundary Pantry",
            lat=40.0020,
            lng=-74.0,
            address_1="1 Edge St",
            postal_code="08000",
            scraper_id="other_b",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        assert pairs == [], f"pair past 200m must NOT be detected, got {pairs!r}"


class TestMultiAddressCartesian:
    """Regression guard for the original Cartesian bug. A location with
    multiple physical addresses must not inflate pair counts."""

    def test_multiple_physical_addresses_yield_single_pair(
        self, clean_dedup_tables: Session
    ) -> None:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Multi Address Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Main St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Multi Address Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 Main St",
            postal_code="08000",
            scraper_id="other_multi",
        )
        # Add a SECOND physical address to each — schema permits it.
        clean_dedup_tables.execute(
            text(
                """
                INSERT INTO address (id, location_id, address_1, city,
                    state_province, postal_code, country, address_type)
                VALUES (:id, :loc, '1 Main Street', 'Anywhere', 'XX',
                        '08000', 'US', 'physical')
                """
            ),
            {"id": str(uuid.uuid4()), "loc": a},
        )
        clean_dedup_tables.execute(
            text(
                """
                INSERT INTO address (id, location_id, address_1, city,
                    state_province, postal_code, country, address_type)
                VALUES (:id, :loc, '1 Main Street', 'Anywhere', 'XX',
                        '08000', 'US', 'physical')
                """
            ),
            {"id": str(uuid.uuid4()), "loc": b},
        )
        clean_dedup_tables.commit()
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        # SELECT DISTINCT should collapse the 2×2 address cross to one
        # (id_a, id_b) pair. Without DISTINCT, we'd see 4 here.
        assert (
            len(pairs) == 1
        ), f"multi-address must not inflate pairs, got {len(pairs)}: {pairs!r}"


class TestAuditTablePopulation:
    """C2/M2 — every mutation logs an audit row that the undo script
    can use to reverse the action."""

    def test_repoint_logs_audit_row_per_moved_row(
        self, clean_dedup_tables: Session
    ) -> None:
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Audit Repoint Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 AR St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Audit Repoint Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 AR St",
            postal_code="08000",
            scraper_id="other_ar",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        repoint_rows = clean_dedup_tables.execute(
            text(
                "SELECT table_name, old_value, new_value FROM dedup_run_audit "
                "WHERE run_id = :rid AND action = 'repoint' "
                "ORDER BY table_name"
            ),
            {"rid": run_id},
        ).fetchall()
        # Each child table that had moves should have audit rows; at
        # minimum location_source and address (from _seed_location).
        tables = {r[0] for r in repoint_rows}
        assert "location_source" in tables
        assert "address" in tables
        # old_value / new_value MUST be present and have location_id.
        for tbl, old, new in repoint_rows:
            assert "location_id" in old, f"{tbl} audit row missing old location_id"
            assert "location_id" in new, f"{tbl} audit row missing new location_id"

    def test_soft_delete_logs_audit_row(self, clean_dedup_tables: Session) -> None:
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Audit Soft Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 AS St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Audit Soft Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 AS St",
            postal_code="08000",
            scraper_id="other_as",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        soft_rows = clean_dedup_tables.execute(
            text(
                "SELECT row_id FROM dedup_run_audit "
                "WHERE run_id = :rid AND action = 'soft_delete'"
            ),
            {"rid": run_id},
        ).fetchall()
        # Exactly one duplicate was soft-deleted.
        assert len(soft_rows) == 1


class TestDiagnosticCount:
    """`diagnostic_count` is the operator's first signal — it has to
    work."""

    def test_diagnostic_count_returns_zero_on_empty_db(
        self, clean_dedup_tables: Session
    ) -> None:
        diag = dedupe_near.diagnostic_count(clean_dedup_tables)
        assert diag["pair_count"] == 0
        assert diag["locations_involved_proxy"] == 0

    def test_diagnostic_count_counts_seeded_pair(
        self, clean_dedup_tables: Session
    ) -> None:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Diag Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Diag St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Diag Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 Diag St",
            postal_code="08000",
            scraper_id="other_diag",
        )
        diag = dedupe_near.diagnostic_count(clean_dedup_tables)
        assert diag["pair_count"] == 1
        assert diag["locations_involved_proxy"] >= 1


class TestUndoDedupRun:
    """The undo companion (`scripts/undo_dedup_run.py`) reverses a run
    by reading the audit table. These tests prove undo round-trips."""

    @pytest.fixture
    def undo_mod(self) -> Any:
        import importlib.util as iu
        import sys as _sys
        from pathlib import Path

        path = Path(__file__).parent.parent / "scripts" / "undo_dedup_run.py"
        spec = iu.spec_from_file_location("undo_dedup_run", path)
        assert spec is not None and spec.loader is not None
        mod = iu.module_from_spec(spec)
        _sys.modules["undo_dedup_run"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_undo_reverses_soft_delete(
        self, clean_dedup_tables: Session, undo_mod: Any
    ) -> None:
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Undo Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Undo St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Undo Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 Undo St",
            postal_code="08000",
            scraper_id="other_undo",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        result = dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        duplicate_id = (clusters[0] - {result["canonical_id"]}).pop()

        # Duplicate is now non-canonical.
        row = clean_dedup_tables.execute(
            text("SELECT is_canonical FROM location WHERE id = :id"),
            {"id": duplicate_id},
        ).first()
        assert row[0] is False

        # Run undo with --apply.
        audit_rows = undo_mod.fetch_audit_rows(clean_dedup_tables, run_id)
        soft_deletes = [r for r in audit_rows if r["action"] == "soft_delete"]
        for r in soft_deletes:
            undo_mod.reverse_soft_delete(clean_dedup_tables, r, apply=True)
        clean_dedup_tables.commit()

        # Duplicate is canonical again.
        row = clean_dedup_tables.execute(
            text("SELECT is_canonical FROM location WHERE id = :id"),
            {"id": duplicate_id},
        ).first()
        assert row[0] is True

    def test_undo_reverses_repoint(
        self, clean_dedup_tables: Session, undo_mod: Any
    ) -> None:
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Undo Repoint Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 UR St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Undo Repoint Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 UR St",
            postal_code="08000",
            scraper_id="other_ur",
        )
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        result = dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        duplicate_id = (clusters[0] - {result["canonical_id"]}).pop()

        # location_source from the duplicate is now on the survivor.
        cnt = clean_dedup_tables.execute(
            text("SELECT COUNT(*) FROM location_source WHERE location_id = :id"),
            {"id": duplicate_id},
        ).scalar()
        assert cnt == 0

        # Run undo on the repoint actions.
        audit_rows = undo_mod.fetch_audit_rows(clean_dedup_tables, run_id)
        repoints = [r for r in audit_rows if r["action"] == "repoint"]
        for r in repoints:
            undo_mod.reverse_repoint(clean_dedup_tables, r, apply=True)
        clean_dedup_tables.commit()

        # Duplicate's location_source is back on the duplicate.
        cnt = clean_dedup_tables.execute(
            text("SELECT COUNT(*) FROM location_source WHERE location_id = :id"),
            {"id": duplicate_id},
        ).scalar()
        assert cnt >= 1


class TestSubmarineExclusionInPickCanonical:
    """I4 — a location_source row whose scraper is FANO-allowlist but
    `source_type='submarine'` must NOT count as FANO-qualifying."""

    def test_fano_submarine_source_does_not_outrank_non_fano(
        self, clean_dedup_tables: Session
    ) -> None:
        from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST

        fano_scraper = next(iter(FANO_ALLOWLIST))
        # Row A: only source is FANO but as submarine enrichment.
        # Row B: non-FANO scraper, higher confidence.
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Submarine Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Sub St",
            postal_code="08000",
            confidence=60,
            scraper_id=fano_scraper,
        )
        # Override the source row to be submarine type.
        clean_dedup_tables.execute(
            text(
                "UPDATE location_source SET source_type = 'submarine' "
                "WHERE location_id = :id AND scraper_id = :s"
            ),
            {"id": a, "s": fano_scraper},
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Submarine Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Sub St",
            postal_code="08000",
            confidence=85,
            scraper_id="non_fano_high_conf",
        )
        clean_dedup_tables.commit()
        survivor = dedupe_near.pick_canonical(clean_dedup_tables, cluster={a, b})
        # B wins because A's only FANO source is submarine (excluded
        # from has_qualifying_source) — confidence_score tie-break
        # gives B at 85 vs A at 60.
        assert survivor == b


class TestMultiChildTableRepoint:
    """I6 — repoint coverage was only on location_source. Cover the
    other tables in CHILD_TABLES via a parametrized case."""

    def test_phone_row_repoints_to_survivor(self, clean_dedup_tables: Session) -> None:
        _ensure_audit_table(clean_dedup_tables)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _seed_location(
            clean_dedup_tables,
            loc_id=a,
            name="Phone Pantry",
            lat=40.0,
            lng=-74.0,
            address_1="1 Phone St",
            postal_code="08000",
        )
        _seed_location(
            clean_dedup_tables,
            loc_id=b,
            name="Phone Pantry",
            lat=40.0008,
            lng=-74.0,
            address_1="1 Phone St",
            postal_code="08000",
            scraper_id="other_phone",
        )
        # Add a phone row to the duplicate-to-be.
        phone_id = str(uuid.uuid4())
        clean_dedup_tables.execute(
            text(
                """
                INSERT INTO phone (id, location_id, number, type)
                VALUES (:id, :loc, '555-555-1212', 'voice')
                """
            ),
            {"id": phone_id, "loc": b},
        )
        clean_dedup_tables.commit()
        pairs = dedupe_near.find_duplicate_pairs(clean_dedup_tables)
        clusters = dedupe_near.group_into_clusters(pairs)
        run_id = str(uuid.uuid4())
        result = dedupe_near.merge_cluster(
            clean_dedup_tables, clusters[0], apply=True, run_id=run_id
        )
        clean_dedup_tables.commit()
        survivor = result["canonical_id"]
        # The phone row must now be on the survivor.
        owner = clean_dedup_tables.execute(
            text("SELECT location_id FROM phone WHERE id = :id"),
            {"id": phone_id},
        ).scalar()
        assert str(owner) == survivor
