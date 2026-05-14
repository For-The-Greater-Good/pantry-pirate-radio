"""One-shot backfill: merge fuzzy near-duplicate locations using the
same Tier 3 SQL that the reconciler now runs at ingest time.

Counterpart to `scripts/dedupe_same_org_locations.py` and to the
reconciler change in `app/reconciler/dedup.py` + `location_creator.py`.
The reconciler change prevents new duplicates; this script cleans up
the duplicates that already exist when two scrapers produced different
names AND different orgs for the same physical pantry.

For each cluster of duplicates:
  1. Pick a survivor canonical using the PTF API survivor rule
     (`has_qualifying_source DESC, confidence_score DESC NULLS LAST,
     id ASC`). FANO-allowlist members win first, then highest
     confidence, then min id as deterministic tie-break. Mirrors the
     PTF `_LIST_SQL` ORDER BY in
     `app/api/v1/partners/ptf/locations_queries.py` so the API's
     serve-time view and this backfill's pick converge on the same row.
  2. Repoint child tables (location_source, accessibility, address,
     contact, language, phone, schedule, service_at_location) from
     each duplicate to the survivor, skipping rows that would conflict
     with an existing survivor row on UNIQUE constraints.
  3. Set `is_canonical=FALSE` on the duplicate (soft-delete). The row
     is retained so existing `record_version` references stay valid
     and the audit trail is preserved.

Rows with `verified_by IN ('admin','source','claimed')` are exempt —
the cleanup script can never overwrite human-curated work (Principle
VI). The detection SQL filters them out on both sides of every pair.

Dry-run by default. Pass `--apply` to commit.

Each cluster is processed in its own savepoint, so a single failure
doesn't roll back prior successful merges in the same run.

Usage:
    ./bouy exec app python scripts/dedupe_near_duplicate_locations.py
    ./bouy exec app python scripts/dedupe_near_duplicate_locations.py --apply
    ./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py
    ./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST
from app.core.config import settings
from app.reconciler.dedup import (
    _ADDR_SIM_THRESHOLD,
    _DEDUP_LOOSE_DEG,
    _NAME_SIM_THRESHOLD,
    accent_fold_expr,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Child tables that hold a FK to location(id). Each entry is
# (table, fk_column, unique_constraint_columns).
# unique_constraint_columns is the set of columns that, together with
# location_id, make a row unique — used to skip rows that would clash
# with an existing row on the canonical side.
#
# SECURITY: These identifiers are interpolated into raw SQL strings via
# f-strings in repoint_child_rows. The constant lives at module scope
# with hard-coded string literals only — never accept user input here.
# The `# noqa: S608` / `# nosec B608` markers in repoint_child_rows
# inherit this rationale.
CHILD_TABLES: list[tuple[str, str, list[str]]] = [
    ("location_source", "location_id", ["scraper_id"]),
    ("address", "location_id", []),
    ("phone", "location_id", []),
    ("schedule", "location_id", []),
    ("service_at_location", "location_id", ["service_id"]),
    ("accessibility", "location_id", []),
    ("contact", "location_id", []),
    ("language", "location_id", []),
]


# Grandchild tables that FK to one of the UNIQUE-conflict parents above.
# When we DELETE a parent row on a UNIQUE conflict, its grandchildren
# would orphan via FK violation unless we first repoint them onto the
# survivor's matching parent row.
#
# This was the cause of the 13% FK-cascade failure rate on the first
# `--apply` run: `service_at_location` has FOUR children that reference
# it (contact, phone, schedule, service_area), and any cluster whose
# merge involved a UNIQUE-conflicting SAL row with any of those
# grandchildren would roll back.
#
# Same security rationale as CHILD_TABLES: identifiers are static
# literals, no user input.
GRANDCHILD_REPOINTS: dict[str, list[tuple[str, str]]] = {
    "service_at_location": [
        ("contact", "service_at_location_id"),
        ("phone", "service_at_location_id"),
        ("schedule", "service_at_location_id"),
        ("service_area", "service_at_location_id"),
    ],
}


# Append-only audit table. Created lazily on first --apply (CREATE TABLE
# IF NOT EXISTS) so this script can ship without a cross-repo migration —
# same pattern the Write API's `ingest_audit` table uses (per CLAUDE.md).
#
# A row per mutating action lets the companion `undo_dedup_run.py`
# reverse repoints + soft-deletes by `run_id` without Aurora PITR.
# UNIQUE-skip DELETEs still need PITR to actually restore the deleted
# row, but the full row snapshot is captured in `old_value` so an
# operator can identify exactly which rows need restoration.
_AUDIT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS dedup_run_audit (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    cluster_id TEXT NOT NULL,
    survivor_id UUID NOT NULL,
    duplicate_id UUID,
    table_name TEXT NOT NULL,
    row_id TEXT NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('repoint', 'delete', 'soft_delete')),
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dedup_run_audit_run_id
    ON dedup_run_audit(run_id);
"""


