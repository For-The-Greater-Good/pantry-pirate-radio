-- Submarine: track crawl state for adaptive cooldown
-- submarine_last_status values: 'success', 'partial', 'no_data', 'error', 'blocked'
-- Cooldown logic in dispatcher:
--   success/partial → cooldown_success_days (30 days default)
--   no_data/blocked → cooldown_no_data_days (90 days default)
--   error           → cooldown_error_days   (14 days default)

ALTER TABLE location ADD COLUMN IF NOT EXISTS submarine_last_crawled_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE location ADD COLUMN IF NOT EXISTS submarine_last_status VARCHAR(20)
    CHECK (submarine_last_status IN ('success', 'partial', 'no_data', 'error', 'blocked'));

CREATE INDEX IF NOT EXISTS idx_location_submarine_crawled
    ON location(submarine_last_crawled_at)
    WHERE submarine_last_crawled_at IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS location_source_submarine_unique_idx
    ON location_source(location_id, scraper_id)
    WHERE source_type = 'submarine';
