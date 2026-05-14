"""Preview what a Tier 3 merge would do to child-table content.

Picks a random sample of clusters from the live detection SQL, then for
each cluster shows:
  * Pre-merge: counts of phones / schedules / addresses / sources per
    row in the cluster, plus the actual values
  * Post-merge: what the survivor would have after repoint+UNIQUE-skip

Read-only. Never mutates. Use this before `--apply` to verify the
merge doesn't lose phones, schedules, etc.

Usage:
    ./bouy run-script --aws --prod scripts/inspect_dedup_merge_preview.py
    ./bouy run-script --aws --prod scripts/inspect_dedup_merge_preview.py --sample 25
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Reuse the dedup script's helpers — same import-as-module trick the
# tests use so this stays a true sibling without copy-paste drift.
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parent / "dedupe_near_duplicate_locations.py"
_spec = importlib.util.spec_from_file_location("dedupe_near", _SCRIPT)
assert _spec is not None and _spec.loader is not None
dedupe_near = importlib.util.module_from_spec(_spec)
sys.modules["dedupe_near"] = dedupe_near
_spec.loader.exec_module(dedupe_near)

from app.core.config import settings  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def cluster_child_summary(db: Any, cluster_ids: list[str]) -> dict[str, Any]:
    """Return per-table content for every row in the cluster, plus a
    simulated post-merge view."""
    out: dict[str, Any] = {"cluster_ids": cluster_ids, "tables": {}}

    # Phones
    phone_rows = db.execute(
        text(
            """
            SELECT location_id, number, type
            FROM phone
            WHERE location_id = ANY(:ids) AND number IS NOT NULL
            """
        ),
        {"ids": cluster_ids},
    ).fetchall()
    phone_numbers = [r[1] for r in phone_rows]
    out["tables"]["phone"] = {
        "pre_rows": len(phone_rows),
        "pre_distinct_numbers": len(set(phone_numbers)),
        "post_repoint_rows": len(phone_rows),  # all repoint, none drop
        "post_distinct_numbers": len(set(phone_numbers)),  # same
        "duplicated_after_merge": len(phone_rows) - len(set(phone_numbers)),
        "values": sorted(set(phone_numbers)),
    }

    # Schedules — using opens_at/closes_at as a content fingerprint
    sched_rows = db.execute(
        text(
            """
            SELECT location_id, freq, byday, opens_at, closes_at, description
            FROM schedule
            WHERE location_id = ANY(:ids)
            """
        ),
        {"ids": cluster_ids},
    ).fetchall()
    sched_fingerprints = [
        (r[1], r[2], r[3], r[4], r[5]) for r in sched_rows
    ]
    out["tables"]["schedule"] = {
        "pre_rows": len(sched_rows),
        "pre_distinct_fingerprints": len(set(sched_fingerprints)),
        "post_repoint_rows": len(sched_rows),
        "duplicated_after_merge": (
            len(sched_rows) - len(set(sched_fingerprints))
        ),
    }

    # Addresses
    addr_rows = db.execute(
        text(
            """
            SELECT location_id, address_1, postal_code
            FROM address
            WHERE location_id = ANY(:ids) AND address_type = 'physical'
            """
        ),
        {"ids": cluster_ids},
    ).fetchall()
    addr_fingerprints = [(r[1], r[2]) for r in addr_rows]
    out["tables"]["address"] = {
        "pre_rows": len(addr_rows),
        "pre_distinct": len(set(addr_fingerprints)),
        "post_repoint_rows": len(addr_rows),
        "duplicated_after_merge": (
            len(addr_rows) - len(set(addr_fingerprints))
        ),
        "values": sorted({f"{r[1]} {r[2]}" for r in addr_rows}),
    }

    # location_source — the UNIQUE-conflict path
    ls_rows = db.execute(
        text(
            """
            SELECT location_id, scraper_id, source_type
            FROM location_source
            WHERE location_id = ANY(:ids)
            """
        ),
        {"ids": cluster_ids},
    ).fetchall()
    scrapers_per_loc: dict[str, list[str]] = {}
    for r in ls_rows:
        scrapers_per_loc.setdefault(str(r[0]), []).append(r[1])
    distinct_scrapers = {r[1] for r in ls_rows}
    # UNIQUE-skip count: rows that share a scraper_id with the survivor.
    # Simulate by assuming the LEXICOGRAPHICALLY MIN id is survivor (mirrors
    # the dedup script's tie-break — not always the actual survivor pick
    # but a fair approximation for blast-radius preview).
    survivor_approx = sorted(cluster_ids)[0]
    survivor_scrapers = set(scrapers_per_loc.get(survivor_approx, []))
    would_delete = 0
    for loc_id, scrapers in scrapers_per_loc.items():
        if loc_id == survivor_approx:
            continue
        for s in scrapers:
            if s in survivor_scrapers:
                would_delete += 1
    out["tables"]["location_source"] = {
        "pre_rows": len(ls_rows),
        "pre_distinct_scrapers": len(distinct_scrapers),
        "would_unique_skip_delete": would_delete,
        "post_rows": len(ls_rows) - would_delete,
        "scrapers": sorted(distinct_scrapers),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="How many random clusters to preview (default 10).",
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        logger.info("Fetching pairs via Tier 3 detection SQL...")
        pairs = dedupe_near.find_duplicate_pairs(db)
        clusters = dedupe_near.group_into_clusters(pairs)
        logger.info(
            "Pool: %d pairs, %d clusters. Sampling %d.",
            len(pairs),
            len(clusters),
            min(args.sample, len(clusters)),
        )
        if not clusters:
            return 0
        sample = random.sample(clusters, min(args.sample, len(clusters)))

        agg_lost_phone = 0
        agg_lost_schedule = 0
        agg_lost_addr = 0
        agg_unique_delete = 0
        agg_phone_dup = 0
        agg_sched_dup = 0
        agg_addr_dup = 0

        for c in sample:
            ids = sorted(c)
            summary = cluster_child_summary(db, ids)
            print(json.dumps(summary, indent=2, default=str))
            print()
            t = summary["tables"]
            # "lost" = pre_rows - post (always 0 for non-unique tables
            # because they all repoint). location_source can lose rows.
            agg_unique_delete += t["location_source"]["would_unique_skip_delete"]
            agg_phone_dup += t["phone"]["duplicated_after_merge"]
            agg_sched_dup += t["schedule"]["duplicated_after_merge"]
            agg_addr_dup += t["address"]["duplicated_after_merge"]
            agg_lost_phone += 0  # always 0 — phone has no UNIQUE
            agg_lost_schedule += 0  # always 0
            agg_lost_addr += 0  # always 0

        print("=== SAMPLE AGGREGATES ===")
        print(
            f"phone rows lost: {agg_lost_phone}      "
            f"(always 0 — non-unique table)"
        )
        print(
            f"schedule rows lost: {agg_lost_schedule}   "
            f"(always 0 — non-unique table)"
        )
        print(
            f"address rows lost: {agg_lost_addr}    "
            f"(always 0 — non-unique table)"
        )
        print(f"location_source UNIQUE-skip deletes (audited): {agg_unique_delete}")
        print()
        print(
            f"post-merge content duplication (could surface in API):"
        )
        print(f"  duplicate phone numbers on survivor: {agg_phone_dup}")
        print(f"  duplicate schedules on survivor:     {agg_sched_dup}")
        print(f"  duplicate addresses on survivor:     {agg_addr_dup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
