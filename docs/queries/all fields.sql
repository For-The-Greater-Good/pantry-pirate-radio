SELECT
    o.id as org_id, o.name as org_name, o.description as org_description,
    s.id as service_id, s.name as service_name, s.description as service_description,
    l.id as location_id, l.name as location_name, l.description as location_description,
    l.latitude, l.longitude,
    sal.id as service_at_location_id, sal.description as service_at_location_description,
    a.address_1, a.address_2, a.city, a.state_province, a.postal_code,
    p.number as phone_number, p.extension, p.type as phone_type,
    acc.description as accessibility_description,
    sch.opens_at, sch.closes_at, sch.byday as schedule_days,
    rv.version_num, rv.created_at as version_created_at, rv.created_by as version_created_by
FROM organization o
LEFT JOIN service s ON s.organization_id = o.id
LEFT JOIN service_at_location sal ON sal.service_id = s.id
LEFT JOIN location l ON l.id = sal.location_id
LEFT JOIN address a ON a.location_id = l.id
LEFT JOIN phone p ON (p.organization_id = o.id OR p.service_id = s.id OR
                     p.location_id = l.id OR p.service_at_location_id = sal.id)
LEFT JOIN accessibility acc ON acc.location_id = l.id
LEFT JOIN schedule sch ON (sch.service_id = s.id OR sch.location_id = l.id OR
                          sch.service_at_location_id = sal.id)
LEFT JOIN record_version rv ON (rv.record_id::text = o.id OR rv.record_id::text = s.id OR
                               rv.record_id::text = l.id OR rv.record_id::text = sal.id)
ORDER BY o.name, s.name, l.name;