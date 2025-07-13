-- Service Offerings
--
-- This query provides detailed information about services offered by organizations,
-- including descriptions, eligibility requirements, and application processes.
--
-- Use this as a Metabase model for understanding what services are available.

SELECT
    s.id AS service_id,
    s.name AS service_name,
    s.alternate_name,
    s.description AS service_description,
    s.url AS service_url,
    s.email AS service_email,
    s.status,

    -- Organization information
    o.id AS organization_id,
    o.name AS organization_name,

    -- Eligibility information
    s.eligibility_description,
    s.minimum_age,
    s.maximum_age,

    -- Application process
    s.application_process,

    -- Fees information
    s.fees_description,

    -- Phone numbers for this service
    STRING_AGG(DISTINCT p.number, ', ') AS phone_numbers,

    -- Languages offered
    STRING_AGG(DISTINCT lang.name, ', ') AS languages,

    -- Count of locations where this service is offered
    COUNT(DISTINCT sal.location_id) AS location_count,

    -- Last updated
    s.last_modified
FROM
    service s
LEFT JOIN
    organization o ON s.organization_id = o.id
LEFT JOIN
    phone p ON p.service_id = s.id
LEFT JOIN
    language lang ON lang.service_id = s.id
LEFT JOIN
    service_at_location sal ON sal.service_id = s.id
GROUP BY
    s.id, s.name, s.alternate_name, s.description, s.url, s.email, s.status,
    o.id, o.name,
    s.eligibility_description, s.minimum_age, s.maximum_age,
    s.application_process, s.fees_description, s.last_modified
ORDER BY
    o.name, s.name;
