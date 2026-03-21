-- Migration script to add human update tracking and audit trail
-- Part of the Tightbeam integration for field staff location management
--
-- Design: Human corrections create new location_source rows for provenance
-- (scraper_id='human_update'). The canonical location, address, and phone tables
-- are updated in place. Soft-deletes set validation_status='rejected'.
-- Every mutation is recorded in the change_audit table with full provenance.

-- 1. Extend location_source for human update tracking
ALTER TABLE location_source ADD COLUMN IF NOT EXISTS confidence_score INTEGER DEFAULT 50;
ALTER TABLE location_source ADD COLUMN IF NOT EXISTS validation_status TEXT;
ALTER TABLE location_source ADD COLUMN IF NOT EXISTS validation_notes JSONB;
ALTER TABLE location_source ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'scraper';
ALTER TABLE location_source ADD COLUMN IF NOT EXISTS updated_by TEXT;

COMMENT ON COLUMN location_source.confidence_score IS 'Source-level confidence score (0-100). Human updates default to 100.';
COMMENT ON COLUMN location_source.validation_status IS 'Validation status: verified, needs_review, or rejected';
COMMENT ON COLUMN location_source.validation_notes IS 'Structured validation/correction notes';
COMMENT ON COLUMN location_source.source_type IS 'Source type: scraper (default) or human_update';
COMMENT ON COLUMN location_source.updated_by IS 'Identifier for who made the update (API key name, user ID, etc.)';

-- 2. Create indexes for new location_source columns
CREATE INDEX IF NOT EXISTS location_source_source_type_idx ON location_source(source_type);
CREATE INDEX IF NOT EXISTS location_source_validation_status_idx ON location_source(validation_status);

-- 3. Drop the unique constraint on (location_id, scraper_id) to allow multiple human updates
-- Human updates use scraper_id='human_update' and need multiple rows per location
-- We keep the constraint for scraper sources via a partial unique index instead
-- Drop constraint first (which also removes the backing index)
ALTER TABLE location_source DROP CONSTRAINT IF EXISTS location_source_location_id_scraper_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS location_source_scraper_unique_idx
    ON location_source(location_id, scraper_id)
    WHERE source_type = 'scraper' OR source_type IS NULL;

-- 4. Append-only audit trail with full provenance
CREATE TABLE IF NOT EXISTS change_audit (
    id VARCHAR(250) PRIMARY KEY,
    location_id VARCHAR(250) NOT NULL REFERENCES location(id),
    action TEXT NOT NULL CHECK (action IN ('update', 'soft_delete', 'restore', 'create')),
    changed_fields JSONB,
    previous_values JSONB,
    new_values JSONB,
    api_key_id TEXT,
    api_key_name TEXT,
    source_ip TEXT,
    user_agent TEXT,
    caller_context JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE change_audit IS 'Append-only audit trail for all tightbeam mutations. Never delete rows.';
COMMENT ON COLUMN change_audit.caller_context IS 'Flexible caller identity: {slack_user_id, cognito_sub, channel_id, ...}';

-- 5. Create indexes for change_audit
CREATE INDEX IF NOT EXISTS change_audit_location_idx ON change_audit(location_id);
CREATE INDEX IF NOT EXISTS change_audit_created_idx ON change_audit(created_at);
CREATE INDEX IF NOT EXISTS change_audit_api_key_idx ON change_audit(api_key_id);

-- 6. Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 09-human-updates.sql completed successfully';
    RAISE NOTICE 'Extended location_source with confidence_score, validation_status, source_type, updated_by';
    RAISE NOTICE 'Created change_audit table for append-only provenance tracking';
END $$;
