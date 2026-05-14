"""Reverse a `scripts/dedupe_near_duplicate_locations.py --apply` run.

Reads `dedup_run_audit` filtered by `--run-id` and reverses every
`repoint` and `soft_delete` action by writing the inverse SQL. Per-row
UNIQUE-skip `delete` actions are NOT automatically restored — those
rows are gone from the live DB and need Aurora PITR (or a HAARRRvest
SQL dump replay). For those, the script prints a per-row recovery
ticket (table, id, full original payload) so an operator knows
exactly what to manually restore.

Dry-run by default. Pass `--apply` to commit the undo.

Usage:
    ./bouy exec app python scripts/undo_dedup_run.py --run-id <uuid>
    ./bouy exec app python scripts/undo_dedup_run.py --run-id <uuid> --apply

Audit-table schema is documented in
`scripts/dedupe_near_duplicate_locations.py::_AUDIT_TABLE_DDL`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def fetch_audit_rows(db: Session, run_id: str) -> list[dict[str, Any]]:
    """Pull every audit row for a run, ordered DESC by id.

    Reversing in DESC order (most-recent-first) matters when a single
    row was repointed twice in a run — restoring to the second-most-
    recent state first leaves us back at the original.
    """
    rows = db.execute(
        text(
            """
            SELECT id, run_id, cluster_id, survivor_id, duplicate_id,
                   table_name, row_id, action, old_value, new_value
            FROM dedup_run_audit
            WHERE run_id = :run_id
            ORDER BY id DESC
            """
        ),
        {"run_id": run_id},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


def reverse_repoint(db: Session, row: dict[str, Any], apply: bool) -> bool:
    """Reverse a repoint: set the FK column back to its `old_value`."""
    if not row["old_value"] or not isinstance(row["old_value"], dict):
        logger.warning(
            "audit_row id=%s missing old_value — cannot reverse repoint",
            row["id"],
        )
        return False
    fk_col, old_fk = next(iter(row["old_value"].items()))
    table = row["table_name"]
    # Defense in depth: only allow identifiers that match the
    # CHILD_TABLES list in the forward script. The audit table is
    # internal so the risk is low, but a manual edit there shouldn't
    # let arbitrary SQL execute.
    allowed_tables = {
        "location_source",
        "address",
        "phone",
        "schedule",
        "service_at_location",
        "accessibility",
        "contact",
        "language",
    }
    if table not in allowed_tables:
        logger.error(
            "audit_row id=%s references unknown table %r — refusing to reverse",
            row["id"],
            table,
        )
        return False
    if fk_col != "location_id":
        # Same defense: only the one expected FK column.
        logger.error(
            "audit_row id=%s repoints unexpected column %r — refusing",
            row["id"],
            fk_col,
        )
        return False
    if not apply:
        return True
    result = db.execute(
        text(
            f"UPDATE {table} SET {fk_col} = :old_fk "  # noqa: S608  # nosec B608 - identifier validated above
            f"WHERE id = :row_id"
        ),
        {"old_fk": old_fk, "row_id": row["row_id"]},
    )
    return (result.rowcount or 0) > 0


def reverse_soft_delete(db: Session, row: dict[str, Any], apply: bool) -> bool:
    """Reverse a soft_delete: set is_canonical back to TRUE."""
    if not apply:
        return True
    result = db.execute(
        text(
            "UPDATE location SET is_canonical = TRUE "
            "WHERE id = :id AND is_canonical = FALSE"
        ),
        {"id": row["row_id"]},
    )
    return (result.rowcount or 0) > 0


def print_recovery_ticket(row: dict[str, Any]) -> None:
    """Print the full payload of an unreversible (deleted) row so an
    operator can restore it from Aurora PITR or a HAARRRvest dump."""
    ticket = {
        "audit_id": row["id"],
        "table": row["table_name"],
        "row_id": row["row_id"],
        "survivor_id": str(row["survivor_id"]),
        "duplicate_id": (
            str(row["duplicate_id"]) if row["duplicate_id"] else None
        ),
        "deleted_payload": row["old_value"],
    }
    print(
        "RECOVERY_TICKET "
        + json.dumps(ticket, default=str)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        required=True,
        help="UUID of the dedupe run to reverse (from the original run's log).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the undo. Default is dry-run.",
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        audit_rows = fetch_audit_rows(db, args.run_id)
        if not audit_rows:
            logger.warning(
                "No audit rows for run_id=%s — either the run didn't "
                "happen, never reached --apply, or the table was wiped.",
                args.run_id,
            )
            return 1

        repoints = [r for r in audit_rows if r["action"] == "repoint"]
        soft_deletes = [r for r in audit_rows if r["action"] == "soft_delete"]
        deletes = [r for r in audit_rows if r["action"] == "delete"]

        logger.info(
            "Run %s: %d repoints, %d soft_deletes, %d deletes",
            args.run_id,
            len(repoints),
            len(soft_deletes),
            len(deletes),
        )

        repointed = 0
        for row in repoints:
            if reverse_repoint(db, row, args.apply):
                repointed += 1
        logger.info(
            "Repoint reversals: %d/%d (%s)",
            repointed,
            len(repoints),
            "applied" if args.apply else "dry-run",
        )

        undeleted = 0
        for row in soft_deletes:
            if reverse_soft_delete(db, row, args.apply):
                undeleted += 1
        logger.info(
            "Soft-delete reversals: %d/%d (%s)",
            undeleted,
            len(soft_deletes),
            "applied" if args.apply else "dry-run",
        )

        # Hard DELETEs are not automatically reversible. Emit a
        # recovery ticket per row so operators can act on them.
        for row in deletes:
            print_recovery_ticket(row)
        if deletes:
            logger.warning(
                "%d UNIQUE-skip DELETEs are NOT automatically reversible. "
                "RECOVERY_TICKET lines above carry the full row payload — "
                "restore via Aurora PITR or HAARRRvest SQL dump.",
                len(deletes),
            )

        if args.apply:
            db.commit()
            logger.info("COMMITTED undo for run_id=%s", args.run_id)
        else:
            db.rollback()
            logger.info(
                "DRY RUN — no changes committed (re-run with --apply)"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
