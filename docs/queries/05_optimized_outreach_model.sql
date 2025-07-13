-- Optimized Comprehensive Outreach Model with Performance Indexes
--
-- This file contains:
-- 1. Index definitions to improve query performance
-- 2. An optimized query for the comprehensive outreach model
--
-- These optimizations focus on improving join performance and address handling

-- =============================================
-- PART 1: INDEX DEFINITIONS
-- =============================================

-- Primary Indexes (Highest Impact)
-- These address the most critical join paths

-- 1. Create index on location.organization_id
-- This speeds up the critical join between location and organization
CREATE INDEX IF NOT EXISTS idx_location_organization_id ON location(organization_id);

-- 2. Create index on address.location_id
-- This speeds up address lookups by location
CREATE INDEX IF NOT EXISTS idx_address_location_id ON address(location_id);

-- 3. Create index on location.is_canonical
-- This speeds up the WHERE filter on canonical locations
CREATE INDEX IF NOT EXISTS idx_location_is_canonical ON location(is_canonical);

-- 4. Create composite index on service_at_location (location_id, service_id)
-- This speeds up joins to service_at_location table from both sides
CREATE INDEX IF NOT EXISTS idx_service_at_location_composite ON service_at_location(location_id, service_id);

-- 5. Create index on service.organization_id
-- This speeds up service lookups by organization
CREATE INDEX IF NOT EXISTS idx_service_organization_id ON service(organization_id);

-- Secondary Indexes (Medium Impact)
-- These improve performance for related tables

-- 6. Create indexes on schedule to speed up joins from three tables
CREATE INDEX IF NOT EXISTS idx_schedule_service_id ON schedule(service_id);
CREATE INDEX IF NOT EXISTS idx_schedule_location_id ON schedule(location_id);
CREATE INDEX IF NOT EXISTS idx_schedule_service_at_location_id ON schedule(service_at_location_id);

-- 7. Create indexes for phone lookups
CREATE INDEX IF NOT EXISTS idx_phone_organization_id ON phone(organization_id);
CREATE INDEX IF NOT EXISTS idx_phone_location_id ON phone(location_id);

-- 8. Create indexes for contact lookups
CREATE INDEX IF NOT EXISTS idx_contact_organization_id ON contact(organization_id);
CREATE INDEX IF NOT EXISTS idx_contact_location_id ON contact(location_id);

-- 9. Create index for language table
CREATE INDEX IF NOT EXISTS idx_language_service_id ON language(service_id);
CREATE INDEX IF NOT EXISTS idx_language_location_id ON language(location_id);
CREATE INDEX IF NOT EXISTS idx_language_phone_id ON language(phone_id);

-- Performance Optimizations for Complex Joins
-- These address the remaining join paths

-- 10. Create indexes for service relationships
CREATE INDEX IF NOT EXISTS idx_service_area_service_id ON service_area(service_id);
CREATE INDEX IF NOT EXISTS idx_service_area_service_at_location_id ON service_area(service_at_location_id);
CREATE INDEX IF NOT EXISTS idx_required_document_service_id ON required_document(service_id);
CREATE INDEX IF NOT EXISTS idx_accessibility_location_id ON accessibility(location_id);

-- Run ANALYZE to update PostgreSQL statistics after creating indexes
ANALYZE;

-- =============================================
-- PART 2: OPTIMIZED QUERY
-- =============================================

-- Enhanced Comprehensive Outreach Model with PostGIS and Properly Joined Addresses
-- This query is optimized to use the indexes defined above and properly handle addresses

