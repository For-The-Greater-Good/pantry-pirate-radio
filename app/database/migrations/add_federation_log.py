#!/usr/bin/env python3
"""Migration: create the federation_log table (HSDS Federation P1, design §6.2b).

The append-only verifiable log. One row per published activity envelope.
`sequence` is the dense, gapless Merkle leaf index assigned by the append helper
(app/federation/log.py) under an advisory lock scoped to ONLY
`SELECT MAX(sequence)+1 -> INSERT -> COMMIT` — NOT a SERIAL, because a SERIAL
gaps on rollback and a gap would break the RFC-6962 tree. `leaf_hash` is the
`sha256:` content address of the JCS-canonical envelope (the envelope `id` and
the Merkle leaf input). `preimage_canonical` stores the EXACT JCS bytes that were
hashed/signed, so the Merkle leaf is re-derived verbatim (a JSONB round-trip
normalizes extreme-magnitude numbers and would break proofs); `object_canonical`
retains the full envelope JSONB for queryability only. Append-only: rows are
never updated or deleted (retention is archive-to-S3, never destruction — §6.2g).

Re-runnable: CREATE ... IF NOT EXISTS makes this safe on environments already
initialized from init-scripts/16-federation-log.sql (fresh envs) — this module
is for applying the table to existing databases that predate it.
"""

from __future__ import annotations

import asyncio
import logging
import os

import asyncpg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS public.federation_log (
        leaf_hash          TEXT PRIMARY KEY,
        sequence           BIGINT      NOT NULL,
        type               TEXT        NOT NULL,
        federation_id      TEXT        NOT NULL,
        object_canonical   JSONB       NOT NULL,
        preimage_canonical BYTEA       NOT NULL,
        published_at       TIMESTAMPTZ NOT NULL,
        origin_did         TEXT        NOT NULL,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

# Upgrade path for databases initialized before preimage_canonical existed
# (federation_log is unreleased, so any such table is empty in practice — the
# SET NOT NULL needs no backfill and keeps the upgraded schema identical to a
# fresh CREATE).
ADD_PREIMAGE_COL_SQL = """
    ALTER TABLE public.federation_log
    ADD COLUMN IF NOT EXISTS preimage_canonical BYTEA
"""
SET_PREIMAGE_NOT_NULL_SQL = """
    ALTER TABLE public.federation_log
    ALTER COLUMN preimage_canonical SET NOT NULL
"""

CREATE_SEQUENCE_IDX_SQL = """
    CREATE UNIQUE INDEX IF NOT EXISTS federation_log_sequence_key
    ON public.federation_log(sequence)
"""

CREATE_FEDERATION_ID_IDX_SQL = """
    CREATE INDEX IF NOT EXISTS federation_log_federation_id_idx
    ON public.federation_log(federation_id)
"""

VERIFY_SQL = """
    SELECT to_regclass('public.federation_log') AS tbl
"""


def _to_asyncpg_dsn(database_url: str) -> str:
    """Strip SQLAlchemy driver prefix; asyncpg wants a plain libpq URL."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )


async def create_table(database_url: str) -> None:
    dsn = _to_asyncpg_dsn(database_url)
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            logger.info("Creating federation_log table + indexes...")
            await conn.execute(CREATE_TABLE_SQL)
            await conn.execute(ADD_PREIMAGE_COL_SQL)
            await conn.execute(SET_PREIMAGE_NOT_NULL_SQL)
            await conn.execute(CREATE_SEQUENCE_IDX_SQL)
            await conn.execute(CREATE_FEDERATION_ID_IDX_SQL)
        row = await conn.fetchrow(VERIFY_SQL)
        if row and row["tbl"]:
            logger.info("Verified: %s exists", row["tbl"])
        else:
            logger.error("Verification failed: federation_log not found")
            raise RuntimeError("federation_log missing after CREATE TABLE returned")
    finally:
        await conn.close()


async def _main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL environment variable not set")
    await create_table(database_url)


if __name__ == "__main__":
    asyncio.run(_main())
