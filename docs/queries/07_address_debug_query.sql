-- Address Debugging Query
--
-- This query is specifically designed to debug address retrieval issues
-- and ensure that address records are properly returned.

-- First, let's check if there are any addresses in the database at all
SELECT COUNT(*) AS total_address_count FROM address;

-- Next, let's check how many locations have associated addresses
SELECT COUNT(DISTINCT location_id) AS locations_with_addresses FROM address;

-- Now, let's check how many organizations have locations with addresses
SELECT COUNT(DISTINCT o.id) AS orgs_with_addresses
FROM organization o
JOIN location l ON l.organization_id = o.id
JOIN address a ON a.location_id = l.id;

-- Let's examine the address data directly without complex joins
SELECT
    a.id AS address_id,
    a.location_id,
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    a.country,
    a.address_type,
    l.name AS location_name,
    o.name AS organization_name
FROM
    address a
LEFT JOIN
    location l ON a.location_id = l.id
LEFT JOIN
    organization o ON l.organization_id = o.id
LIMIT 20;

-- Now let's try a simplified query that focuses ONLY on returning addresses
-- This removes the GROUP BY clause which might be causing issues
SELECT
    o.id AS organization_id,
    o.name AS organization_name,
    l.id AS location_id,
    l.name AS location_name,
    a.id AS address_id,
    a.address_1,
    a.address_2,
    a.city,
    a.state_province,
    a.postal_code,
    a.country,
    a.address_type
FROM
    address a
JOIN
    location l ON a.location_id = l.id
JOIN
    organization o ON l.organization_id = o.id
WHERE
    (l.is_canonical IS NULL OR l.is_canonical = TRUE)
ORDER BY
    o.name, l.name, a.address_type
LIMIT 100;

-- If the above query returns results but the original doesn't, the issue is likely with:
-- 1. The LEFT JOIN approach (try using INNER JOIN instead)
-- 2. The GROUP BY clause (which might be excluding some addresses)
-- 3. The WHERE clause (which might be filtering out addresses)

-- Here's a revised version of the original query that should fix address retrieval issues:
SELECT
    -- Organization Information
    o.id AS organization_id,
    o.name AS organization_name,
    o.alternate_name AS organization_alternate_name,
    o.description AS organization_description,
    o.email AS organization_email,
    o.website AS organization_website,

    -- Location Information
    l.id AS location_id,
    l.name AS location_name,
    l.description AS location_description,
    l.latitude,
    l.longitude,
    l.location_type,
    l.transportation,

    -- PostGIS Geometry
    ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326) AS location_geom,

    -- Address Information - Direct Selection
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

    -- Formatted Single Address
    a.address_1 ||
    CASE WHEN a.address_2 IS NOT NULL AND a.address_2 != '' THEN ', ' || a.address_2 ELSE '' END ||
    ', ' || a.city || ', ' || a.state_province || ' ' || a.postal_code ||
    CASE WHEN a.country != 'US' THEN ', ' || a.country ELSE '' END AS formatted_address

FROM
    address a
JOIN
    location l ON a.location_id = l.id
JOIN
    organization o ON l.organization_id = o.id
LEFT JOIN
    phone p ON (p.organization_id = o.id OR p.location_id = l.id)
WHERE
    (l.is_canonical IS NULL OR l.is_canonical = TRUE)
ORDER BY
    o.name, l.name, a.address_type;

-- If you need the aggregated fields (all_addresses, phone_numbers), here's a version
-- that uses a different approach to GROUP BY that should preserve all addresses:
SELECT
    -- Organization and Location Info
    o.id AS organization_id,
    o.name AS organization_name,
    l.id AS location_id,
    l.name AS location_name,

    -- Address Info (as JSON array to preserve all addresses)
    jsonb_agg(
        jsonb_build_object(
            'id', a.id,
            'address_1', a.address_1,
            'address_2', a.address_2,
            'city', a.city,
            'state_province', a.state_province,
            'postal_code', a.postal_code,
            'country', a.country,
            'address_type', a.address_type,
            'formatted', a.address_1 ||
                CASE WHEN a.address_2 IS NOT NULL AND a.address_2 != '' THEN ', ' || a.address_2 ELSE '' END ||
                ', ' || a.city || ', ' || a.state_province || ' ' || a.postal_code ||
                CASE WHEN a.country != 'US' THEN ', ' || a.country ELSE '' END
        )
    ) AS addresses,

    -- Phone Numbers
    STRING_AGG(DISTINCT p.number, ', ') AS phone_numbers

FROM
    organization o
JOIN
    location l ON l.organization_id = o.id
JOIN
    address a ON a.location_id = l.id
LEFT JOIN
    phone p ON (p.organization_id = o.id OR p.location_id = l.id)
WHERE
    (l.is_canonical IS NULL OR l.is_canonical = TRUE)
GROUP BY
    o.id, o.name, l.id, l.name
ORDER BY
    o.name, l.name;
