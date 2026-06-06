-- Migration: federation_log — the append-only verifiable federation log (design §6.2b).
--
-- One row per published activity envelope (HSDS Federation P1). `sequence` is
-- the dense, gapless Merkle leaf index, assigned by the append helper
-- (app/federation/log.py) under an advisory lock scoped to ONLY
-- `SELECT MAX(sequence)+1 -> INSERT -> COMMIT` — never a SERIAL, because a
-- SERIAL gaps on rollback and a gap would break the RFC-6962 tree. `leaf_hash`
-- is the `sha256:` content address of the JCS-canonical envelope (the envelope
-- `id` and the Merkle leaf input); `object_canonical` stores the full envelope
-- so the content address is exactly re-derivable. Append-only: rows are never
-- updated or deleted (retention is archive-to-S3, never destruction — §6.2g).
--
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.federation_log (
    leaf_hash        TEXT PRIMARY KEY,
    sequence         BIGINT      NOT NULL,
    type             TEXT        NOT NULL,
    federation_id    TEXT        NOT NULL,
    object_canonical JSONB       NOT NULL,
    published_at     TIMESTAMPTZ NOT NULL,
    origin_did       TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dense leaf index: UNIQUE so a duplicate sequence can never be committed
-- (defense in depth behind the advisory lock); the index also serves the
-- keyset-pagination + safe-high-water reads on /export.
CREATE UNIQUE INDEX IF NOT EXISTS federation_log_sequence_key
    ON public.federation_log(sequence);

-- history/{federation_id} lookups.
CREATE INDEX IF NOT EXISTS federation_log_federation_id_idx
    ON public.federation_log(federation_id);

COMMIT;
