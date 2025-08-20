-- Script to normalize state names to 2-letter codes in the database
-- This fixes entries like "Wisconsin" -> "WI", "Alabama" -> "AL", etc.

BEGIN;

-- Create a temporary mapping table
CREATE TEMP TABLE state_mapping (
    full_name TEXT,
    code CHAR(2)
);

-- Insert all US state mappings
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

-- Also add common variations
INSERT INTO state_mapping (full_name, code) VALUES
    ('WYoming', 'WY'),  -- Seen in logs
    ('British Columbia', NULL),  -- Canadian province, should be removed
    ('District Of Columbia', 'DC'),
    ('U.S. Virgin Islands', 'VI'),
    ('US Virgin Islands', 'VI');

-- Count addresses to be updated
DO $$
DECLARE
    update_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO update_count
    FROM address a
    WHERE LENGTH(a.state_province) > 2
       OR EXISTS (
           SELECT 1 FROM state_mapping sm 
           WHERE LOWER(a.state_province) = LOWER(sm.full_name)
       );
    
    RAISE NOTICE 'Found % addresses that need state normalization', update_count;
END $$;

-- Update addresses with full state names to use 2-letter codes
UPDATE address a
SET state_province = COALESCE(sm.code, 
    CASE 
        -- If it's already a valid 2-letter code, keep it
        WHEN LENGTH(a.state_province) = 2 AND a.state_province ~ '^[A-Z]{2}$' THEN a.state_province
        -- If we can extract a valid 2-letter code from the beginning
        WHEN LENGTH(a.state_province) >= 2 AND SUBSTRING(a.state_province, 1, 2) ~ '^[A-Z]{2}$' 
             AND SUBSTRING(a.state_province, 1, 2) IN (
                 'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',
                 'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
                 'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
                 'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
                 'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY',
                 'DC','PR','VI','GU','AS','MP'
             ) THEN SUBSTRING(a.state_province, 1, 2)
        -- Otherwise, set to empty string (will be handled by geocoding later)
        ELSE ''
    END),
    updated_at = CURRENT_TIMESTAMP
FROM state_mapping sm
WHERE LOWER(a.state_province) = LOWER(sm.full_name)
   OR LENGTH(a.state_province) > 2;

-- Report on remaining invalid states
DO $$
DECLARE
    invalid_count INTEGER;
    empty_count INTEGER;
    valid_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO invalid_count
    FROM address
    WHERE state_province NOT IN (
        'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',
        'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
        'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
        'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
        'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY',
        'DC','PR','VI','GU','AS','MP'
    )
    AND state_province != '';
    
    SELECT COUNT(*) INTO empty_count
    FROM address
    WHERE state_province = '' OR state_province IS NULL;
    
    SELECT COUNT(*) INTO valid_count
    FROM address
    WHERE state_province IN (
        'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',
        'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
        'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
        'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
        'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY',
        'DC','PR','VI','GU','AS','MP'
    );
    
    RAISE NOTICE 'After normalization:';
    RAISE NOTICE '  Valid state codes: %', valid_count;
    RAISE NOTICE '  Invalid state codes: %', invalid_count;
    RAISE NOTICE '  Empty state codes: %', empty_count;
    
    -- Show examples of remaining invalid states
    IF invalid_count > 0 THEN
        RAISE NOTICE 'Examples of remaining invalid states exist (count: %)', invalid_count;
    END IF;
END $$;

-- Clean up
DROP TABLE state_mapping;

COMMIT;