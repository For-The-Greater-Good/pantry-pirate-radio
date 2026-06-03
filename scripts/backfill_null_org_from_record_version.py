"""One-shot backfill: recover `organization_id` for canonical locations
whose org link was NULLed, from the latest `record_version` snapshot.

Counterpart to the code fixes that STOP the org-wipe — SUB-1 (#499, submarine
stops NULLing `organization_id`) and REC-4 (#510, matched-update path is org
fill-only, never wipes). This script cleans up the ~6,906 canonical rows whose
org link was already lost before those fixes landed.

**ORDERING (critical):** apply in prod only AFTER #499 and #510 are merged and
deployed. The wipe came from the submarine/scraper update paths; if this
backfill runs while those still NULL the org on the next pass, the restored
links get wiped again. Dry-run is safe any time.

Recovery source: `record_version.data->>'organization_id'`. The reconciler
versions every canonical write, so a location whose org was later NULLed still
carries its last non-NULL org in an older version. `location_source` does NOT
store organization_id, so `record_version` is the only recovery source
(verified against prod). For each NULL-org canonical row we take the
highest-`version_num` location version whose `organization_id` is non-empty AND
still points to an existing `organization` row.

Owner protection (Principle VI): rows with `verified_by IN ('admin','source',
'claimed')` are exempt — never touched. The candidate query filters them out
and the UPDATE carries the same guard as defense-in-depth.

Reversibility: this script only ever runs `UPDATE location SET
organization_id = <recovered> WHERE organization_id IS NULL ...` — pure
fill-only UPDATEs, no deletes. Every change is logged to `org_backfill_audit`
keyed by `run_id`, and `--undo-run-id` reverses a run exactly (re-NULLing only
rows that still hold the value this run wrote and are still not human-curated).

Dry-run by default. Pass `--apply` to commit.

Usage:
    ./bouy exec app python scripts/backfill_null_org_from_record_version.py
    ./bouy exec app python scripts/backfill_null_org_from_record_version.py --apply
    ./bouy run-script --aws --prod scripts/backfill_null_org_from_record_version.py
    ./bouy run-script --aws --prod scripts/backfill_null_org_from_record_version.py --apply
    # staged rollout:
    ./bouy run-script --aws --prod scripts/backfill_null_org_from_record_version.py --max-rows 50 --apply
    # reverse a run:
    ./bouy run-script --aws --prod scripts/backfill_null_org_from_record_version.py --undo-run-id <uuid> --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import uuid
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Human-curated tiers that must never be overwritten by an automated backfill
# (kept in sync with app/validator/scoring.py:HUMAN_VERIFIED_SOURCES).
_HUMAN_VERIFIED = ("admin", "source", "claimed")


# Append-only audit table. Created lazily on first --apply (CREATE TABLE
# IF NOT EXISTS) so this script ships without a cross-repo migration — same
# pattern as dedup_run_audit / the Write API's ingest_audit (per CLAUDE.md).
_AUDIT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS org_backfill_audit (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    location_id UUID NOT NULL,
    old_organization_id UUID,
    new_organization_id UUID NOT NULL,
    source_version_num INTEGER,
    action TEXT NOT NULL DEFAULT 'org_fill'
        CHECK (action IN ('org_fill', 'undo')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_org_backfill_audit_run_id
    ON org_backfill_audit(run_id);
"""


def ensure_audit_table(db: Session) -> None:
    """Create `org_backfill_audit` on first --apply if absent (idempotent)."""
    db.execute(text(_AUDIT_TABLE_DDL))