def ensure_audit_table(db: Session) -> None:
    """Create `dedup_run_audit` on first --apply if it doesn't exist.

    Lazy creation keeps this script self-contained — no need to push a
    migration through a separate channel. Mirrors `ingest_audit` from
    the Write API plugin.
    """
    db.execute(text(_AUDIT_TABLE_DDL))


def _log_audit(
    db: Session,
    *,
    run_id: str,
    cluster_id: str,
    survivor_id: str,
    duplicate_id: str | None,
    table_name: str,
    row_id: str,
    action: str,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    """Append one audit row for a mutation that's about to happen.

    Called BEFORE the mutation so a failure of the mutation leaves the
    savepoint in a state where the audit row is also rolled back. We
    never have audit rows for actions that didn't actually occur.
    """
    db.execute(
        text(
            """
            INSERT INTO dedup_run_audit (
                run_id, cluster_id, survivor_id, duplicate_id,
                table_name, row_id, action, old_value, new_value
            ) VALUES (
                :run_id, :cluster_id, :survivor_id, :duplicate_id,
                :table_name, :row_id, :action,
                CAST(:old_value AS JSONB),
                CAST(:new_value AS JSONB)
            )
            """
        ),
        {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "survivor_id": survivor_id,
            "duplicate_id": duplicate_id,
            "table_name": table_name,
            "row_id": row_id,
            "action": action,
            "old_value": json.dumps(old_value) if old_value is not None else None,
            "new_value": json.dumps(new_value) if new_value is not None else None,
        },
    )


def detection_sql() -> str:
    """SQL that finds candidate pairs under the Tier 3 fuzzy gate.

    Returns directed pairs with `a.id < b.id` so each undirected pair
    appears exactly once. Excludes human-curated rows on both sides
    (Principle VI). Mirrors the gate semantics of
    `app.reconciler.dedup.tier3_match_sql()` so the prevent-on-ingest
    and drain-backlog paths can't diverge.

    `SELECT DISTINCT` on the outer projection is load-bearing: the
    HSDS schema permits multiple physical addresses per location
    (init-scripts/01-hsds-schema.sql doesn't enforce one-per-location).
    Without DISTINCT, a 2×2 address cross between two pair candidates
    would inflate pair counts and over-report blast radius in the
    diagnostic. Address-gate semantics with DISTINCT: a pair matches
    if ANY physical-address pair clears the trigram + zip5 gate,
    which is the right behavior — distinct addresses on the same
    canonical are usually scraper-side typos, not legitimately
    different sites.
    """
    name_fold_a = accent_fold_expr("a.name")
    name_fold_b = accent_fold_expr("b.name")
    addr_fold_a = accent_fold_expr("addr_a.address_1")
    addr_fold_b = accent_fold_expr("addr_b.address_1")
    sql = f"""
        WITH candidate AS (
            SELECT DISTINCT
                a.id AS id_a,
                b.id AS id_b
            FROM location a
            JOIN location b
              ON a.id < b.id
             AND a.is_canonical = TRUE
             AND b.is_canonical = TRUE
             AND (a.verified_by IS NULL
                  OR a.verified_by NOT IN ('admin','source','claimed'))
             AND (b.verified_by IS NULL
                  OR b.verified_by NOT IN ('admin','source','claimed'))
             AND ABS(a.latitude - b.latitude) < :loose_deg
             AND ABS(a.longitude - b.longitude) < :loose_deg
             AND ST_DWithin(
                    ST_SetSRID(
                        ST_MakePoint(
                            CAST(a.longitude AS float8),
                            CAST(a.latitude  AS float8)
                        ), 4326),
                    ST_SetSRID(
                        ST_MakePoint(
                            CAST(b.longitude AS float8),
                            CAST(b.latitude  AS float8)
                        ), 4326),
                    :loose_deg
                 )
            LEFT JOIN address addr_a
                ON addr_a.location_id = a.id
               AND addr_a.address_type = 'physical'
            LEFT JOIN address addr_b
                ON addr_b.location_id = b.id
               AND addr_b.address_type = 'physical'
            WHERE (
                similarity({name_fold_a}, {name_fold_b}) > :name_sim
                OR (
                    addr_a.address_1 IS NOT NULL
                    AND addr_b.address_1 IS NOT NULL
                    AND addr_a.postal_code IS NOT NULL
                    AND SUBSTR(addr_a.postal_code, 1, 5)
                        = SUBSTR(addr_b.postal_code, 1, 5)
                    AND similarity({addr_fold_a}, {addr_fold_b}) > :addr_sim
                )
            )
        )
        SELECT id_a, id_b FROM candidate
    """  # noqa: S608  # nosec B608 - bind params and a static literal IN-list
    return sql


def pick_canonical_sql() -> str:
    """SQL to pick the survivor canonical from a cluster of duplicate ids.

    Mirrors the PTF API survivor pick (`has_qualifying_source DESC,
    confidence_score DESC NULLS LAST, id ASC`) so the API's serve-time
    view of a cluster and this script's pick converge on the same row.
    `qualifying_source` excludes submarine source_type because submarine
    is enrichment, not discovery.
    """
    return """
        WITH qualifying_source AS (
            SELECT location_id,
                   BOOL_OR(true) AS has_qualifying_source
            FROM location_source
            WHERE scraper_id IN :allowlist
              AND (source_type IS NULL OR source_type != 'submarine')
            GROUP BY location_id
        )
        SELECT l.id
        FROM location l
        LEFT JOIN qualifying_source qs ON qs.location_id = l.id
        WHERE l.id = ANY(:ids)
        ORDER BY COALESCE(qs.has_qualifying_source, false) DESC,
                 l.confidence_score DESC NULLS LAST,
                 l.id ASC
        LIMIT 1
    """


def find_duplicate_pairs(db: Session) -> list[dict[str, Any]]:
    """Return candidate duplicate pairs under the Tier 3 fuzzy gate."""
    rows = db.execute(
        text(detection_sql()),
        {
            "loose_deg": _DEDUP_LOOSE_DEG,
            "name_sim": _NAME_SIM_THRESHOLD,
            "addr_sim": _ADDR_SIM_THRESHOLD,
        },
    ).fetchall()
    return [{"id_a": str(r[0]), "id_b": str(r[1])} for r in rows]


def group_into_clusters(pairs: list[dict[str, Any]]) -> list[set[str]]:
    """Union-find over the pair edges. Two locations in the same cluster
    means they should all collapse to one canonical."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for pair in pairs:
        union(pair["id_a"], pair["id_b"])
    clusters: dict[str, set[str]] = defaultdict(set)
    nodes = {p["id_a"] for p in pairs} | {p["id_b"] for p in pairs}
    for node in nodes:
        clusters[find(node)].add(node)
    return [c for c in clusters.values() if len(c) > 1]


def pick_canonical(db: Session, cluster: set[str]) -> str:
    """Pick the survivor canonical via the PTF API survivor rule.

    Two binding strategies in one query, intentionally: `ANY(:ids)` for
    the cluster ids (passed as a Python list, simpler to plumb) and
    `expanding=True` on `:allowlist` (required by SQLAlchemy 2 to expand
    a tuple into a positional `IN (...)` clause). Both are bind params;
    no user input is interpolated into SQL text.
    """
    ids = list(cluster)
    allowlist = tuple(FANO_ALLOWLIST)
    stmt = text(pick_canonical_sql()).bindparams(
        bindparam("allowlist", expanding=True),
    )
    row = db.execute(stmt, {"ids": ids, "allowlist": allowlist}).first()
    if row is None:
        raise RuntimeError(
            f"No canonical found for cluster {cluster} — "
            "ids may have been concurrently soft-deleted or removed. "
            "Re-run detection to refresh the candidate set."
        )
    return str(row[0])


def repoint_child_rows(
    db: Session,
    canonical_id: str,
    duplicate_id: str,
    apply: bool,
    *,
    run_id: str | None = None,
    cluster_id: str | None = None,
) -> dict[str, dict[str, int]]:
    """Move child rows from duplicate -> canonical, skipping rows that
    would violate a UNIQUE constraint. Returns a summary by table.

    When `apply=True` and `run_id`/`cluster_id` are supplied, every
    repoint and every UNIQUE-skip DELETE is logged to
    `dedup_run_audit` BEFORE it happens — `undo_dedup_run.py` reads
    that log to reverse a bad run.

    UNIQUE-skip DELETEs are NOT reversible from the audit log alone
    (Aurora PITR still required) but the full row snapshot is captured
    in `old_value` so an operator can identify exactly which rows to
    restore.

    Largely mirrors `scripts/dedupe_same_org_locations.repoint_child_rows`.
    Duplicated rather than imported because the existing script lives
    outside the app package and we don't want test runners to pick up
    its CLI side effects via cross-import. **If you change the merge
    semantics here, mirror the change in
    `scripts/dedupe_same_org_locations.py::repoint_child_rows` so the
    two backfills don't diverge.**
    """
    summary: dict[str, dict[str, int]] = {}
    audit_enabled = apply and run_id is not None and cluster_id is not None
    for table, fk_col, unique_cols in CHILD_TABLES:
        moved = 0
        skipped = 0

        if unique_cols:
            # Fetch the full duplicate-side row so we can audit-log the
            # complete contents before deleting. row_to_json captures
            # every column including ones the script doesn't know about
            # (source_type, last_seen_at, payload columns, etc.) — those
            # are exactly the columns an operator needs to identify the
            # destroyed row if a fuzzy false-positive is reported.
            #
            # Also fetch `c.id AS survivor_row_id` so we can repoint any
            # grandchildren (rows that FK to this row) onto the survivor's
            # matching row BEFORE we delete the duplicate's row.
            unique_join = " AND ".join([f"d.{c} = c.{c}" for c in unique_cols])
            conflict_query = text(
                f"""
                SELECT d.id, row_to_json(d.*) AS payload, c.id AS survivor_row_id
                FROM {table} d
                JOIN {table} c
                  ON c.{fk_col} = :canonical_id
                 AND {unique_join}
                WHERE d.{fk_col} = :duplicate_id
                """  # noqa: S608  # nosec B608 - identifiers from static CHILD_TABLES
            )
            conflict_rows = [
                (r[0], r[1], r[2])
                for r in db.execute(
                    conflict_query,
                    {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
                )
            ]
            skipped = len(conflict_rows)

            if apply and skipped > 0:
                # Step 1: repoint grandchildren onto the survivor's
                # matching row. Without this, the DELETE in step 3 would
                # violate FK constraints (e.g.,
                # schedule_service_at_location_id_fkey when SAL rows are
                # being deleted). The repoint is audit-logged per row
                # so undo can reverse it.
                grandchild_specs = GRANDCHILD_REPOINTS.get(table, [])
                for grand_table, grand_fk_col in grandchild_specs:
                    for dup_row_id, _payload, surv_row_id in conflict_rows:
                        result = db.execute(
                            text(
                                f"UPDATE {grand_table} "  # noqa: S608
                                f"SET {grand_fk_col} = :surv "
                                f"WHERE {grand_fk_col} = :dup "
                                f"RETURNING id"
                            ),  # nosec B608 - identifiers from static GRANDCHILD_REPOINTS
                            {"surv": surv_row_id, "dup": dup_row_id},
                        )
                        moved_grand_ids = [r[0] for r in result]
                        if audit_enabled:
                            for gid in moved_grand_ids:
                                _log_audit(
                                    db,
                                    run_id=run_id,  # type: ignore[arg-type]
                                    cluster_id=cluster_id,  # type: ignore[arg-type]
                                    survivor_id=canonical_id,
                                    duplicate_id=duplicate_id,
                                    table_name=grand_table,
                                    row_id=str(gid),
                                    action="repoint",
                                    old_value={grand_fk_col: str(dup_row_id)},
                                    new_value={grand_fk_col: str(surv_row_id)},
                                )

                # Step 2: audit-log the about-to-be-deleted parent rows.
                if audit_enabled:
                    for row_id, payload, _surv in conflict_rows:
                        _log_audit(
                            db,
                            run_id=run_id,  # type: ignore[arg-type]
                            cluster_id=cluster_id,  # type: ignore[arg-type]
                            survivor_id=canonical_id,
                            duplicate_id=duplicate_id,
                            table_name=table,
                            row_id=str(row_id),
                            action="delete",
                            old_value=payload,
                        )

                # Step 3: DELETE the conflicting parent rows.
                placeholders = ",".join([f":cid_{i}" for i in range(skipped)])
                delete_params = {
                    f"cid_{i}": conflict_rows[i][0] for i in range(skipped)
                }
                db.execute(
                    text(
                        f"DELETE FROM {table} WHERE id IN ({placeholders})"  # noqa: S608
                    ),  # nosec B608 - identifiers from static CHILD_TABLES; placeholders are internal counters
                    delete_params,
                )

        if apply:
            # RETURNING id so we can audit-log each moved row. A bulk
            # UPDATE alone gives only rowcount; per-row ids are
            # essential for the undo path.
            update_result = db.execute(
                text(
                    f"UPDATE {table} SET {fk_col} = :canonical_id "  # noqa: S608
                    f"WHERE {fk_col} = :duplicate_id "
                    f"RETURNING id"
                ),  # nosec B608 - identifiers from static CHILD_TABLES
                {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
            )
            moved_ids = [r[0] for r in update_result]
            moved = len(moved_ids)
            if audit_enabled:
                for row_id in moved_ids:
                    _log_audit(
                        db,
                        run_id=run_id,  # type: ignore[arg-type]
                        cluster_id=cluster_id,  # type: ignore[arg-type]
                        survivor_id=canonical_id,
                        duplicate_id=duplicate_id,
                        table_name=table,
                        row_id=str(row_id),
                        action="repoint",
                        old_value={fk_col: duplicate_id},
                        new_value={fk_col: canonical_id},
                    )
        else:
            count_result = db.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} "  # noqa: S608
                    f"WHERE {fk_col} = :duplicate_id"
                ),  # nosec B608 - identifiers from static CHILD_TABLES
                {"duplicate_id": duplicate_id},
            )
            moved = count_result.scalar() or 0
            moved = max(0, moved - skipped)

        summary[table] = {"moved": moved, "skipped": skipped}
    return summary


def soft_delete_duplicate(
    db: Session,
    duplicate_id: str,
    apply: bool,
    *,
    run_id: str | None = None,
    cluster_id: str | None = None,
    survivor_id: str | None = None,
) -> int:
    """Mark the duplicate as non-canonical so it no longer appears in
    matches or the public API. Keep the row so historical record_version
    references remain valid (Principle VI auditability).

    `WHERE is_canonical = TRUE` guard makes re-runs safe — a row that
    was already soft-deleted by a previous run is a no-op here, and
    we don't emit a phantom audit row.

    Returns the number of rows affected (0 = already soft-deleted; 1 =
    flipped this run).
    """
    if not apply:
        return 0
    result = db.execute(
        text(
            "UPDATE location SET is_canonical = FALSE "
            "WHERE id = :id AND is_canonical = TRUE"
        ),
        {"id": duplicate_id},
    )
    rowcount = result.rowcount or 0
    if rowcount > 0 and run_id is not None and cluster_id is not None and survivor_id is not None:
        _log_audit(
            db,
            run_id=run_id,
            cluster_id=cluster_id,
            survivor_id=survivor_id,
            duplicate_id=duplicate_id,
            table_name="location",
            row_id=duplicate_id,
            action="soft_delete",
            old_value={"is_canonical": True},
            new_value={"is_canonical": False},
        )
    return rowcount


def merge_cluster(
    db: Session,
    cluster: set[str],
    apply: bool,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Merge all locations in a cluster onto one survivor canonical.

    `cluster_id` for audit logging is derived from the lexicographically
    minimum id in the cluster — deterministic, doesn't require a
    separate sequence, and stable across re-runs.
    """
    canonical_id = pick_canonical(db, cluster)
    duplicates = sorted(cluster - {canonical_id})
    cluster_id = min(cluster)
    per_dup_summary: dict[str, dict[str, dict[str, int]]] = {}
    for dup_id in duplicates:
        per_dup_summary[dup_id] = repoint_child_rows(
            db,
            canonical_id,
            dup_id,
            apply,
            run_id=run_id,
            cluster_id=cluster_id,
        )
        soft_delete_duplicate(
            db,
            dup_id,
            apply,
            run_id=run_id,
            cluster_id=cluster_id,
            survivor_id=canonical_id,
        )
    return {
        "canonical_id": canonical_id,
        "duplicates": duplicates,
        "cluster_id": cluster_id,
        "per_duplicate": per_dup_summary,
    }


def diagnostic_count(db: Session) -> dict[str, int]:
    """Return pair_count + a proxy for locations-involved.

    Lets operators eyeball the blast radius before committing. Counting
    distinct ids across BOTH columns of every pair needs union-find on
    the full pair list, so this query gives a fast lower-bound proxy:
    distinct `id_a` values. Real locations-involved comes from
    `group_into_clusters` after pair fetch.

    A `COUNT()` aggregate **always** returns at least one row, so a
    `None` result here means the query never executed (permissions
    issue, connection drop mid-fetch, etc.). Silently treating that as
    "no work to do" would make a permissions misconfiguration look
    identical to a clean DB — raise instead.
    """
    result = db.execute(
        text(
            f"""
            WITH pairs AS ({detection_sql()})
            SELECT COUNT(*) AS pair_count,
                   COUNT(DISTINCT id_a) AS proxy_locations
            FROM pairs
            """  # noqa: S608  # nosec B608 - inner detection_sql() is parameterized
        ),
        {
            "loose_deg": _DEDUP_LOOSE_DEG,
            "name_sim": _NAME_SIM_THRESHOLD,
            "addr_sim": _ADDR_SIM_THRESHOLD,
        },
    ).first()
    if result is None:
        raise RuntimeError(
            "diagnostic_count returned no row — COUNT aggregates always "
            "return a row, so this means the query failed to execute. "
            "Check DB permissions and connectivity before retrying."
        )
    return {
        "pair_count": int(result[0]),
        "locations_involved_proxy": int(result[1]),
    }


def check_haarrrvest_freshness(db: Session, *, max_age_hours: int = 12) -> bool:
    """Verify the latest HAARRRvest SQL dump in `record_version` is
    recent. The HAARRRvest publisher writes record_version rows for
    every export; if those rows are stale, the latest known-good
    rollback target is also stale.

    This is a heuristic pre-flight — not a hard guarantee. The real
    safety net is a manual Aurora snapshot taken before `--apply`
    (see CLAUDE.md operator runbook). But forcing the operator to
    notice "the last dump was 3 days ago" before committing prevents
    the most common failure mode: backfilling onto a DB whose
    published dump no longer matches reality.

    Returns True if a dump newer than `max_age_hours` exists.
    """
    result = db.execute(
        text(
            """
            SELECT MAX(created_at) AS most_recent
            FROM record_version
            WHERE created_at > NOW() - (:max_age_hours || ' hours')::interval
            LIMIT 1
            """
        ),
        {"max_age_hours": str(max_age_hours)},
    ).first()
    if result is None or result[0] is None:
        return False
    return True


def _dump_sample_clusters(
    db: Session,
    clusters: list[set[str]],
    n: int,
) -> None:
    """Print N random clusters' before-state JSON to stdout for the
    operator to eyeball. Dry-run only — never commits."""
    sample = random.sample(clusters, min(n, len(clusters)))
    for cluster in sample:
        try:
            survivor_id = pick_canonical(db, cluster)
        except RuntimeError as exc:
            logger.warning("Sample cluster pick failed: %s", exc)
            continue
        ids = sorted(cluster)
        rows = db.execute(
            text(
                """
                SELECT id, name, latitude, longitude, confidence_score,
                       verified_by, is_canonical
                FROM location
                WHERE id = ANY(:ids)
                ORDER BY id
                """
            ),
            {"ids": ids},
        ).fetchall()
        payload = {
            "cluster_ids": ids,
            "survivor": survivor_id,
            "would_soft_delete": [i for i in ids if i != survivor_id],
            "rows": [dict(r._mapping) for r in rows],
        }
        print(json.dumps(payload, default=str, indent=2))


def main() -> int:  # noqa: C901 - linear top-to-bottom orchestration, splitting would hurt readability
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the merge. Default is dry-run (logs only).",
    )
    parser.add_argument(
        "--max-clusters",
        type=int,
        default=None,
        help=(
            "Cap the run to the first N clusters (ordered by min cluster id). "
            "Enables staged rollout: --max-clusters 50, then 500, then full run."
        ),
    )
    parser.add_argument(
        "--dry-run-sample",
        type=int,
        default=0,
        help=(
            "In dry-run mode, dump N random clusters' before-state JSON to "
            "stdout so operators can eyeball merges before --apply."
        ),
    )
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help=(
            "Skip the HAARRRvest freshness pre-flight check. Use only "
            "during emergency runs when a known-good dump exists in S3 "
            "but the record_version metadata is missing or stale."
        ),
    )
    parser.add_argument(
        "--fail-fast-threshold",
        type=int,
        default=5,
        help=(
            "Abort the run if more than this many CONSECUTIVE clusters fail. "
            "Protects against a logic bug looking like routine transient "
            "FK errors. Default 5."
        ),
    )
    args = parser.parse_args()

    # Run identifier — stamped on every audit row so a bad run is
    # reversible by `scripts/undo_dedup_run.py --run-id <id>`.
    run_id = str(uuid.uuid4())
    logger.info("Run id: %s", run_id)

    engine = create_engine(settings.DATABASE_URL)
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        # Pre-flight: HAARRRvest freshness. Skip on dry-run (no harm
        # exploring without a fresh dump) and when explicitly disabled.
        if args.apply and not args.skip_freshness_check:
            if not check_haarrrvest_freshness(db):
                logger.error(
                    "Pre-flight failed: no record_version rows in the last "
                    "12 hours. The most recent rollback target is stale. "
                    "Either let HAARRRvest publish a fresh dump, take a "
                    "manual Aurora snapshot, or pass --skip-freshness-check."
                )
                return 2

        # Ensure the audit table exists before any writes. Idempotent
        # CREATE TABLE IF NOT EXISTS — safe on every run.
        if args.apply:
            ensure_audit_table(db)
            db.commit()

        try:
            diag = diagnostic_count(db)
        except RuntimeError:
            logger.exception("Diagnostic count failed — aborting")
            return 2
        logger.info(
            "Diagnostic: pair_count=%d, locations_involved_proxy=%d",
            diag["pair_count"],
            diag["locations_involved_proxy"],
        )

        pairs = find_duplicate_pairs(db)
        if not pairs:
            logger.info(
                "No fuzzy duplicate pairs found within %sdeg", _DEDUP_LOOSE_DEG
            )
            return 0
        logger.info(
            "Found %d fuzzy duplicate pairs (Tier 3 gate, <=%sdeg)",
            len(pairs),
            _DEDUP_LOOSE_DEG,
        )
        clusters = group_into_clusters(pairs)
        # Stable ordering for --max-clusters: lexicographic min id.
        # Without this, a re-run with --max-clusters 50 might touch a
        # different 50 each time.
        clusters_sorted: list[set[str]] = sorted(clusters, key=lambda c: min(c))
        logger.info(
            "Grouped into %d clusters covering %d locations",
            len(clusters_sorted),
            sum(len(c) for c in clusters_sorted),
        )

        # --dry-run-sample only matters in dry-run; bail early if --apply
        # was passed so we don't accidentally commit a partial sample.
        if not args.apply and args.dry_run_sample > 0:
            _dump_sample_clusters(db, clusters_sorted, args.dry_run_sample)

        if args.max_clusters is not None:
            clusters_sorted = clusters_sorted[: args.max_clusters]
            logger.info(
                "Capped to first %d clusters via --max-clusters",
                len(clusters_sorted),
            )

        total_canonicals = 0
        total_duplicates_merged = 0
        total_rows_moved = 0
        total_rows_skipped = 0
        failed_clusters: list[dict[str, Any]] = []
        consecutive_failures = 0

        for cluster in clusters_sorted:
            # Isolate each cluster in its own savepoint so a single
            # failure (e.g., an FK violation from a since-deleted child
            # row) doesn't roll back every successful merge in the run.
            savepoint = db.begin_nested()
            try:
                result = merge_cluster(db, cluster, args.apply, run_id=run_id)
                savepoint.commit()
                consecutive_failures = 0
            except (IntegrityError, OperationalError) as exc:
                # Transient/recoverable: FK violation from a since-
                # deleted child, serialization conflict, lock timeout.
                # Roll back this cluster's savepoint and continue.
                savepoint.rollback()
                failed_clusters.append(
                    {"cluster": sorted(cluster), "error": str(exc)}
                )
                logger.warning(
                    "Cluster %s rolled back (transient): %s",
                    sorted(cluster),
                    exc,
                )
                consecutive_failures += 1
                if consecutive_failures > args.fail_fast_threshold:
                    logger.error(
                        "Aborting: %d consecutive cluster failures exceed "
                        "--fail-fast-threshold=%d. Likely a logic bug, not "
                        "transient errors.",
                        consecutive_failures,
                        args.fail_fast_threshold,
                    )
                    break
                continue
            except Exception:
                # Anything not in (IntegrityError, OperationalError) is
                # almost certainly a bug — KeyError, RuntimeError from
                # pick_canonical, SQL syntax error in our own f-strings.
                # Roll back the savepoint AND the whole run; if we
                # continue we'd plow through every remaining cluster
                # generating identical "failures" that mask the bug.
                savepoint.rollback()
                logger.exception(
                    "Cluster %s hit a non-transient error — aborting run",
                    sorted(cluster),
                )
                db.rollback()
                return 2

            total_canonicals += 1
            total_duplicates_merged += len(result["duplicates"])
            for dup_summary in result["per_duplicate"].values():
                for table_summary in dup_summary.values():
                    total_rows_moved += table_summary["moved"]
                    total_rows_skipped += table_summary["skipped"]
            logger.info(
                "Cluster -> canonical=%s, duplicates=%s",
                result["canonical_id"],
                result["duplicates"],
            )

        if args.apply:
            try:
                db.commit()
            except Exception:
                # Outer commit failure rolls back every savepoint —
                # nothing was persisted. The run_id has no committed
                # audit rows, so undo is a no-op. Document the recovery
                # state in the log line so an operator on-call sees it
                # without digging.
                logger.exception(
                    "Final commit failed — NOTHING was persisted, all "
                    "savepoints rolled back. Safe to re-run. (run_id=%s)",
                    run_id,
                )
                return 2
            logger.info("COMMITTED (run_id=%s)", run_id)
        else:
            db.rollback()
            logger.info("DRY RUN — no changes committed (re-run with --apply)")

        logger.info(
            "Summary: run_id=%s, canonicals=%d, duplicates_merged=%d, "
            "child_rows_moved=%d, child_rows_skipped_as_conflict=%d, "
            "failed_clusters=%d",
            run_id,
            total_canonicals,
            total_duplicates_merged,
            total_rows_moved,
            total_rows_skipped,
            len(failed_clusters),
        )
        if failed_clusters:
            logger.warning(
                "Failed clusters (each rolled back individually, NOT committed):"
            )
            for failure in failed_clusters:
                logger.warning(
                    "  cluster=%s error=%s", failure["cluster"], failure["error"]
                )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