SELECT
    -- Organization Information
    o.id AS organization_id,
    o.name AS organization_name,
    o.alternate_name AS organization_alternate_name,
    o.description AS organization_description,
    o.email AS organization_email,
    o.website AS organization_website,
    o.legal_status,
    o.year_incorporated,
    o.tax_status,
    o.tax_id,
    o.logo AS organization_logo,
    o.uri AS organization_uri,
    o.parent_organization_id,

    -- Location Information
    l.id AS location_id,
    l.name AS location_name,
    l.alternate_name AS location_alternate_name,
    l.description AS location_description,
    l.latitude,
    l.longitude,
    l.location_type,
    l.transportation,
    l.external_identifier AS location_external_id,
    l.external_identifier_type AS location_external_id_type,
    l.url AS location_url,

    -- Address Information - Direct Selection to Ensure Inclusion
    a.id AS address_id,
    a.attention,
    a.address_1,
    a.address_2,
    a.city,
    a.region,
    a.state_province,
    a.postal_code,
    a.country,
    a.address_type,

    -- Alternative Address Aggregation Approach
    -- This ensures we capture all addresses for a location
    COALESCE(
        (SELECT
            STRING_AGG(
                addr.address_1 ||
                CASE WHEN addr.address_2 IS NOT NULL AND addr.address_2 != '' THEN ', ' || addr.address_2 ELSE '' END ||
                ', ' || addr.city || ', ' || addr.state_province || ' ' || addr.postal_code ||
                CASE WHEN addr.country != 'US' THEN ', ' || addr.country ELSE '' END,
                '; '
            )
        FROM
            address addr
        WHERE
            addr.location_id = l.id),
        ''
    ) AS complete_addresses,

    -- PostGIS Geometry
    ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326) AS location_geom,

    -- Phone Information
    STRING_AGG(DISTINCT p.number ||
        CASE WHEN p.extension IS NOT NULL THEN ' x' || p.extension::text ELSE '' END ||
        CASE WHEN p.type IS NOT NULL THEN ' (' || p.type || ')' ELSE '' END,
        ', ') AS phone_numbers,

    -- Contact Information
    STRING_AGG(
        DISTINCT
        COALESCE(c.name, '') ||
        CASE WHEN c.title IS NOT NULL THEN ' (' || c.title || ')' ELSE '' END ||
        CASE WHEN c.department IS NOT NULL THEN ', ' || c.department ELSE '' END ||
        CASE WHEN c.email IS NOT NULL THEN ': ' || c.email ELSE '' END,
        '; '
    ) FILTER (WHERE c.name IS NOT NULL OR c.email IS NOT NULL) AS contacts,

    -- Service Information
    COUNT(DISTINCT s.id) AS service_count,
    STRING_AGG(DISTINCT s.name, '; ') AS services,
    STRING_AGG(DISTINCT s.description, '; ') FILTER (WHERE s.description IS NOT NULL) AS service_descriptions,

    -- Schedule Information
    STRING_AGG(
        DISTINCT
        CASE
            WHEN sch.byday IS NOT NULL THEN
                sch.byday ||
                CASE
                    WHEN sch.opens_at IS NOT NULL AND sch.closes_at IS NOT NULL
                    THEN ': ' || sch.opens_at::text || ' - ' || sch.closes_at::text
                    ELSE ''
                END
            ELSE
                COALESCE(sch.description, '')
        END,
        '; '
    ) FILTER (WHERE sch.byday IS NOT NULL OR sch.description IS NOT NULL) AS operating_hours,

    -- Language Information
    STRING_AGG(DISTINCT lang.name, ', ') FILTER (WHERE lang.name IS NOT NULL) AS languages,

    -- Accessibility Information
    STRING_AGG(DISTINCT acc.description, '; ') FILTER (WHERE acc.description IS NOT NULL) AS accessibility_features,

    -- Service Area Information
    STRING_AGG(DISTINCT sa.name, '; ') FILTER (WHERE sa.name IS NOT NULL) AS service_areas,

    -- Required Document Information
    STRING_AGG(DISTINCT rd.document, '; ') FILTER (WHERE rd.document IS NOT NULL) AS required_documents,

    -- Organization Identifier Information
    STRING_AGG(DISTINCT oi.identifier_type || ': ' || oi.identifier, '; ')
        FILTER (WHERE oi.identifier IS NOT NULL) AS organization_identifiers,

    -- Funding Information
    STRING_AGG(DISTINCT f.source, '; ') FILTER (WHERE f.source IS NOT NULL) AS funding_sources,

    -- Cost Option Information
    STRING_AGG(
        DISTINCT
        co.option ||
        CASE WHEN co.amount IS NOT NULL THEN ' (' || co.amount::text ||
            CASE WHEN co.currency IS NOT NULL THEN ' ' || co.currency ELSE '' END || ')'
        ELSE '' END,
        '; '
    ) FILTER (WHERE co.option IS NOT NULL) AS cost_options

