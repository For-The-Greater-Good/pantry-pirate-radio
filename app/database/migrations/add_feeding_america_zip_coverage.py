#!/usr/bin/env python3
"""Migration: create feeding_america_zip_coverage and load from CSV.

Run inside the app container:
    ./bouy exec app python app/database/migrations/add_feeding_america_zip_coverage.py

Creates the table (idempotent) and loads rows from
scripts/feeding-america/data/feeding_america_zip_coverage.csv. The
table is TRUNCATEd before load so reruns produce a clean state.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CSV_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "feeding-america"
    / "data"
    / "feeding_america_zip_coverage.csv"
)

DDL = [
    """
    CREATE TABLE IF NOT EXISTS feeding_america_zip_coverage (
        zip          TEXT    NOT NULL,
        fa_org_id    INTEGER NOT NULL,
        fa_org_name  TEXT    NOT NULL,
        PRIMARY KEY (zip, fa_org_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fa_zip_coverage_org ON feeding_america_zip_coverage(fa_org_id)",
]

INSERT_CHUNK = 1000


def main() -> None:
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
    logger.info("table and index ensured")

    if not CSV_PATH.exists():
        logger.warning(
            "CSV not found at %s -- table is empty. "
            "Generate it with: python scripts/feeding-america/build_zip_crosswalk.py",
            CSV_PATH,
        )
        return

    with CSV_PATH.open() as f:
        reader = csv.DictReader(f)
        rows = [
            {
                "zip": r["zip"],
                "fa_org_id": int(r["fa_org_id"]),
                "fa_org_name": r["fa_org_name"],
            }
            for r in reader
        ]
    logger.info("read %d rows from %s", len(rows), CSV_PATH)

    insert_stmt = text(
        "INSERT INTO feeding_america_zip_coverage (zip, fa_org_id, fa_org_name) "
        "VALUES (:zip, :fa_org_id, :fa_org_name)"
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE feeding_america_zip_coverage"))
        for offset in range(0, len(rows), INSERT_CHUNK):
            conn.execute(insert_stmt, rows[offset : offset + INSERT_CHUNK])
    logger.info("loaded %d rows into feeding_america_zip_coverage", len(rows))


if __name__ == "__main__":
    main()
