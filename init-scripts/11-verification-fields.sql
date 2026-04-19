-- Migration script to add verification tracking fields to location table
-- Part of the confidence scoring overhaul for ppr-beacon mini-sites
--
-- Design: Tracks WHO verified a location (auto/admin/source) and WHEN.
-- Source verification (Lighthouse portal) is the gold standard.
-- Admin verification (Helm) is high trust but below source.
-- Automated scoring (pipeline) can set 'auto' at score >= 80.
-- These fields are operational metadata, not HSDS data fields.

-- 1. Add verified_by field to location table.
-- NOTE: 'claimed' was added in 12-claimed-verified-by.sql for the
-- self-service claim flow. Keeping both values here so fresh installs
-- land with the full set without needing a follow-up migration.
ALTER TABLE location
ADD COLUMN IF NOT EXISTS verified_by TEXT
CONSTRAINT location_verified_by_check CHECK (verified_by IN ('auto', 'admin', 'source', 'claimed'));

COMMENT ON COLUMN location.verified_by IS 'Who verified: auto (score>=80), admin (Helm), source (Lighthouse portal), claimed (Lighthouse claimant), NULL (unverified)';

-- 2. Add verified_at timestamp
ALTER TABLE location
ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

COMMENT ON COLUMN location.verified_at IS 'When verification happened (admin edit, portal confirmation, or auto-scoring)';

-- 3. Create indexes for verification queries
CREATE INDEX IF NOT EXISTS location_verified_by_idx
ON location(verified_by)
WHERE verified_by IS NOT NULL;

-- Composite index for the beacon quality gate query
CREATE INDEX IF NOT EXISTS location_beacon_eligible_idx
ON location(confidence_score, verified_by)
WHERE verified_by IN ('admin', 'source', 'claimed') AND confidence_score >= 93;

-- 4. Update location_master view to include verification fields
CREATE OR REPLACE VIEW location_master AS
SELECT
    l.id,
    l.location_type,
    l.url,
    l.organization_id,
    l.name,
    l.alternate_name,
    l.description,
    l.transportation,
    l.latitude,
    l.longitude,
    l.external_identifier,
    l.external_identifier_type,
    l.confidence_score,
    l.validation_notes,
    l.validation_status,
    l.geocoding_source,
    o.name as organization_name,
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    a.country,
    l.verified_by,
    l.verified_at
FROM location l
LEFT JOIN organization o ON l.organization_id = o.id
LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical';

COMMENT ON VIEW location_master IS 'Master view of locations with validation and verification fields for HAARRRvest export';

-- 5. Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 11-verification-fields.sql completed successfully';
    RAISE NOTICE 'Added verified_by and verified_at fields to location table';
    RAISE NOTICE 'Created beacon eligibility index for quality gate queries';
    RAISE NOTICE 'Updated location_master view with verification fields';
END $$;
