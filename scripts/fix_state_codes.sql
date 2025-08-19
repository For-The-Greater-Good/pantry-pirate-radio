-- Fix state codes in address table to use 2-letter codes
-- This script normalizes full state names to their 2-letter codes

BEGIN;

-- Create temporary mapping table
CREATE TEMP TABLE state_mapping (
    full_name TEXT PRIMARY KEY,
    code VARCHAR(2)
);

-- Insert state mappings
INSERT INTO state_mapping (full_name, code) VALUES
    ('Alabama', 'AL'),
    ('Alaska', 'AK'),
    ('Arizona', 'AZ'),
    ('Arkansas', 'AR'),
    ('California', 'CA'),
    ('Colorado', 'CO'),
    ('Connecticut', 'CT'),
    ('Delaware', 'DE'),
    ('Florida', 'FL'),
    ('Georgia', 'GA'),
    ('Hawaii', 'HI'),
    ('Idaho', 'ID'),
    ('Illinois', 'IL'),
    ('Indiana', 'IN'),
    ('Iowa', 'IA'),
    ('Kansas', 'KS'),
    ('Kentucky', 'KY'),
    ('Louisiana', 'LA'),
    ('Maine', 'ME'),
    ('Maryland', 'MD'),
    ('Massachusetts', 'MA'),
    ('Michigan', 'MI'),
    ('Minnesota', 'MN'),
    ('Mississippi', 'MS'),
    ('Missouri', 'MO'),
    ('Montana', 'MT'),
    ('Nebraska', 'NE'),
    ('Nevada', 'NV'),
    ('New Hampshire', 'NH'),
    ('New Jersey', 'NJ'),
    ('New Mexico', 'NM'),
    ('New York', 'NY'),
    ('North Carolina', 'NC'),
    ('North Dakota', 'ND'),
    ('Ohio', 'OH'),
    ('Oklahoma', 'OK'),
    ('Oregon', 'OR'),
    ('Pennsylvania', 'PA'),
    ('Rhode Island', 'RI'),
    ('South Carolina', 'SC'),
    ('South Dakota', 'SD'),
    ('Tennessee', 'TN'),
    ('Texas', 'TX'),
    ('Utah', 'UT'),
    ('Vermont', 'VT'),
    ('Virginia', 'VA'),
    ('Washington', 'WA'),
    ('West Virginia', 'WV'),
    ('Wisconsin', 'WI'),
    ('Wyoming', 'WY'),
    ('District of Columbia', 'DC'),
    ('Puerto Rico', 'PR'),
    ('Virgin Islands', 'VI'),
    ('Guam', 'GU'),
    ('American Samoa', 'AS'),
    ('Northern Mariana Islands', 'MP');

-- Show what will be updated
SELECT 
    a.state_province AS current_state,
    sm.code AS new_code,
    COUNT(*) AS count
FROM address a
JOIN state_mapping sm ON a.state_province = sm.full_name
GROUP BY a.state_province, sm.code
ORDER BY count DESC;

-- Update addresses with full state names to 2-letter codes
UPDATE address
SET state_province = sm.code
FROM state_mapping sm
WHERE address.state_province = sm.full_name;

-- Show results
SELECT 
    'Updated ' || COUNT(*) || ' addresses from full state names to 2-letter codes' AS result
FROM address
WHERE LENGTH(state_province) = 2;

-- Check for any remaining non-2-letter state codes
SELECT 
    state_province,
    LENGTH(state_province) as length,
    COUNT(*) as count
FROM address
WHERE LENGTH(state_province) != 2
GROUP BY state_province
ORDER BY count DESC
LIMIT 20;

COMMIT;

-- Summary
SELECT 
    'Total addresses' AS metric,
    COUNT(*) AS count
FROM address
UNION ALL
SELECT 
    'Addresses with 2-letter state codes' AS metric,
    COUNT(*) AS count
FROM address
WHERE LENGTH(state_province) = 2
UNION ALL
SELECT 
    'Addresses with non-standard state codes' AS metric,
    COUNT(*) AS count
FROM address
WHERE LENGTH(state_province) != 2;