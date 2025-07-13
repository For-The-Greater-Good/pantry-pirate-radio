-- Add is_canonical column to location table
ALTER TABLE location
ADD COLUMN is_canonical BOOLEAN DEFAULT FALSE;
-- Update existing locations to be canonical
UPDATE location
SET is_canonical = TRUE;
-- Create location_source table
CREATE TABLE location_source (
    id character varying(250) PRIMARY KEY,
    location_id character varying(250) NOT NULL REFERENCES location(id),
    scraper_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    location_type VARCHAR(50) DEFAULT 'physical',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(location_id, scraper_id)
);
-- Create index on location_source for faster lookups
CREATE INDEX location_source_location_id_idx ON location_source(location_id);
CREATE INDEX location_source_scraper_id_idx ON location_source(scraper_id);
-- Create organization_source table
CREATE TABLE organization_source (
    id character varying(250) PRIMARY KEY,
    organization_id character varying(250) NOT NULL REFERENCES organization(id),
    scraper_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    website VARCHAR(255),
    email VARCHAR(255),
    year_incorporated INTEGER,
    legal_status VARCHAR(50),
    tax_status VARCHAR(50),
    tax_id VARCHAR(50),
    uri VARCHAR(255),
    parent_organization_id character varying(250) REFERENCES organization(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(organization_id, scraper_id)
);
-- Create index on organization_source for faster lookups
CREATE INDEX organization_source_organization_id_idx ON organization_source(organization_id);
CREATE INDEX organization_source_scraper_id_idx ON organization_source(scraper_id);
-- Create service_source table
CREATE TABLE service_source (
    id character varying(250) PRIMARY KEY,
    service_id character varying(250) NOT NULL REFERENCES service(id),
    scraper_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    organization_id character varying(250) REFERENCES organization(id),
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(service_id, scraper_id)
);
-- Create index on service_source for faster lookups
CREATE INDEX service_source_service_id_idx ON service_source(service_id);
CREATE INDEX service_source_scraper_id_idx ON service_source(scraper_id);
-- Add source_id column to record_version table
ALTER TABLE record_version
ADD COLUMN source_id character varying(250);
-- Create index on record_version for faster lookups
CREATE INDEX record_version_source_id_idx ON record_version(source_id);
-- Create a view for merged location data with source attribution
CREATE OR REPLACE VIEW location_merged_view AS
SELECT l.id,
    l.name,
    l.description,
    l.latitude,
    l.longitude,
    l.location_type,
    json_object_agg(
        ls.scraper_id,
        json_build_object(
            'id',
            ls.id,
            'name',
            ls.name,
            'description',
            ls.description,
            'latitude',
            ls.latitude,
            'longitude',
            ls.longitude
        )
    ) AS source_data,
    json_object_agg(
        'name',
        CASE
            WHEN l.name = ls.name THEN ls.scraper_id
            ELSE NULL
        END
    ) FILTER (
        WHERE l.name = ls.name
    ) AS field_sources
FROM location l
    JOIN location_source ls ON l.id = ls.location_id
WHERE l.is_canonical = TRUE
GROUP BY l.id,
    l.name,
    l.description,
    l.latitude,
    l.longitude,
    l.location_type;
-- Create a function to update the canonical location when source records change
CREATE OR REPLACE FUNCTION update_canonical_location() RETURNS TRIGGER AS $$ BEGIN -- This is a placeholder for the merging logic
    -- In a real implementation, this would apply the merging strategy
    -- to update the canonical record based on all source records
    -- The MergeStrategy class will handle the actual merging of data
    -- We don't update any timestamp here since the location table doesn't have an updated_at column
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- Create a trigger to update the canonical record when source records change
CREATE TRIGGER update_canonical_location_trigger
AFTER
INSERT
    OR
UPDATE ON location_source FOR EACH ROW EXECUTE FUNCTION update_canonical_location();