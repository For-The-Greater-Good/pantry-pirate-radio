-- Comprehensive Outreach Model with PostGIS and Complete Address Handling
--
-- This query combines organization information, location details, addresses, operating schedules,
-- contact information, and all related data into a single comprehensive model with
-- spatial capabilities for outreach efforts.
--
-- Prerequisites: Run the index creation statements from 05_optimized_outreach_model.sql first

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

    -- Organization Scraper Information
    STRING_AGG(DISTINCT os.scraper_id, ', ') AS organization_scrapers,
    COUNT(DISTINCT os.scraper_id) AS organization_scraper_count,
    STRING_AGG(DISTINCT os.id, ', ') AS organization_source_ids,
    MAX(os.updated_at) AS organization_last_updated,
    MIN(os.created_at) AS organization_first_created,
    COUNT(DISTINCT rv.id) FILTER (WHERE rv.source_id = os.id) AS organization_version_count,

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

    -- Location Scraper Information
    STRING_AGG(DISTINCT ls.scraper_id, ', ') AS location_scrapers,
    COUNT(DISTINCT ls.scraper_id) AS location_scraper_count,
    STRING_AGG(DISTINCT ls.id, ', ') AS location_source_ids,
    MAX(ls.updated_at) AS location_last_updated,
    MIN(ls.created_at) AS location_first_created,
    COUNT(DISTINCT rv.id) FILTER (WHERE rv.source_id = ls.id) AS location_version_count,

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

    -- Complete Formatted Address
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

    -- Service Scraper Information
    STRING_AGG(DISTINCT ss.scraper_id, ', ') AS service_scrapers,
    COUNT(DISTINCT ss.scraper_id) AS service_scraper_count,
    STRING_AGG(DISTINCT ss.id, ', ') AS service_source_ids,
    MAX(ss.updated_at) AS service_last_updated,
    MIN(ss.created_at) AS service_first_created,
    COUNT(DISTINCT rv.id) FILTER (WHERE rv.source_id = ss.id) AS service_version_count,

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
    ) FILTER (WHERE co.option IS NOT NULL) AS cost_options,

    -- Overall Source Information
    STRING_AGG(DISTINCT
        CASE
            WHEN os.scraper_id IS NOT NULL THEN 'Organization: ' || os.scraper_id
            WHEN ls.scraper_id IS NOT NULL THEN 'Location: ' || ls.scraper_id
            WHEN ss.scraper_id IS NOT NULL THEN 'Service: ' || ss.scraper_id
        END,
        '; '
    ) FILTER (WHERE os.scraper_id IS NOT NULL OR ls.scraper_id IS NOT NULL OR ss.scraper_id IS NOT NULL) AS all_data_sources

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
-- Add source tables to get scraper information
LEFT JOIN
    organization_source os ON os.organization_id = o.id
LEFT JOIN
    location_source ls ON ls.location_id = l.id
LEFT JOIN
    service_source ss ON ss.service_id = s.id
LEFT JOIN
    record_version rv ON (rv.source_id = os.id OR rv.source_id = ls.id OR rv.source_id = ss.id)

WHERE
    (l.is_canonical IS NULL OR l.is_canonical = TRUE) -- Only include canonical locations

GROUP BY
    o.id, o.name, o.alternate_name, o.description, o.email, o.website, o.legal_status, o.year_incorporated,
    o.tax_status, o.tax_id, o.logo, o.uri, o.parent_organization_id,
    l.id, l.name, l.alternate_name, l.description, l.latitude, l.longitude, l.location_type, l.transportation,
    l.external_identifier, l.external_identifier_type, l.url,
    a.id, a.attention, a.address_1, a.address_2, a.city, a.region, a.state_province, a.postal_code, a.country, a.address_type

ORDER BY
    o.name, l.name;
