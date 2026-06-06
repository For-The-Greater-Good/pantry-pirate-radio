"""One-shot backfill: merge same-org/same-name duplicate locations within
a configurable radius.

Counterpart to the reconciler change in
`app/reconciler/location_creator.py`. The reconciler change prevents new
duplicates; this script cleans up the duplicates that already exist.

For each cluster of duplicates:
  1. Pick a canonical (most location_source rows, then earliest created_at).
  2. Repoint child tables (location_source, accessibility, address,
     contact, language, phone, schedule, service_at_location) from each
     duplicate to the canonical, skipping rows that would conflict with
     an existing canonical row on UNIQUE constraints.
  3. Set is_canonical = FALSE on the duplicate (soft-delete). The row is
     retained so existing record_version references stay valid.

Dry-run by default. Pass --apply to commit.

Each cluster is processed in its own savepoint, so a single failure
doesn't roll back prior successful merges in the same run.

Usage:
    ./bouy exec app python scripts/dedupe_same_org_locations.py
    ./bouy exec app python scripts/dedupe_same_org_locations.py --apply
    ./bouy exec app python scripts/dedupe_same_org_locations.py --max-distance-deg 0.001 --apply
    ./bouy run-script --aws --prod scripts/dedupe_same_org_locations.py
    ./bouy run-script --aws --prod scripts/dedupe_same_org_locations.py --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

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


def find_duplicate_pairs(db: Session, max_distance_deg: float) -> list[dict[str, Any]]:
    """Return clusters of canonical locations with the same name + same
    organization within max_distance_deg of each other."""
    query = text(
        """
        WITH candidate AS (
            SELECT
                a.id AS id_a,
                b.id AS id_b,
                a.name AS name,
                a.organization_id AS organization_id,
                a.latitude AS lat_a,
                a.longitude AS lon_a,
                b.latitude AS lat_b,
                b.longitude AS lon_b
            FROM location a
            JOIN location b
              ON a.id < b.id
             AND a.is_canonical = TRUE
             AND b.is_canonical = TRUE
             AND a.organization_id IS NOT NULL
             AND a.organization_id = b.organization_id
             AND LOWER(TRIM(a.name)) = LOWER(TRIM(b.name))
             AND ABS(a.latitude - b.latitude) < :max_dist
             AND ABS(a.longitude - b.longitude) < :max_dist
        )
        SELECT id_a, id_b, name, organization_id,
               lat_a, lon_a, lat_b, lon_b
        FROM candidate
        ORDER BY name, organization_id
        """
    )
    rows = db.execute(query, {"max_dist": max_distance_deg}).fetchall()
    return [
        {
            "id_a": r[0],
            "id_b": r[1],
            "name": r[2],
            "organization_id": r[3],
            "lat_a": r[4],
            "lon_a": r[5],
            "lat_b": r[6],
            "lon_b": r[7],
        }
        for r in rows
    ]


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
    """Pick the canonical from a cluster. Prefer the location with the
    most location_source rows (best multi-scraper coverage), tie-break
    by earliest created_at (oldest record likely has the longest paper
    trail in record_version)."""
    ids = list(cluster)
    placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
    params = {f"id_{i}": ids[i] for i in range(len(ids))}
    query = text(
        f"""
        SELECT l.id,
               COALESCE(s.source_count, 0) AS source_count,
               l.created_at
        FROM location l
        LEFT JOIN (
            SELECT location_id, COUNT(*) AS source_count
            FROM location_source
            GROUP BY location_id
        ) s ON s.location_id = l.id
        WHERE l.id IN ({placeholders})
        ORDER BY source_count DESC, l.created_at ASC
        LIMIT 1
        """
    )
    row = db.execute(query, params).first()
    if row is None:
        raise RuntimeError(f"No canonical found for cluster {cluster}")
    return row[0]


def repoint_child_rows(
    db: Session,
    canonical_id: str,
    duplicate_id: str,
    apply: bool,
) -> dict[str, dict[str, int]]:
    """Move child rows from duplicate -> canonical, skipping rows that
    would violate a UNIQUE constraint. Returns a summary by table."""
    summary: dict[str, dict[str, int]] = {}
    for table, fk_col, unique_cols in CHILD_TABLES:
        moved = 0
        skipped = 0

        if unique_cols:
            # Find duplicate rows that DON'T conflict (move them) and
            # those that DO (skip — they're already represented on the
            # canonical and a separate cleanup pass can decide whether
            # to delete the duplicate or keep both).
            unique_join = " AND ".join([f"d.{c} = c.{c}" for c in unique_cols])
            conflict_query = text(
                f"""
                SELECT d.id
                FROM {table} d
                JOIN {table} c
                  ON c.{fk_col} = :canonical_id
                 AND {unique_join}
                WHERE d.{fk_col} = :duplicate_id
                """
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
                # Drop the duplicate-side rows that would conflict on the
                # canonical. They're redundant data already captured on
                # the canonical side.
                placeholders = ",".join([f":cid_{i}" for i in range(skipped)])
                delete_params = {f"cid_{i}": conflict_ids[i] for i in range(skipped)}
                db.execute(
                    text(f"DELETE FROM {table} WHERE id IN ({placeholders})"),
                    delete_params,
                )

        # Repoint the remaining rows
        if apply:
            update_result = db.execute(
                text(
                    f"UPDATE {table} SET {fk_col} = :canonical_id "
                    f"WHERE {fk_col} = :duplicate_id"
                ),
                {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
            )
            moved = update_result.rowcount or 0
        else:
            count_result = db.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} " f"WHERE {fk_col} = :duplicate_id"
                ),
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
    survivor_id: str | None = None,
) -> None:
    """Mark the duplicate as non-canonical so it no longer appears in
    matches or the public API. Keep the row so historical record_version
    references remain valid."""
    if not apply:
        return
    result = db.execute(
        text("UPDATE location SET is_canonical = FALSE WHERE id = :id"),
        {"id": duplicate_id},
    )
    # Federation Delete hook (PR-C Task 5, §6.2e/§9). This older script keeps no
    # dedup_run_audit, so redirectTo falls back to the immediate survivor (still
    # chain-resolved if a near-duplicate run later supersedes it). Guarded +
    # fail-soft inside publish_location_delete.
    if (result.rowcount or 0) > 0 and survivor_id is not None:
        from app.federation.publish import publish_location_delete

        publish_location_delete(
            db, dead_location_id=duplicate_id, survivor_location_id=survivor_id
        )


def merge_cluster(db: Session, cluster: set[str], apply: bool) -> dict[str, Any]:
    """Merge all locations in a cluster onto one canonical."""
    canonical_id = pick_canonical(db, cluster)
    duplicates = sorted(cluster - {canonical_id})
    per_dup_summary: dict[str, dict[str, dict[str, int]]] = {}
    for dup_id in duplicates:
        per_dup_summary[dup_id] = repoint_child_rows(db, canonical_id, dup_id, apply)
        soft_delete_duplicate(db, dup_id, apply, survivor_id=canonical_id)
    return {
        "canonical_id": canonical_id,
        "duplicates": duplicates,
        "per_duplicate": per_dup_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the merge. Default is dry-run (logs only).",
    )
    parser.add_argument(
        "--max-distance-deg",
        type=float,
        default=0.001,
        help=(
            "Maximum coordinate distance (degrees, applied independently "
            "to lat and lon) for a pair to be considered a same-org/"
            "same-name duplicate. Default 0.001 ≈ 111m in latitude; "
            "longitude distance varies with latitude (≈85m at 40 deg N, "
            "≈55m at 60 deg N). Conservative same-pantry merge radius."
        ),
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        pairs = find_duplicate_pairs(db, args.max_distance_deg)
        if not pairs:
            logger.info("No duplicate pairs found within %sdeg", args.max_distance_deg)
            return 0
        logger.info(
            "Found %d same-org/same-name duplicate pairs within %sdeg",
            len(pairs),
            args.max_distance_deg,
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
