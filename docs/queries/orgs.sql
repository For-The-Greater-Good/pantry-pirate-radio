WITH latest_versions AS (
    SELECT record_id,
           MAX(version_num) as max_version
    FROM record_version
    GROUP BY record_id
),
latest_version_details AS (
    SELECT
        rv.record_id,
        rv.version_num,
        rv.created_at,
        rv.created_by,
        rv.data
    FROM record_version rv
    JOIN latest_versions lv ON
        rv.record_id = lv.record_id AND
        rv.version_num = lv.max_version
),
location_details AS (
    SELECT
        l.id,
        l.name,
        l.description,
        l.latitude,
        l.longitude,
        l.transportation,
        (
            SELECT COALESCE(JSON_AGG(DISTINCT JSONB_BUILD_OBJECT(
                'id', a.id,
                'address_1', a.address_1,
                'address_2', a.address_2,
                'city', a.city,
                'state_province', a.state_province,
                'postal_code', a.postal_code,
                'country', a.country
            )) FILTER (WHERE a.id IS NOT NULL), '[]'::json)
            FROM address a
            WHERE a.location_id = l.id
        ) as addresses,
        (
            SELECT COALESCE(JSON_AGG(DISTINCT JSONB_BUILD_OBJECT(
                'id', acc.id,
                'description', acc.description,
                'details', acc.details,
                'url', acc.url
            )) FILTER (WHERE acc.id IS NOT NULL), '[]'::json)
            FROM accessibility acc
            WHERE acc.location_id = l.id
        ) as accessibility
    FROM location l
)
SELECT
    o.id as org_id,
    o.name as org_name,
    o.description as org_description,
    o.website as org_website,
    o.email as org_email,
    o.year_incorporated,
    o.legal_status,

    -- Aggregate services
    COALESCE(JSON_AGG(DISTINCT JSONB_BUILD_OBJECT(
        'id', s.id,
        'name', s.name,
        'description', s.description,
        'status', s.status
    )) FILTER (WHERE s.id IS NOT NULL), '[]'::json) as services,

    -- Aggregate locations using pre-computed details
    COALESCE(JSON_AGG(DISTINCT JSONB_BUILD_OBJECT(
        'id', ld.id,
        'name', ld.name,
        'description', ld.description,
        'latitude', ld.latitude,
        'longitude', ld.longitude,
        'transportation', ld.transportation,
        'addresses', ld.addresses,
        'accessibility', ld.accessibility
    )) FILTER (WHERE ld.id IS NOT NULL), '[]'::json) as locations,

    -- Aggregate phones
    COALESCE(JSON_AGG(DISTINCT JSONB_BUILD_OBJECT(
        'id', p.id,
        'number', p.number,
        'extension', p.extension,
        'type', p.type
    )) FILTER (WHERE p.id IS NOT NULL), '[]'::json) as phones,

    -- Aggregate schedules
    COALESCE(JSON_AGG(DISTINCT JSONB_BUILD_OBJECT(
        'id', sch.id,
        'opens_at', sch.opens_at,
        'closes_at', sch.closes_at,
        'byday', sch.byday,
        'freq', sch.freq,
        'interval', sch.interval
    )) FILTER (WHERE sch.id IS NOT NULL), '[]'::json) as schedules,

    -- Latest version info from pre-computed details
    lvd.version_num as latest_version_num,
    lvd.created_at as version_created_at,
    lvd.created_by as version_created_by,
    lvd.data as version_data

FROM organization o
LEFT JOIN service s ON s.organization_id = o.id
LEFT JOIN service_at_location sal ON sal.service_id = s.id
LEFT JOIN location_details ld ON ld.id = sal.location_id
LEFT JOIN phone p ON (
    p.organization_id = o.id OR
    p.service_id = s.id OR
    p.location_id = ld.id OR
    p.service_at_location_id = sal.id
)
LEFT JOIN schedule sch ON (
    sch.service_id = s.id OR
    sch.location_id = ld.id OR
    sch.service_at_location_id = sal.id
)
LEFT JOIN latest_version_details lvd ON lvd.record_id::text = o.id
GROUP BY
    o.id,
    o.name,
    o.description,
    o.website,
    o.email,
    o.year_incorporated,
    o.legal_status,
    lvd.version_num,
    lvd.created_at,
    lvd.created_by,
    lvd.data
ORDER BY o.name;