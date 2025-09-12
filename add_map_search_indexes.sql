-- Indexes for map search performance
-- Run this against the production database to improve search query performance

-- Geographic indexes (if not already present)
CREATE INDEX IF NOT EXISTS idx_location_lat_lng ON location(latitude, longitude) 
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- State search index
CREATE INDEX IF NOT EXISTS idx_address_state ON address(state_province);

-- Confidence score index
CREATE INDEX IF NOT EXISTS idx_location_confidence ON location(confidence_score);

-- Validation status index
CREATE INDEX IF NOT EXISTS idx_location_validation ON location(validation_status);

-- Canonical locations index
CREATE INDEX IF NOT EXISTS idx_location_canonical ON location(is_canonical) 
WHERE is_canonical = true;

-- Full-text search indexes using PostgreSQL GIN indexes
-- These are critical for text search performance

-- Create text search indexes on individual columns
CREATE INDEX IF NOT EXISTS idx_location_name_gin ON location USING gin(to_tsvector('english', COALESCE(name, '')));
CREATE INDEX IF NOT EXISTS idx_location_description_gin ON location USING gin(to_tsvector('english', COALESCE(description, '')));

-- Organization text search
CREATE INDEX IF NOT EXISTS idx_organization_name_gin ON organization USING gin(to_tsvector('english', COALESCE(name, '')));
CREATE INDEX IF NOT EXISTS idx_organization_description_gin ON organization USING gin(to_tsvector('english', COALESCE(description, '')));

-- Address text search
CREATE INDEX IF NOT EXISTS idx_address_address1_gin ON address USING gin(to_tsvector('english', COALESCE(address_1, '')));
CREATE INDEX IF NOT EXISTS idx_address_city_gin ON address USING gin(to_tsvector('english', COALESCE(city, '')));

-- Service names index
CREATE INDEX IF NOT EXISTS idx_service_name_gin ON service USING gin(to_tsvector('english', COALESCE(name, '')));

-- Language names index
CREATE INDEX IF NOT EXISTS idx_language_name ON language(name);

-- Schedule indexes for day filtering
CREATE INDEX IF NOT EXISTS idx_schedule_byday ON schedule(byday);
CREATE INDEX IF NOT EXISTS idx_schedule_times ON schedule(opens_at, closes_at);

-- Relationship indexes for joins
CREATE INDEX IF NOT EXISTS idx_service_at_location_location ON service_at_location(location_id);
CREATE INDEX IF NOT EXISTS idx_service_at_location_service ON service_at_location(service_id);
CREATE INDEX IF NOT EXISTS idx_location_source_location ON location_source(location_id);
CREATE INDEX IF NOT EXISTS idx_location_source_scraper ON location_source(scraper_id);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_location_geo_confidence ON location(latitude, longitude, confidence_score) 
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Phone and organization relationship indexes
CREATE INDEX IF NOT EXISTS idx_phone_location ON phone(location_id);
CREATE INDEX IF NOT EXISTS idx_phone_organization ON phone(organization_id);

-- For counting sources per location
CREATE INDEX IF NOT EXISTS idx_location_source_count ON location_source(location_id, scraper_id);

-- Analyze tables to update statistics after creating indexes
ANALYZE location;
ANALYZE organization;
ANALYZE address;
ANALYZE service;
ANALYZE service_at_location;
ANALYZE location_source;
ANALYZE language;
ANALYZE schedule;
ANALYZE phone;