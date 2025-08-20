-- Script to drop all data from food_helpline_org scraper
-- This removes corrupted data with massive state_province values

BEGIN;

-- First, get counts for logging
DO $$
DECLARE
    location_count INTEGER;
    org_count INTEGER;
    service_count INTEGER;
BEGIN
    -- Count affected locations
    SELECT COUNT(DISTINCT l.id) INTO location_count
    FROM location l
    JOIN location_source ls ON ls.location_id = l.id
    WHERE ls.scraper_id = 'food_helpline_org';
    
    -- Count affected organizations
    SELECT COUNT(DISTINCT o.id) INTO org_count
    FROM organization o
    JOIN organization_source os ON os.organization_id = o.id
    WHERE os.scraper_id = 'food_helpline_org';
    
    -- Count affected services
    SELECT COUNT(DISTINCT s.id) INTO service_count
    FROM service s
    JOIN service_source ss ON ss.service_id = s.id
    WHERE ss.scraper_id = 'food_helpline_org';
    
    RAISE NOTICE 'About to delete data from food_helpline_org scraper:';
    RAISE NOTICE '  Locations: %', location_count;
    RAISE NOTICE '  Organizations: %', org_count;
    RAISE NOTICE '  Services: %', service_count;
END $$;

-- Delete addresses associated with affected locations
DELETE FROM address
WHERE location_id IN (
    SELECT DISTINCT l.id
    FROM location l
    JOIN location_source ls ON ls.location_id = l.id
    WHERE ls.scraper_id = 'food_helpline_org'
);

-- Delete phones associated with affected locations
DELETE FROM phone
WHERE location_id IN (
    SELECT DISTINCT l.id
    FROM location l
    JOIN location_source ls ON ls.location_id = l.id
    WHERE ls.scraper_id = 'food_helpline_org'
);

-- Delete phones associated with affected organizations
DELETE FROM phone
WHERE organization_id IN (
    SELECT DISTINCT o.id
    FROM organization o
    JOIN organization_source os ON os.organization_id = o.id
    WHERE os.scraper_id = 'food_helpline_org'
);

-- Delete service_at_location records
DELETE FROM service_at_location
WHERE location_id IN (
    SELECT DISTINCT l.id
    FROM location l
    JOIN location_source ls ON ls.location_id = l.id
    WHERE ls.scraper_id = 'food_helpline_org'
);

-- Delete service_at_location records for affected services
DELETE FROM service_at_location
WHERE service_id IN (
    SELECT DISTINCT s.id
    FROM service s
    JOIN service_source ss ON ss.service_id = s.id
    WHERE ss.scraper_id = 'food_helpline_org'
);

-- Delete schedules for affected services
DELETE FROM schedule
WHERE service_id IN (
    SELECT DISTINCT s.id
    FROM service s
    JOIN service_source ss ON ss.service_id = s.id
    WHERE ss.scraper_id = 'food_helpline_org'
);

-- Delete languages for affected locations
DELETE FROM language
WHERE location_id IN (
    SELECT DISTINCT l.id
    FROM location l
    JOIN location_source ls ON ls.location_id = l.id
    WHERE ls.scraper_id = 'food_helpline_org'
);

-- Delete accessibility records
DELETE FROM accessibility
WHERE location_id IN (
    SELECT DISTINCT l.id
    FROM location l
    JOIN location_source ls ON ls.location_id = l.id
    WHERE ls.scraper_id = 'food_helpline_org'
);

-- Delete the source records
DELETE FROM location_source WHERE scraper_id = 'food_helpline_org';
DELETE FROM organization_source WHERE scraper_id = 'food_helpline_org';
DELETE FROM service_source WHERE scraper_id = 'food_helpline_org';

-- Delete orphaned services (those with no source records left)
DELETE FROM service
WHERE id IN (
    SELECT s.id
    FROM service s
    LEFT JOIN service_source ss ON ss.service_id = s.id
    WHERE ss.service_id IS NULL
);

-- Delete orphaned locations (those with no source records left)
-- Must be done before organizations due to foreign key constraint
DELETE FROM location
WHERE id IN (
    SELECT l.id
    FROM location l
    LEFT JOIN location_source ls ON ls.location_id = l.id
    WHERE ls.location_id IS NULL
);

-- Delete orphaned organizations (those with no source records left)
-- Must be done after locations due to foreign key constraint
DELETE FROM organization
WHERE id IN (
    SELECT o.id
    FROM organization o
    LEFT JOIN organization_source os ON os.organization_id = o.id
    WHERE os.organization_id IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM location l WHERE l.organization_id = o.id
    )
);

-- Final counts
DO $$
DECLARE
    location_count INTEGER;
    org_count INTEGER;
    address_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO location_count
    FROM location l
    WHERE EXISTS (
        SELECT 1 FROM location_source ls 
        WHERE ls.location_id = l.id 
        AND ls.scraper_id = 'food_helpline_org'
    );
    
    SELECT COUNT(*) INTO org_count
    FROM organization o
    WHERE EXISTS (
        SELECT 1 FROM organization_source os 
        WHERE os.organization_id = o.id 
        AND os.scraper_id = 'food_helpline_org'
    );
    
    SELECT COUNT(*) INTO address_count
    FROM address
    WHERE LENGTH(state_province) > 100;
    
    RAISE NOTICE 'After deletion:';
    RAISE NOTICE '  Remaining food_helpline_org locations: %', location_count;
    RAISE NOTICE '  Remaining food_helpline_org organizations: %', org_count;
    RAISE NOTICE '  Remaining corrupted addresses (>100 chars): %', address_count;
END $$;

COMMIT;