-- Migration: add 'claimed' to location.verified_by allowed values.
-- Part of the self-service claim flow (ppr-lighthouse Part 2).
--
-- 'claimed' sits alongside 'admin' and 'source' as a trusted verification
-- tier. It represents a program representative who verified ownership of
-- a listing via the claim flow (invite, self-verify, or admin-approved
-- manual review). Reconciler-guard treats claimed fields the same as
-- admin/source — scraper updates do not overwrite them.
--
-- Idempotent: safe to re-run.

BEGIN;

-- 1. Replace the CHECK constraint to include 'claimed'.
ALTER TABLE location DROP CONSTRAINT IF EXISTS location_verified_by_check;
ALTER TABLE location
ADD CONSTRAINT location_verified_by_check
CHECK (verified_by IN ('auto', 'admin', 'source', 'claimed'));

COMMENT ON COLUMN location.verified_by IS
  'Who verified: auto (score>=80), admin (Helm), source (Lighthouse portal), claimed (Lighthouse claimant), NULL (unverified)';

-- 2. Extend the beacon-eligible composite index to include claimed, so
-- claimed locations qualify for rendering on beacon pages.
DROP INDEX IF EXISTS location_beacon_eligible_idx;
CREATE INDEX IF NOT EXISTS location_beacon_eligible_idx
ON location(confidence_score, verified_by)
WHERE verified_by IN ('admin', 'source', 'claimed') AND confidence_score >= 93;

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 12-claimed-verified-by.sql completed';
END $$;
