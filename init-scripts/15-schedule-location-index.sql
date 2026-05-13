-- Migration: index supporting schedule lookups by location_id.
--
-- The /api/v1/map/search endpoint does a LATERAL join into `schedule`
-- per row in the bbox-filtered location set. Without this index that
-- LATERAL re-scans the entire schedule table (~58k rows) per location,
-- which makes a small NYC-bbox map query hit ~15M buffer reads and
-- time out at the API Gateway 30s ceiling. With the index the same
-- query runs in well under 500ms.
--
-- Partial because ~42% of schedule rows have NULL location_id (the
-- schedule is attached to a service_id instead) and never qualify for
-- this lookup; indexing them just wastes space.
--
-- Idempotent: safe to re-run.

BEGIN;

CREATE INDEX IF NOT EXISTS schedule_location_id_idx
    ON public.schedule(location_id)
    WHERE location_id IS NOT NULL;

COMMIT;
