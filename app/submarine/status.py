"""Submarine status reporting."""

import structlog
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = structlog.get_logger(__name__)


def get_status() -> dict[str, Any]:
    """Get submarine crawl status summary from the database.

    Returns:
        Dict with counts of crawled locations by status.
    """
    engine = create_engine(settings.DATABASE_URL)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        # Count locations by submarine status
        rows = session.execute(
            text(
                "SELECT submarine_last_status, COUNT(*) "
                "FROM location "
                "WHERE submarine_last_crawled_at IS NOT NULL "
                "GROUP BY submarine_last_status"
            )
        ).fetchall()

        status_counts = {row[0] or "unknown": row[1] for row in rows}

        # Count locations eligible for crawling (have website, not yet crawled)
        eligible = session.execute(
            text(
                "SELECT COUNT(DISTINCT l.id) "
                "FROM location l "
                "JOIN organization o ON l.organization_id = o.id "
                "WHERE o.website IS NOT NULL "
                "AND l.submarine_last_crawled_at IS NULL "
                "AND l.validation_status != 'rejected'"
            )
        ).scalar()

        # Total locations with websites
        total_with_website = session.execute(
            text(
                "SELECT COUNT(DISTINCT l.id) "
                "FROM location l "
                "JOIN organization o ON l.organization_id = o.id "
                "WHERE o.website IS NOT NULL"
            )
        ).scalar()

    return {
        "total_with_website": total_with_website or 0,
        "never_crawled": eligible or 0,
        "by_status": status_counts,
        "enabled": settings.SUBMARINE_ENABLED,
    }
