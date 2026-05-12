-- Migration: create feeding_america_zip_coverage table.
-- Mirrors app/database/migrations/add_feeding_america_zip_coverage.py so the
-- table exists in every fresh database (including the ephemeral test DB and
-- new dev installs). The Python migration script handles the row-level load
-- from scripts/feeding-america/data/feeding_america_zip_coverage.csv.
--
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS feeding_america_zip_coverage (
    zip          TEXT    NOT NULL,
    fa_org_id    INTEGER NOT NULL,
    fa_org_name  TEXT    NOT NULL,
    PRIMARY KEY (zip, fa_org_id)
);

CREATE INDEX IF NOT EXISTS idx_fa_zip_coverage_org
    ON feeding_america_zip_coverage(fa_org_id);

COMMENT ON TABLE feeding_america_zip_coverage IS
  'ZIP → Feeding America regional food bank crosswalk. Populated from '
  'scripts/feeding-america/data/feeding_america_zip_coverage.csv via '
  'app/database/migrations/add_feeding_america_zip_coverage.py.';

COMMIT;
