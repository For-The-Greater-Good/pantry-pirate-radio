-- Migration script to fix race conditions in reconciler matching
-- This addresses https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/6

-- 1. Add unique constraints to prevent duplicate canonical records

-- Organization name normalization function for consistent matching
CREATE OR REPLACE FUNCTION normalize_organization_name(name TEXT) RETURNS TEXT AS $$
BEGIN
    -- Normalize organization names for consistent matching
    -- Remove extra whitespace, convert to lowercase, handle common variations
    RETURN LOWER(TRIM(REGEXP_REPLACE(name, '\s+', ' ', 'g')));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Add normalized name column and unique constraint for organizations
ALTER TABLE organization 
ADD COLUMN IF NOT EXISTS normalized_name TEXT;

-- Update existing records with normalized names
UPDATE organization 
SET normalized_name = normalize_organization_name(name) 
WHERE normalized_name IS NULL;

-- Make normalized_name NOT NULL
ALTER TABLE organization 
ALTER COLUMN normalized_name SET NOT NULL;

-- Add unique constraint on normalized organization name
ALTER TABLE organization 
ADD CONSTRAINT organization_normalized_name_unique 
UNIQUE (normalized_name);

-- Create index for faster organization lookups
CREATE INDEX IF NOT EXISTS organization_normalized_name_idx 
ON organization(normalized_name);

-- 2. Location coordinate constraints and spatial indexing

-- Add spatial index for location coordinates (if not exists from PostGIS setup)
CREATE INDEX IF NOT EXISTS location_coordinates_idx 
ON location USING gist(point(longitude, latitude));

-- Add constraint to ensure canonical locations have coordinates
ALTER TABLE location 
ADD CONSTRAINT location_canonical_coordinates_check 
CHECK (is_canonical = FALSE OR (latitude IS NOT NULL AND longitude IS NOT NULL));

-- Create function for location coordinate matching with tolerance
CREATE OR REPLACE FUNCTION location_coordinates_match(
    lat1 NUMERIC, lon1 NUMERIC, 
    lat2 NUMERIC, lon2 NUMERIC, 
    tolerance NUMERIC DEFAULT 0.0001
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN ABS(lat1 - lat2) < tolerance AND ABS(lon1 - lon2) < tolerance;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 3. Service constraints for name + organization uniqueness

-- Add unique constraint for service name + organization combination
-- This allows same service name under different organizations
ALTER TABLE service 
ADD CONSTRAINT service_name_organization_unique 
UNIQUE (name, organization_id);

-- Create index for faster service lookups
CREATE INDEX IF NOT EXISTS service_name_organization_idx 
ON service(name, organization_id);

-- 4. Add retry configuration table for managing constraint violation retries

CREATE TABLE IF NOT EXISTS reconciler_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert default retry configuration
INSERT INTO reconciler_config (key, value, description) VALUES
    ('max_retry_attempts', '3', 'Maximum number of retry attempts for constraint violations'),
    ('retry_base_delay_ms', '100', 'Base delay in milliseconds between retries'),
    ('retry_backoff_multiplier', '2.0', 'Exponential backoff multiplier for retries'),
    ('location_tolerance', '0.0001', 'Default coordinate tolerance for location matching (≈11m)')
ON CONFLICT (key) DO NOTHING;

-- 5. Create advisory lock functions for complex operations

-- Function to acquire advisory lock for organization operations
CREATE OR REPLACE FUNCTION acquire_organization_lock(org_name TEXT) RETURNS BIGINT AS $$
DECLARE
    lock_id BIGINT;
BEGIN
    -- Create deterministic lock ID from normalized organization name
    lock_id := abs(hashtext(normalize_organization_name(org_name)));
    PERFORM pg_advisory_lock(lock_id);
    RETURN lock_id;
END;
$$ LANGUAGE plpgsql;

-- Function to release advisory lock
CREATE OR REPLACE FUNCTION release_organization_lock(lock_id BIGINT) RETURNS VOID AS $$
BEGIN
    PERFORM pg_advisory_unlock(lock_id);
END;
$$ LANGUAGE plpgsql;

-- Function to acquire advisory lock for location operations (using coordinates)
CREATE OR REPLACE FUNCTION acquire_location_lock(lat NUMERIC, lon NUMERIC) RETURNS BIGINT AS $$
DECLARE
    lock_id BIGINT;
    coord_hash TEXT;
BEGIN
    -- Create deterministic lock ID from coordinates (rounded to tolerance)
    coord_hash := ROUND(lat, 4)::TEXT || ',' || ROUND(lon, 4)::TEXT;
    lock_id := abs(hashtext(coord_hash));
    PERFORM pg_advisory_lock(lock_id);
    RETURN lock_id;
END;
$$ LANGUAGE plpgsql;

-- Function to release location advisory lock
CREATE OR REPLACE FUNCTION release_location_lock(lock_id BIGINT) RETURNS VOID AS $$
BEGIN
    PERFORM pg_advisory_unlock(lock_id);
END;
$$ LANGUAGE plpgsql;

-- 6. Add triggers to automatically update normalized_name

-- Trigger function to update normalized_name on organization changes
CREATE OR REPLACE FUNCTION update_organization_normalized_name() RETURNS TRIGGER AS $$
BEGIN
    NEW.normalized_name := normalize_organization_name(NEW.name);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for organization name normalization
DROP TRIGGER IF EXISTS organization_normalize_name_trigger ON organization;
CREATE TRIGGER organization_normalize_name_trigger
    BEFORE INSERT OR UPDATE OF name ON organization
    FOR EACH ROW
    EXECUTE FUNCTION update_organization_normalized_name();

-- 7. Add constraint violation monitoring table

CREATE TABLE IF NOT EXISTS reconciler_constraint_violations (
    id SERIAL PRIMARY KEY,
    constraint_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    operation VARCHAR(20) NOT NULL, -- 'INSERT', 'UPDATE'
    conflicting_data JSONB,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Index for monitoring queries
CREATE INDEX IF NOT EXISTS reconciler_violations_created_at_idx 
ON reconciler_constraint_violations(created_at);

CREATE INDEX IF NOT EXISTS reconciler_violations_resolved_idx 
ON reconciler_constraint_violations(resolved, created_at);

-- 8. Performance optimization: Add missing indexes for foreign keys

-- These indexes improve performance of ON CONFLICT operations
CREATE INDEX IF NOT EXISTS location_source_location_scraper_idx 
ON location_source(location_id, scraper_id);

CREATE INDEX IF NOT EXISTS organization_source_org_scraper_idx 
ON organization_source(organization_id, scraper_id);

CREATE INDEX IF NOT EXISTS service_source_service_scraper_idx 
ON service_source(service_id, scraper_id);

-- Add index for service organization lookups
CREATE INDEX IF NOT EXISTS service_organization_id_idx 
ON service(organization_id) 
WHERE organization_id IS NOT NULL;

-- 9. Add function to clean up old constraint violation logs

CREATE OR REPLACE FUNCTION cleanup_old_constraint_violations(retention_days INTEGER DEFAULT 30) RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM reconciler_constraint_violations 
    WHERE created_at < NOW() - INTERVAL '1 day' * retention_days
    AND resolved = TRUE;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Schedule cleanup function to run periodically (can be called from application)
COMMENT ON FUNCTION cleanup_old_constraint_violations IS 
'Cleans up resolved constraint violations older than specified days. Call periodically from application.';