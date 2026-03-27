"""Batch scanner for manual submarine job creation.

Queries the database for locations with website URLs and missing fields,
then enqueues SubmarineJobs. Used by the `./bouy submarine scan` command
for manual control before automatic dispatch is enabled.
"""

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.reconciler.submarine_dispatcher import SubmarineDispatcher

logger = logging.getLogger(__name__)


def scan_and_enqueue(
    limit: int | None = None,
    location_id: str | None = None,
    scraper_id: str | None = None,
) -> dict[str, Any]:
    """Scan DB for locations needing submarine enrichment and enqueue jobs.

    Args:
        limit: Maximum number of jobs to enqueue (None = no limit).
        location_id: Target a specific location ID (overrides other filters).
        scraper_id: Filter to locations produced by this scraper.

    Returns:
        Summary dict with counts of scanned/enqueued/skipped locations.
    """
    engine = create_engine(settings.DATABASE_URL)
    session_factory = sessionmaker(bind=engine)

    enqueued = 0
    skipped = 0
    errors = 0

    with session_factory() as session:
        dispatcher = SubmarineDispatcher(db=session)

        if location_id:
            # Target a specific location
            rows = session.execute(
                text("SELECT l.id, l.organization_id FROM location l WHERE l.id = :id"),
                {"id": location_id},
            ).fetchall()
        else:
            # Build query with optional scraper filter
            params: dict[str, Any] = {}
            if scraper_id:
                base_sql = (
                    "SELECT DISTINCT l.id, l.organization_id "
                    "FROM location l "
                    "JOIN organization o ON l.organization_id = o.id "
                    "JOIN location_source ls ON ls.location_id = l.id "
                    "WHERE o.website IS NOT NULL "
                    "AND l.validation_status != 'rejected' "
                    "AND ls.scraper_id = :scraper_id "
                    "ORDER BY l.id"
                )
                params["scraper_id"] = scraper_id
            else:
                base_sql = (
                    "SELECT DISTINCT l.id, l.organization_id "
                    "FROM location l "
                    "JOIN organization o ON l.organization_id = o.id "
                    "WHERE o.website IS NOT NULL "
                    "AND l.validation_status != 'rejected' "
                    "ORDER BY l.id"
                )
            if limit:
                params["lim"] = int(limit)
                rows = session.execute(
                    text(base_sql + " LIMIT :lim"), params
                ).fetchall()
            else:
                rows = session.execute(text(base_sql), params).fetchall()

        total = len(rows)
        logger.info(f"submarine_scan_started: {total} candidate locations")

        for row in rows:
            loc_id, org_id = row[0], row[1]
            try:
                # Use the dispatcher with SUBMARINE_ENABLED override
                # (scanner works even when auto-dispatch is off)
                result = _dispatch_for_scan(
                    dispatcher, str(loc_id), str(org_id) if org_id else None
                )
                if result:
                    enqueued += 1
                    logger.info(
                        f"submarine_scan_enqueued: location={loc_id}, job={result}"
                    )
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                logger.warning(f"submarine_scan_error: location={loc_id}, error={e}")

    summary: dict[str, Any] = {
        "total_candidates": total,
        "enqueued": enqueued,
        "skipped": skipped,
        "errors": errors,
    }
    if scraper_id:
        summary["scraper_id"] = scraper_id
    logger.info(f"submarine_scan_completed: {summary}")
    return summary


def _dispatch_for_scan(
    dispatcher: SubmarineDispatcher,
    location_id: str,
    organization_id: str | None,
) -> str | None:
    """Dispatch a submarine job from the scanner (bypasses SUBMARINE_ENABLED check).

    The scanner is the manual trigger — it should work even when
    automatic dispatch is disabled.
    """
    return dispatcher.check_and_enqueue(
        location_id=location_id,
        organization_id=organization_id,
        job_metadata={"scraper_id": "scanner"},
        force=True,  # Bypass SUBMARINE_ENABLED for manual scans
    )
