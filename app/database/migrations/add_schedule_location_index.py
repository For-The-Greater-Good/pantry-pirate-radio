#!/usr/bin/env python3
"""Migration: add schedule_location_id_idx for /api/v1/map/search.

The map/search endpoint does a LATERAL join into `schedule` per row in
the bbox-filtered location set. Without this index that LATERAL
re-scans the entire schedule table (~58k rows) per location, which
makes a small NYC-bbox map query hit ~15M buffer reads and time out at
the API Gateway 30s ceiling. With the index the same query runs in
well under 500ms (verified via EXPLAIN ANALYZE on prod, 2026-05-13).

Partial because ~42% of schedule rows have NULL location_id (those
rows attach to a service_id instead) and never qualify for this
lookup; indexing them just wastes space.

Uses CREATE INDEX CONCURRENTLY so the build doesn't take a table lock
on live prod traffic. CONCURRENTLY can't run inside a transaction
block, so we open a dedicated raw asyncpg connection and execute it
outside SQLAlchemy's transactional wrapper.

Re-runnable: IF NOT EXISTS makes this safe on environments where the
index has already been added (e.g. fresh envs initialized from
init-scripts/15-schedule-location-index.sql).
"""

from __future__ import annotations

import asyncio
import logging
import os

import asyncpg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


CREATE_INDEX_SQL = """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS schedule_location_id_idx
    ON public.schedule(location_id)
    WHERE location_id IS NOT NULL
"""

VERIFY_SQL = """
    SELECT indexname
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'schedule'
      AND indexname = 'schedule_location_id_idx'
"""


def _to_asyncpg_dsn(database_url: str) -> str:
    """Strip SQLAlchemy driver prefix; asyncpg wants a plain libpq URL."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )


async def create_index(database_url: str) -> None:
    dsn = _to_asyncpg_dsn(database_url)
    # CONCURRENTLY requires autocommit; asyncpg's default connection is
    # already non-transactional outside an explicit `async with conn.transaction()`.
    conn = await asyncpg.connect(dsn)
    try:
        logger.info("Creating schedule_location_id_idx (CONCURRENTLY)...")
        await conn.execute(CREATE_INDEX_SQL)
        logger.info("Index creation issued; verifying...")
        row = await conn.fetchrow(VERIFY_SQL)
        if row:
            logger.info("Verified: %s exists", row["indexname"])
        else:
            logger.error("Verification failed: schedule_location_id_idx not found")
            raise RuntimeError("index missing after CREATE INDEX returned success")
    finally:
        await conn.close()


async def _main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL environment variable not set")
    await create_index(database_url)


if __name__ == "__main__":
    asyncio.run(_main())
