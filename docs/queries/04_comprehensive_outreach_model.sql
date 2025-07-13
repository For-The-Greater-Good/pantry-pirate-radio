-- Comprehensive Outreach Model
--
-- This query combines organization information, location details, operating schedules,
-- and contact information into a single comprehensive model for outreach efforts.
--
-- Use this as the primary Metabase model for creating call sheets for food organizations.

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

    -- Location Information
    l.id AS location_id,
    l.name AS location_name,
    l.description AS location_description,
    l.latitude,
    l.longitude,
    l.location_type,

    -- Address Information
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    a.country,

    -- Transportation Information
    l.transportation,

    -- Phone Information
    STRING_AGG(DISTINCT p.number, ', ') AS phone_numbers,

    -- Contact Information
    STRING_AGG(
        DISTINCT
        COALESCE(c.name, '') ||
        CASE WHEN c.title IS NOT NULL THEN ' (' || c.title || ')' ELSE '' END ||
        CASE WHEN c.email IS NOT NULL THEN ': ' || c.email ELSE '' END,
        '; '
    ) FILTER (WHERE c.name IS NOT NULL OR c.email IS NOT NULL) AS contacts,

    -- Service Information
    COUNT(DISTINCT s.id) AS service_count,
    STRING_AGG(DISTINCT s.name, '; ') AS services,

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
    ) FILTER (WHERE sch.byday IS NOT NULL OR sch.description IS NOT NULL) AS operating_hours
FROM
    organization o
LEFT JOIN
    location l ON l.organization_id = o.id
LEFT JOIN
    address a ON a.location_id = l.id
LEFT JOIN
    phone p ON p.organization_id = o.id OR p.location_id = l.id
LEFT JOIN
    contact c ON c.organization_id = o.id OR c.location_id = l.id
LEFT JOIN
    service s ON s.organization_id = o.id
LEFT JOIN
    service_at_location sal ON sal.service_id = s.id AND (sal.location_id = l.id OR l.id IS NULL)
LEFT JOIN
    schedule sch ON sch.service_id = s.id OR sch.location_id = l.id OR sch.service_at_location_id = sal.id
GROUP BY
    o.id, o.name, o.alternate_name, o.description, o.email, o.website, o.legal_status, o.year_incorporated,
    l.id, l.name, l.description, l.latitude, l.longitude, l.location_type, l.transportation,
    a.address_1, a.address_2, a.city, a.state_province, a.postal_code, a.country
ORDER BY
    o.name, l.name;
