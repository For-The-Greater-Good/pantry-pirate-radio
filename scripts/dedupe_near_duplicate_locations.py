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
     confidence, then min id as deterministic tie-break. Mirrors
     `app/api/v1/partners/ptf/locations_queries.py:308-311` so the
     API's serve-time view and this backfill's pick converge on the
     same row.
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
import logging
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import create_engine, text
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


def detection_sql() -> str:
    """SQL that finds candidate pairs under the Tier 3 fuzzy gate.

    Returns directed pairs with `a.id < b.id` so each undirected pair
    appears exactly once. Excludes human-curated rows on both sides
    (Principle VI). Mirrors the gate semantics of
    `app.reconciler.dedup.tier3_match_sql()` so the prevent-on-ingest
    and drain-backlog paths can't diverge.
    """
    name_fold_a = accent_fold_expr("a.name")
    name_fold_b = accent_fold_expr("b.name")
    addr_fold_a = accent_fold_expr("addr_a.address_1")
    addr_fold_b = accent_fold_expr("addr_b.address_1")
    sql = f"""
        WITH candidate AS (
            SELECT
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
    """Pick the survivor canonical via the PTF API survivor rule."""
    ids = list(cluster)
    # SQLAlchemy `expanding=True` handles tuple IN; we use ANY(:ids)
    # instead so the same query shape works with a Python list passed
    # directly. The FANO allowlist is a tuple of strings (no user input).
    allowlist = tuple(FANO_ALLOWLIST)
    from sqlalchemy import bindparam

    stmt = text(pick_canonical_sql()).bindparams(
        bindparam("allowlist", expanding=True),
    )
    row = db.execute(stmt, {"ids": ids, "allowlist": allowlist}).first()
    if row is None:
        raise RuntimeError(f"No canonical found for cluster {cluster}")
    return str(row[0])


def repoint_child_rows(
    db: Session,
    canonical_id: str,
    duplicate_id: str,
    apply: bool,
) -> dict[str, dict[str, int]]:
    """Move child rows from duplicate -> canonical, skipping rows that
    would violate a UNIQUE constraint. Returns a summary by table.

    Identical to `dedupe_same_org_locations.repoint_child_rows` —
    duplicated rather than imported because the existing script lives
    outside the app package and we don't want test runners to pick up
    its CLI side effects via cross-import.
    """
    summary: dict[str, dict[str, int]] = {}
    for table, fk_col, unique_cols in CHILD_TABLES:
        moved = 0
        skipped = 0

        if unique_cols:
            unique_join = " AND ".join([f"d.{c} = c.{c}" for c in unique_cols])
            conflict_query = text(
                f"""
                SELECT d.id
                FROM {table} d
                JOIN {table} c
                  ON c.{fk_col} = :canonical_id
                 AND {unique_join}
                WHERE d.{fk_col} = :duplicate_id
                """  # noqa: S608  # nosec B608 - identifiers from static CHILD_TABLES
            )
            conflict_ids = [
                r[0]
                for r in db.execute(
                    conflict_query,
                    {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
                )
            ]
            skipped = len(conflict_ids)

            if apply and skipped > 0:
                placeholders = ",".join([f":cid_{i}" for i in range(skipped)])
                delete_params = {f"cid_{i}": conflict_ids[i] for i in range(skipped)}
                db.execute(
                    text(
                        f"DELETE FROM {table} WHERE id IN ({placeholders})"  # noqa: S608
                    ),  # nosec B608 - identifiers from static CHILD_TABLES; placeholders are internal counters
                    delete_params,
                )

        if apply:
            update_result = db.execute(
                text(
                    f"UPDATE {table} SET {fk_col} = :canonical_id "  # noqa: S608
                    f"WHERE {fk_col} = :duplicate_id"
                ),  # nosec B608 - identifiers from static CHILD_TABLES
                {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
            )
            moved = update_result.rowcount or 0
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


def soft_delete_duplicate(db: Session, duplicate_id: str, apply: bool) -> None:
    """Mark the duplicate as non-canonical so it no longer appears in
    matches or the public API. Keep the row so historical record_version
    references remain valid (Principle VI auditability)."""
    if not apply:
        return
    db.execute(
        text("UPDATE location SET is_canonical = FALSE WHERE id = :id"),
        {"id": duplicate_id},
    )


def merge_cluster(db: Session, cluster: set[str], apply: bool) -> dict[str, Any]:
    """Merge all locations in a cluster onto one survivor canonical."""
    canonical_id = pick_canonical(db, cluster)
    duplicates = sorted(cluster - {canonical_id})
    per_dup_summary: dict[str, dict[str, dict[str, int]]] = {}
    for dup_id in duplicates:
        per_dup_summary[dup_id] = repoint_child_rows(db, canonical_id, dup_id, apply)
        soft_delete_duplicate(db, dup_id, apply)
    return {
        "canonical_id": canonical_id,
        "duplicates": duplicates,
        "per_duplicate": per_dup_summary,
    }


def diagnostic_count(db: Session) -> dict[str, int]:
    """Return pair_count + locations_involved for the dry-run summary.

    Lets operators eyeball the blast radius before committing.
    """
    result = db.execute(
        text(
            f"""
            WITH pairs AS ({detection_sql()})
            SELECT COUNT(*) AS pair_count,
                   COUNT(DISTINCT LEAST(id_a, id_b)
                       + 0
                   ) AS proxy_locations
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
        return {"pair_count": 0, "locations_involved": 0}
    # `proxy_locations` is a count-distinct proxy; the real
    # locations-involved figure comes from union-find on the full pair
    # list (more accurate but requires loading all pairs).
    return {
        "pair_count": int(result[0]),
        "locations_involved_proxy": int(result[1]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the merge. Default is dry-run (logs only).",
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        diag = diagnostic_count(db)
        logger.info(
            "Diagnostic: pair_count=%d, locations_involved_proxy=%d",
            diag["pair_count"],
            diag["locations_involved_proxy"],
        )

        pairs = find_duplicate_pairs(db)
        if not pairs:
            logger.info("No fuzzy duplicate pairs found within %sdeg", _DEDUP_LOOSE_DEG)
            return 0
        logger.info(
            "Found %d fuzzy duplicate pairs (Tier 3 gate, <=%sdeg)",
            len(pairs),
            _DEDUP_LOOSE_DEG,
        )
        clusters = group_into_clusters(pairs)
        logger.info(
            "Grouped into %d clusters covering %d locations",
            len(clusters),
            sum(len(c) for c in clusters),
        )

        total_canonicals = 0
        total_duplicates_merged = 0
        total_rows_moved = 0
        total_rows_skipped = 0
        failed_clusters: list[dict[str, Any]] = []

        for cluster in clusters:
            # Isolate each cluster in its own savepoint so a single
            # failure (e.g., an FK violation from a since-deleted child
            # row) doesn't roll back every successful merge in the run.
            savepoint = db.begin_nested()
            try:
                result = merge_cluster(db, cluster, args.apply)
                savepoint.commit()
            except Exception as exc:
                savepoint.rollback()
                failed_clusters.append({"cluster": sorted(cluster), "error": str(exc)})
                logger.exception(
                    "Cluster %s failed to merge — rolled back this cluster, "
                    "continuing with next",
                    sorted(cluster),
                )
                continue

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
            db.commit()
            logger.info("COMMITTED")
        else:
            db.rollback()
            logger.info("DRY RUN — no changes committed (re-run with --apply)")

        logger.info(
            "Summary: canonicals=%d, duplicates_merged=%d, "
            "child_rows_moved=%d, child_rows_skipped_as_conflict=%d, "
            "failed_clusters=%d",
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
