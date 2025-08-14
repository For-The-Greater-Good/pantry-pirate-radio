-- Migration script to add confidence score and validation fields to location table
-- This addresses https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/362
-- Part of the data validation pipeline implementation

-- 1. Add confidence score field to location table
ALTER TABLE location
ADD COLUMN IF NOT EXISTS confidence_score INTEGER DEFAULT 50
CONSTRAINT location_confidence_score_check CHECK (confidence_score >= 0 AND confidence_score <= 100);

COMMENT ON COLUMN location.confidence_score IS 'Data quality confidence score (0-100). Default 50 for neutral confidence.';

-- 2. Add validation notes field (JSONB for flexibility)
ALTER TABLE location
ADD COLUMN IF NOT EXISTS validation_notes JSONB;

COMMENT ON COLUMN location.validation_notes IS 'Structured validation results and notes in JSON format';

-- 3. Add validation status field with enum constraint
ALTER TABLE location
ADD COLUMN IF NOT EXISTS validation_status TEXT
CONSTRAINT location_validation_status_check CHECK (validation_status IN ('verified', 'needs_review', 'rejected'));

COMMENT ON COLUMN location.validation_status IS 'Validation status: verified, needs_review, or rejected';

-- 4. Add geocoding source field to track where coordinates came from
ALTER TABLE location
ADD COLUMN IF NOT EXISTS geocoding_source TEXT;

COMMENT ON COLUMN location.geocoding_source IS 'Source of geocoding: arcgis, google, nominatim, census, original, etc.';

-- 5. Create indexes for better query performance
CREATE INDEX IF NOT EXISTS location_confidence_score_idx
ON location(confidence_score)
WHERE confidence_score IS NOT NULL;

CREATE INDEX IF NOT EXISTS location_validation_status_idx
ON location(validation_status)
WHERE validation_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS location_geocoding_source_idx
ON location(geocoding_source)
WHERE geocoding_source IS NOT NULL;

-- Index for filtering out rejected locations
CREATE INDEX IF NOT EXISTS location_not_rejected_idx
ON location(id)
WHERE validation_status IS NULL OR validation_status != 'rejected';

-- 6. Update existing records with default values (if any exist)
UPDATE location
SET confidence_score = 50
WHERE confidence_score IS NULL;

-- 7. Create or replace HAARRRvest location_master view to include new fields
-- Note: This view is used by HAARRRvest publisher for data export
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
    -- Include organization name for context
    o.name as organization_name,
    -- Include address information if available
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    a.country
FROM location l
LEFT JOIN organization o ON l.organization_id = o.id
LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical'
-- Optionally filter out rejected locations from default view
-- Uncomment the following line to exclude rejected locations by default:
-- WHERE l.validation_status IS NULL OR l.validation_status != 'rejected'
;

COMMENT ON VIEW location_master IS 'Master view of locations with validation fields for HAARRRvest export';

-- 8. Add validation fields to organization table as well (for completeness)
ALTER TABLE organization
ADD COLUMN IF NOT EXISTS confidence_score INTEGER DEFAULT 50
CONSTRAINT organization_confidence_score_check CHECK (confidence_score >= 0 AND confidence_score <= 100);

ALTER TABLE organization
ADD COLUMN IF NOT EXISTS validation_notes JSONB;

ALTER TABLE organization
ADD COLUMN IF NOT EXISTS validation_status TEXT
CONSTRAINT organization_validation_status_check CHECK (validation_status IN ('verified', 'needs_review', 'rejected'));

-- 9. Add validation fields to service table
ALTER TABLE service
ADD COLUMN IF NOT EXISTS confidence_score INTEGER DEFAULT 50
CONSTRAINT service_confidence_score_check CHECK (confidence_score >= 0 AND confidence_score <= 100);

ALTER TABLE service
ADD COLUMN IF NOT EXISTS validation_notes JSONB;

ALTER TABLE service
ADD COLUMN IF NOT EXISTS validation_status TEXT
CONSTRAINT service_validation_status_check CHECK (validation_status IN ('verified', 'needs_review', 'rejected'));

-- 10. Create indexes for organization and service validation fields
CREATE INDEX IF NOT EXISTS organization_confidence_score_idx
ON organization(confidence_score)
WHERE confidence_score IS NOT NULL;

CREATE INDEX IF NOT EXISTS organization_validation_status_idx
ON organization(validation_status)
WHERE validation_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS service_confidence_score_idx
ON service(confidence_score)
WHERE confidence_score IS NOT NULL;

CREATE INDEX IF NOT EXISTS service_validation_status_idx
ON service(validation_status)
WHERE validation_status IS NOT NULL;

-- 11. Create a function to calculate aggregate confidence scores
CREATE OR REPLACE FUNCTION calculate_aggregate_confidence(
    org_confidence INTEGER,
    loc_confidence INTEGER,
    svc_confidence INTEGER
) RETURNS INTEGER AS $$
BEGIN
    -- Calculate weighted average of non-null confidence scores
    -- Organization: 40% weight, Location: 40% weight, Service: 20% weight
    RETURN ROUND(
        (COALESCE(org_confidence * 0.4, 0) + 
         COALESCE(loc_confidence * 0.4, 0) + 
         COALESCE(svc_confidence * 0.2, 0)) /
        NULLIF(
            (CASE WHEN org_confidence IS NOT NULL THEN 0.4 ELSE 0 END +
             CASE WHEN loc_confidence IS NOT NULL THEN 0.4 ELSE 0 END +
             CASE WHEN svc_confidence IS NOT NULL THEN 0.2 ELSE 0 END), 0)
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION calculate_aggregate_confidence IS 'Calculate weighted average confidence score across organization, location, and service';

-- 12. Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 06-validation-fields.sql completed successfully';
    RAISE NOTICE 'Added confidence_score, validation_notes, validation_status, and geocoding_source fields';
    RAISE NOTICE 'Created indexes and updated location_master view for HAARRRvest';
END $$;