-- Migration: indexes supporting /api/v1/partners/ptf/locations.
--
-- The PTF list query is expected to be called on every map-pan by the
-- consuming mobile app. Without these indexes the JOINs over location,
-- address, phone, and feeding_america_zip_coverage all fall back to
-- sequential scans, and the SUBSTR(postal_code, 1, 5) join predicate
-- cannot use the FA crosswalk's PK.
--
-- All indexes are conditional (IF NOT EXISTS) so this script is safe
-- to re-run.

BEGIN;

-- 1. JOIN indexes used by every PTF locations request
CREATE INDEX IF NOT EXISTS idx_address_location_id
    ON public.address(location_id);

CREATE INDEX IF NOT EXISTS idx_phone_location_id
    ON public.phone(location_id);

-- 2. Functional index that makes the FA crosswalk JOIN sargable.
-- The query uses SUBSTR(a.postal_code, 1, 5) so the 5-digit prefix can
-- match a zip+4 in the address column. Without this, the planner
-- can't use the feeding_america_zip_coverage(zip) PK index.
CREATE INDEX IF NOT EXISTS idx_address_postal5
    ON public.address ((SUBSTR(postal_code, 1, 5)));

-- 3. Trigram indexes for the `q` text search. ILIKE '%foo%' cannot use
-- a btree; pg_trgm gives sub-10ms typeahead on the full 66k+ location
-- corpus.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_location_name_trgm
    ON public.location USING gin (LOWER(name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_location_alt_name_trgm
    ON public.location USING gin (LOWER(COALESCE(alternate_name, '')) gin_trgm_ops);

-- 4. Partial index covering the WHERE clause shared by both PTF queries:
-- non-rejected, geocoded, not Null Island. Lets the planner skip rows
-- without consulting the main table.
CREATE INDEX IF NOT EXISTS idx_location_ptf_eligible
    ON public.location(id)
    WHERE (validation_status IS NULL OR validation_status != 'rejected')
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND NOT (latitude = 0 AND longitude = 0);

COMMIT;