def check_haarrrvest_freshness(db: Session, *, max_age_hours: int = 12) -> bool:
    """Verify a recent `record_version` row exists (HAARRRvest publishes one
    per export). A stale newest row means the latest known-good rollback
    target is stale. Heuristic pre-flight — the real safety net is a manual
    Aurora snapshot (see CLAUDE.md runbook). Mirrors the dedup script's check.
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
    return not (result is None or result[0] is None)


def candidate_sql() -> str:
    """SQL selecting (location_id, recovered org, source version) for every
    recoverable NULL-org canonical row.

    A LATERAL subquery picks the highest-`version_num` location version with a
    non-empty `organization_id`; the `record_version (record_id, version_num)`
    unique index makes each lookup an indexed scan. The JOIN to `organization`
    drops orgs that no longer exist (stale FK), and the `verified_by` guard
    excludes human-curated rows.

    Type note: `location.id`/`organization.id` are varchar but
    `record_version.record_id` is uuid, so the LATERAL casts the single outer
    `l.id::uuid` (index on `rv.record_id` stays usable; all location ids are
    valid uuids). The org join is varchar=text, no cast needed.
    """
    return """
    SELECT l.id AS location_id,
           lo.org_id AS recovered_org_id,
           lo.version_num AS source_version_num
    FROM location l
    CROSS JOIN LATERAL (
        SELECT rv.data->>'organization_id' AS org_id,
               rv.version_num
        FROM record_version rv
        WHERE rv.record_id = l.id::uuid
          AND rv.record_type = 'location'
          AND COALESCE(rv.data->>'organization_id', '') <> ''
        ORDER BY rv.version_num DESC
        LIMIT 1
    ) lo
    JOIN organization o ON o.id = lo.org_id
    WHERE l.organization_id IS NULL
      AND l.is_canonical = TRUE
      AND (l.verified_by IS NULL OR l.verified_by NOT IN :human_verified)
    ORDER BY l.id
    """


def find_candidates(db: Session) -> list[dict[str, Any]]:
    """Return all recoverable NULL-org canonical rows (deterministic order)."""
    rows = db.execute(
        text(candidate_sql()).bindparams(bindparam("human_verified", expanding=True)),
        {"human_verified": list(_HUMAN_VERIFIED)},
    ).fetchall()
    return [
        {
            "location_id": str(r.location_id),
            "recovered_org_id": str(r.recovered_org_id),
            "source_version_num": (
                int(r.source_version_num) if r.source_version_num is not None else None
            ),
        }
        for r in rows
    ]


def total_null_org_canonical(db: Session) -> int:
    """Count all NULL-org canonical rows (recoverable or not) for diagnostics."""
    row = db.execute(
        text(
            """
            SELECT COUNT(*) FROM location
            WHERE organization_id IS NULL AND is_canonical = TRUE
            """
        )
    ).first()
    if row is None:
        raise RuntimeError(
            "null-org count returned no row — COUNT always returns one, so the "
            "query failed to execute. Check DB connectivity before retrying."
        )
    return int(row[0])


def _log_audit(
    db: Session,
    *,
    run_id: str,
    location_id: str,
    old_org: str | None,
    new_org: str,
    source_version_num: int | None,
    action: str = "org_fill",
) -> None:
    """Append one audit row BEFORE the mutation, so a failed mutation rolls the
    audit row back with it inside the same savepoint."""
    db.execute(
        text(
            """
            INSERT INTO org_backfill_audit (
                run_id, location_id, old_organization_id,
                new_organization_id, source_version_num, action
            )
            VALUES (:run_id, :location_id, :old_org, :new_org, :ver, :action)
            """
        ),
        {
            "run_id": run_id,
            "location_id": location_id,
            "old_org": old_org,
            "new_org": new_org,
            "ver": source_version_num,
            "action": action,
        },
    )


def fill_org(db: Session, candidate: dict[str, Any], run_id: str) -> bool:
    """Fill one location's org link (guarded). Returns True if a row changed.

    The UPDATE re-checks `organization_id IS NULL` and the `verified_by` guard,
    so a row that gained an org or human curation between candidate selection
    and now is left untouched (rowcount 0)."""
    loc_id = candidate["location_id"]
    new_org = candidate["recovered_org_id"]
    _log_audit(
        db,
        run_id=run_id,
        location_id=loc_id,
        old_org=None,
        new_org=new_org,
        source_version_num=candidate["source_version_num"],
    )
    result = db.execute(
        text(
            """
            UPDATE location
            SET organization_id = :new_org
            WHERE id = :loc_id
              AND organization_id IS NULL
              AND is_canonical = TRUE
              AND (verified_by IS NULL OR verified_by NOT IN :human_verified)
            """
        ).bindparams(bindparam("human_verified", expanding=True)),
        {
            "new_org": new_org,
            "loc_id": loc_id,
            "human_verified": list(_HUMAN_VERIFIED),
        },
    )
    return result.rowcount > 0


def undo_run(db: Session, run_id: str, apply: bool) -> int:
    """Reverse a backfill run: re-NULL only the rows that still hold the org
    this run wrote AND are still not human-curated (so a human edit made after
    the backfill is never clobbered). Returns the count reverted (or that would
    be reverted in dry-run)."""
    audit_rows = db.execute(
        text(
            """
            SELECT location_id, new_organization_id
            FROM org_backfill_audit
            WHERE run_id = :run_id AND action = 'org_fill'
            """
        ),
        {"run_id": run_id},
    ).fetchall()
    if not audit_rows:
        logger.warning("No 'org_fill' audit rows for run_id=%s", run_id)
        return 0

    reverted = 0
    for ar in audit_rows:
        loc_id = str(ar.location_id)
        org = str(ar.new_organization_id)
        result = db.execute(
            text(
                """
                UPDATE location
                SET organization_id = NULL
                WHERE id = :loc_id
                  AND organization_id = :org
                  AND (verified_by IS NULL OR verified_by NOT IN :human_verified)
                """
            ).bindparams(bindparam("human_verified", expanding=True)),
            {"loc_id": loc_id, "org": org, "human_verified": list(_HUMAN_VERIFIED)},
        )
        if result.rowcount > 0:
            reverted += 1
            if apply:
                _log_audit(
                    db,
                    run_id=run_id,
                    location_id=loc_id,
                    old_org=org,
                    new_org=org,
                    source_version_num=None,
                    action="undo",
                )
    return reverted


def _dump_sample(db: Session, candidates: list[dict[str, Any]], n: int) -> None:
    """Print N random candidates' before-state for the operator to eyeball.
    Dry-run only — never commits."""
    sample = random.sample(candidates, min(n, len(candidates)))  # noqa: S311
    for cand in sample:
        row = db.execute(
            text(
                """
                SELECT id, name, organization_id, confidence_score,
                       verified_by, is_canonical
                FROM location WHERE id = :id
                """
            ),
            {"id": cand["location_id"]},
        ).first()
        org = db.execute(
            text("SELECT id, name FROM organization WHERE id = :id"),
            {"id": cand["recovered_org_id"]},
        ).first()
        payload = {
            "location": dict(row._mapping) if row else None,
            "would_set_org": dict(org._mapping) if org else cand["recovered_org_id"],
            "source_version_num": cand["source_version_num"],
        }
        print(json.dumps(payload, default=str, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Commit changes (default: dry-run)."
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help=(
            "Cap the number of rows touched (staged rollout: 50, then 500, then "
            "full). Candidates are processed in stable id order so a re-run "
            "with the same cap touches the same rows."
        ),
    )
    parser.add_argument(
        "--dry-run-sample",
        type=int,
        default=0,
        help="Print N random candidates' before-state (dry-run only).",
    )
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help="Skip the HAARRRvest freshness pre-flight (emergencies only).",
    )
    parser.add_argument(
        "--undo-run-id",
        type=str,
        default=None,
        help="Reverse a prior run by its run_id instead of running a backfill.",
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        # ---- Undo path ----
        if args.undo_run_id:
            if args.apply:
                ensure_audit_table(db)
                db.commit()
            reverted = undo_run(db, args.undo_run_id, args.apply)
            if args.apply:
                db.commit()
                logger.info(
                    "UNDO committed for run_id=%s: %d rows re-NULLed",
                    args.undo_run_id,
                    reverted,
                )
            else:
                logger.info(
                    "UNDO dry-run for run_id=%s: %d rows WOULD be re-NULLed "
                    "(pass --apply to commit)",
                    args.undo_run_id,
                    reverted,
                )
            return 0

        # ---- Backfill path ----
        # Pre-flight: HAARRRvest freshness (apply only; dry-run is harmless).
        if args.apply and not args.skip_freshness_check:
            if not check_haarrrvest_freshness(db):
                logger.error(
                    "Pre-flight failed: no record_version rows in the last 12h. "
                    "The most recent rollback target is stale. Let HAARRRvest "
                    "publish, take a manual Aurora snapshot, or pass "
                    "--skip-freshness-check."
                )
                return 2

        run_id = str(uuid.uuid4())
        logger.info("Run id: %s", run_id)

        total_null = total_null_org_canonical(db)
        candidates = find_candidates(db)
        logger.info(
            "Diagnostic: %d NULL-org canonical rows; %d recoverable from "
            "record_version (%d excluded: no org-carrying version, stale org "
            "FK, or human-curated)",
            total_null,
            len(candidates),
            total_null - len(candidates),
        )

        if not candidates:
            logger.info("Nothing to backfill.")
            return 0

        if not args.apply and args.dry_run_sample > 0:
            _dump_sample(db, candidates, args.dry_run_sample)

        if args.max_rows is not None:
            candidates = candidates[: args.max_rows]
            logger.info("Capped to first %d candidates via --max-rows", len(candidates))

        if args.apply:
            ensure_audit_table(db)
            db.commit()

        filled = 0
        skipped = 0
        failed = 0
        for cand in candidates:
            if not args.apply:
                filled += 1  # dry-run: count what WOULD be filled
                continue
            # Per-row savepoint so one failure doesn't roll back the run.
            savepoint = db.begin_nested()
            try:
                if fill_org(db, cand, run_id):
                    filled += 1
                else:
                    skipped += 1  # raced: gained org or human curation
                savepoint.commit()
            except Exception as e:
                savepoint.rollback()
                failed += 1
                logger.warning(
                    "fill_failed location_id=%s error=%s",
                    cand["location_id"],
                    e,
                )

        if args.apply:
            db.commit()
            logger.info(
                "APPLY committed (run_id=%s): filled=%d skipped=%d failed=%d",
                run_id,
                filled,
                skipped,
                failed,
            )
        else:
            logger.info(
                "DRY-RUN: %d rows WOULD be filled (pass --apply to commit)",
                filled,
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
