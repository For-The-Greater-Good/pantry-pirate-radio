-- Version tracking table for HSDS records
-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Create version tracking table
CREATE TABLE IF NOT EXISTS record_version (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL,
    record_type TEXT NOT NULL,
    version_num INTEGER NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by TEXT,
    UNIQUE (record_id, version_num)
);
-- Create indexes
CREATE INDEX IF NOT EXISTS idx_record_version_record ON record_version(record_id);
CREATE INDEX IF NOT EXISTS idx_record_version_type ON record_version(record_type);
CREATE INDEX IF NOT EXISTS idx_record_version_created ON record_version(created_at);
-- Add comments
COMMENT ON TABLE record_version IS 'Tracks version history for HSDS records';
COMMENT ON COLUMN record_version.id IS 'Unique identifier for version record';
COMMENT ON COLUMN record_version.record_id IS 'ID of the HSDS record being versioned';
COMMENT ON COLUMN record_version.record_type IS 'Type of HSDS record (organization, service, location)';
COMMENT ON COLUMN record_version.version_num IS 'Sequential version number for this record';
COMMENT ON COLUMN record_version.data IS 'Complete record data at this version';
COMMENT ON COLUMN record_version.created_at IS 'When this version was created';
COMMENT ON COLUMN record_version.created_by IS 'What created this version';
-- Create function to get latest version
CREATE OR REPLACE FUNCTION get_latest_version(p_record_id UUID, p_record_type TEXT) RETURNS JSONB LANGUAGE plpgsql AS $func$ BEGIN RETURN (
        SELECT data
        FROM record_version
        WHERE record_id = p_record_id
            AND record_type = p_record_type
        ORDER BY version_num DESC
        LIMIT 1
    );
END;
$func$;
-- Create function to get version history
CREATE OR REPLACE FUNCTION get_version_history(p_record_id UUID, p_record_type TEXT) RETURNS TABLE (
        version_num INTEGER,
        data JSONB,
        created_at TIMESTAMP WITH TIME ZONE,
        created_by TEXT
    ) LANGUAGE plpgsql AS $func$ BEGIN RETURN QUERY
SELECT rv.version_num,
    rv.data,
    rv.created_at,
    rv.created_by
FROM record_version rv
WHERE rv.record_id = p_record_id
    AND rv.record_type = p_record_type
ORDER BY rv.version_num DESC;
END;
$func$;