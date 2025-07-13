-- Location Details with Addresses and Operating Schedules
--
-- This query provides detailed information about physical locations including
-- complete address information, coordinates, accessibility details, and operating schedules.
--
-- Use this as a Metabase model for creating call sheets with location information and operating hours.

SELECT
    l.id AS location_id,
    l.name AS location_name,
    l.description AS location_description,
    l.latitude,
    l.longitude,

    -- Organization information
    o.id AS organization_id,
    o.name AS organization_name,

    -- Address information
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    a.country,

    -- Transportation information
    l.transportation,

    -- Accessibility information
    STRING_AGG(DISTINCT acc.description, '; ') AS accessibility_features,

    -- Phone numbers for this location
    STRING_AGG(DISTINCT p.number, ', ') AS phone_numbers,

    -- Count of services at this location
    COUNT(DISTINCT sal.service_id) AS service_count,

    -- Operating schedule information
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

    -- Schedule validity
    MIN(sch.valid_from) AS schedule_valid_from,
    MAX(sch.valid_to) AS schedule_valid_to,

    -- Schedule notes
    STRING_AGG(DISTINCT sch.notes, '; ') FILTER (WHERE sch.notes IS NOT NULL) AS schedule_notes
FROM
    location l
LEFT JOIN
    organization o ON l.organization_id = o.id
LEFT JOIN
    address a ON a.location_id = l.id
LEFT JOIN
    accessibility acc ON acc.location_id = l.id
LEFT JOIN
    phone p ON p.location_id = l.id
LEFT JOIN
    service_at_location sal ON sal.location_id = l.id
LEFT JOIN
    schedule sch ON sch.location_id = l.id OR sch.service_at_location_id = sal.id
WHERE
    l.location_type = 'physical'
    AND l.is_canonical = TRUE
GROUP BY
    l.id, l.name, l.description, l.latitude, l.longitude,
    o.id, o.name,
    a.address_1, a.address_2, a.city, a.state_province, a.postal_code, a.country,
    l.transportation
ORDER BY
    o.name, l.name;
