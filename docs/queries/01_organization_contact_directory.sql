-- Organization Contact Directory
--
-- This query provides a comprehensive list of organizations with their contact information,
-- including names, descriptions, websites, emails, and phone numbers.
--
-- Use this as a Metabase model for creating call sheets for outreach to food organizations.

SELECT
    o.id AS organization_id,
    o.name AS organization_name,
    o.alternate_name,
    o.description,
    o.email AS organization_email,
    o.website,
    o.legal_status,
    o.year_incorporated,

    -- Aggregate phone numbers for the organization
    STRING_AGG(DISTINCT p.number, ', ' ORDER BY p.number) AS phone_numbers,

    -- Count of services offered
    COUNT(DISTINCT s.id) AS service_count,

    -- Count of locations
    COUNT(DISTINCT l.id) AS location_count,

    -- Most recent update
    MAX(s.last_modified) AS last_updated
FROM
    organization o
LEFT JOIN
    phone p ON p.organization_id = o.id
LEFT JOIN
    service s ON s.organization_id = o.id
LEFT JOIN
    service_at_location sal ON sal.service_id = s.id
LEFT JOIN
    location l ON l.id = sal.location_id OR l.organization_id = o.id
GROUP BY
    o.id, o.name, o.alternate_name, o.description, o.email, o.website, o.legal_status, o.year_incorporated
ORDER BY
    o.name;
