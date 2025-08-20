-- Migration: Fix overly restrictive organization name constraint
-- Issue #382: Allow organizations with same name in different geographic locations
-- 
-- Problem: The unique constraint on normalized_name prevents legitimate organizations
-- like "Salvation Army" or "Food Bank" from existing in multiple cities.
-- 
-- Solution: Remove the unique constraint and implement proximity-based matching
-- to prevent duplicates at the same location while allowing branches in different areas.

-- Drop the overly restrictive unique constraint
-- This allows organizations with the same name to exist in different locations
ALTER TABLE organization DROP CONSTRAINT IF EXISTS organization_normalized_name_unique;

-- Keep the index for query performance
-- The index organization_normalized_name_idx already exists and will remain

-- Create function for proximity-based organization matching
-- This function finds organizations with the same normalized name
-- that have locations within a specified proximity threshold
CREATE OR REPLACE FUNCTION find_matching_organization(
    org_name TEXT,
    check_lat NUMERIC,
    check_lon NUMERIC,
    proximity_threshold NUMERIC DEFAULT 0.01  -- Default ~0.7 miles
) RETURNS UUID AS $$
DECLARE
    matched_org_id UUID;
BEGIN
    -- Return NULL if no coordinates provided
    IF check_lat IS NULL OR check_lon IS NULL THEN
        RETURN NULL;
    END IF;

    -- Find organizations with same normalized name that have locations within proximity
    -- Using strict proximity: both lat and lon must be within threshold
    SELECT DISTINCT o.id INTO matched_org_id
    FROM organization o
    JOIN location l ON l.organization_id = o.id::varchar
    WHERE o.normalized_name = normalize_organization_name(org_name)
    AND ABS(l.latitude - check_lat) < proximity_threshold
    AND ABS(l.longitude - check_lon) < proximity_threshold
    LIMIT 1;
    
    RETURN matched_org_id;
END;
$$ LANGUAGE plpgsql;

-- Add comment to explain the change
COMMENT ON TABLE organization IS 'Organizations providing services. Same-named organizations can exist in different geographic locations (e.g., Food Bank in NYC and LA are separate entities). Deduplication is handled through location proximity matching rather than name uniqueness.';

-- Add comment on the function
COMMENT ON FUNCTION find_matching_organization IS 'Finds an organization with the same normalized name that has a location within the proximity threshold (default 0.01 degrees ~0.7 miles). Returns NULL if no match found, allowing creation of new organization for that location.';