FROM
    organization o
-- Use LEFT JOIN to ensure we get all organizations even without locations
LEFT JOIN
    location l ON l.organization_id = o.id
-- Use LEFT JOIN to get addresses, one row per address
LEFT JOIN
    address a ON a.location_id = l.id
LEFT JOIN
    phone p ON (p.organization_id = o.id OR p.location_id = l.id)
LEFT JOIN
    contact c ON (c.organization_id = o.id OR c.location_id = l.id)
LEFT JOIN
    service s ON s.organization_id = o.id
LEFT JOIN
    service_at_location sal ON sal.service_id = s.id AND (sal.location_id = l.id OR l.id IS NULL)
LEFT JOIN
    schedule sch ON (sch.service_id = s.id OR sch.location_id = l.id OR sch.service_at_location_id = sal.id)
LEFT JOIN
    language lang ON (lang.service_id = s.id OR lang.location_id = l.id OR lang.phone_id = p.id)
LEFT JOIN
    accessibility acc ON acc.location_id = l.id
LEFT JOIN
    service_area sa ON (sa.service_id = s.id OR sa.service_at_location_id = sal.id)
LEFT JOIN
    required_document rd ON rd.service_id = s.id
LEFT JOIN
    organization_identifier oi ON oi.organization_id = o.id
LEFT JOIN
    funding f ON (f.organization_id = o.id OR f.service_id = s.id)
LEFT JOIN
    cost_option co ON co.service_id = s.id

WHERE
    (l.is_canonical IS NULL OR l.is_canonical = TRUE) -- Only include canonical locations
    -- Add any additional filters as needed
    -- Example: AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL -- Only include locations with coordinates
    -- Example: AND ST_DWithin(ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326)::geography, ST_SetSRID(ST_MakePoint(-122.4194, 37.7749), 4326)::geography, 10000) -- Within 10km of San Francisco

GROUP BY
    o.id, o.name, o.alternate_name, o.description, o.email, o.website, o.legal_status, o.year_incorporated,
    o.tax_status, o.tax_id, o.logo, o.uri, o.parent_organization_id,
    l.id, l.name, l.alternate_name, l.description, l.latitude, l.longitude, l.location_type, l.transportation,
    l.external_identifier, l.external_identifier_type, l.url,
    a.id, a.attention, a.address_1, a.address_2, a.city, a.region, a.state_province, a.postal_code, a.country, a.address_type

ORDER BY
    o.name, l.name;

-- =============================================
-- PART 3: USAGE EXAMPLES
-- =============================================

-- Example 1: Filter by geographic area (within 5km of downtown San Francisco)
/*
SELECT * FROM (
    -- Insert the main query here
) AS outreach_data
WHERE location_geom IS NOT NULL
AND ST_DWithin(
    location_geom::geography,
    ST_SetSRID(ST_MakePoint(-122.4194, 37.7749), 4326)::geography,
    5000  -- 5km radius
);
*/

-- Example 2: Filter by service type
/*
SELECT * FROM (
    -- Insert the main query here
) AS outreach_data
WHERE services ILIKE '%food%' OR services ILIKE '%meal%';
*/

-- Example 3: Filter by operating hours (places open on Monday)
/*
SELECT * FROM (
    -- Insert the main query here
) AS outreach_data
WHERE operating_hours ILIKE '%MO%';
*/

-- Example 4: Find organizations with accessibility features
/*
SELECT * FROM (
    -- Insert the main query here
) AS outreach_data
WHERE accessibility_features IS NOT NULL;
*/
