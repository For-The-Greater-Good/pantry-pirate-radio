-- Map search performance indexes
-- This script creates indexes needed for efficient map search functionality

-- Geographic indexes for spatial queries
CREATE INDEX IF NOT EXISTS idx_location_lat_lng 
    ON location(latitude, longitude) 
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Composite index for geo queries with confidence filtering
CREATE INDEX IF NOT EXISTS idx_location_geo_confidence 
    ON location(latitude, longitude, confidence_score) 
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- State search index
CREATE INDEX IF NOT EXISTS idx_address_state 
    ON address(state_province);

-- City search index
CREATE INDEX IF NOT EXISTS idx_address_city 
    ON address(LOWER(city));

-- Confidence score index for quality filtering
CREATE INDEX IF NOT EXISTS idx_location_confidence 
    ON location(confidence_score);

-- Validation status index
CREATE INDEX IF NOT EXISTS idx_location_validation 
    ON location(validation_status);

-- Canonical locations index
CREATE INDEX IF NOT EXISTS idx_location_canonical 
    ON location(is_canonical) 
    WHERE is_canonical = true;

-- Text search indexes using LOWER for case-insensitive searches
-- These match the optimized query patterns
CREATE INDEX IF NOT EXISTS idx_location_name_lower 
    ON location(LOWER(name));

CREATE INDEX IF NOT EXISTS idx_location_description_lower 
    ON location(LOWER(description));

CREATE INDEX IF NOT EXISTS idx_organization_name_lower 
    ON organization(LOWER(name));

CREATE INDEX IF NOT EXISTS idx_organization_description_lower 
    ON organization(LOWER(description));

CREATE INDEX IF NOT EXISTS idx_address_address1_lower 
    ON address(LOWER(address_1));

-- Service and language indexes
CREATE INDEX IF NOT EXISTS idx_service_name_lower 
    ON service(LOWER(name));

CREATE INDEX IF NOT EXISTS idx_language_name_lower 
    ON language(LOWER(name));

-- Schedule indexes for time-based filtering
CREATE INDEX IF NOT EXISTS idx_schedule_byday 
    ON schedule(byday);

CREATE INDEX IF NOT EXISTS idx_schedule_times 
    ON schedule(opens_at, closes_at);

-- Relationship indexes for efficient joins
CREATE INDEX IF NOT EXISTS idx_service_at_location_location 
    ON service_at_location(location_id);

CREATE INDEX IF NOT EXISTS idx_service_at_location_service 
    ON service_at_location(service_id);

CREATE INDEX IF NOT EXISTS idx_location_source_location 
    ON location_source(location_id);

CREATE INDEX IF NOT EXISTS idx_location_source_scraper 
    ON location_source(scraper_id);

-- Composite index for source counting
CREATE INDEX IF NOT EXISTS idx_location_source_count 
    ON location_source(location_id, scraper_id);

-- Phone relationship indexes
CREATE INDEX IF NOT EXISTS idx_phone_location 
    ON phone(location_id) 
    WHERE location_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_phone_organization 
    ON phone(organization_id) 
    WHERE organization_id IS NOT NULL;

-- Language location index
CREATE INDEX IF NOT EXISTS idx_language_location 
    ON language(location_id) 
    WHERE location_id IS NOT NULL;

-- Update table statistics for query planner
ANALYZE location;
ANALYZE organization;
ANALYZE address;
ANALYZE service;
ANALYZE service_at_location;
ANALYZE location_source;
ANALYZE language;
ANALYZE schedule;
ANALYZE phone;