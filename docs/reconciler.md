# Reconciler Service

The reconciler service is responsible for processing HSDS data from LLM outputs and integrating it into the database while maintaining data consistency and versioning. This document describes how the reconciler works and its key components.

## Overview

The reconciler takes completed jobs from the LLM queue, processes their output to extract HSDS entities, and either creates new records or updates existing ones based on matching criteria. It maintains a complete version history of all changes and tracks various metrics about the reconciliation process.

The reconciler now supports source-specific records, allowing it to maintain multiple views of the same entity from different scrapers. This enables the API to provide both a merged view of all data and individual views from each scraper, with clear attribution of which scraper provided each piece of data.

## Architecture

The reconciler is built on a hierarchical component structure:

1. **Base Components**
   - `BaseReconciler`: Abstract base class providing database and Redis connections
   - Implements async context management for resource cleanup

2. **Core Components**
   - `JobProcessor`: Handles job queue processing and HSDS data extraction
   - `LocationCreator`: Manages location creation and matching
   - `OrganizationCreator`: Handles organization and identifier creation
   - `ServiceCreator`: Manages services, phones, languages, and schedules
   - `VersionTracker`: Maintains record version history
   - `MergeStrategy`: Implements strategies for merging source-specific records
   - `ReconcilerUtils`: High-level utility wrapper

## Data Flow

1. **Job Processing**
   - Polls Redis queue for completed LLM jobs
   - Validates job completion status and required fields
   - Extracts and validates HSDS data using TypedDict schemas
   - Processes entities in order: organizations → locations → services
   - Creates service-to-location links with schedules
   - Handles phone numbers and languages for all entity types

2. **Location Matching**
   - Uses coordinate-based matching with 4-decimal precision (~11m radius)
   - When match found:
     * Creates or updates source-specific record for the current scraper
     * Merges all source records to update the canonical record
     * Creates new version to track changes
   - When no match found:
     * Creates new canonical location with UUID
     * Creates source-specific record for the current scraper
     * Creates addresses with validation
     * Creates accessibility records
     * Creates phone records with languages
     * Creates initial version

3. **Organization Processing**
   - Matches organizations by name
   - Creates new organizations with complete metadata
   - Creates or updates source-specific records
   - Handles organization identifiers
   - Creates phone records with language support
   - Maintains version history

4. **Service Processing**
   - Creates services with UUIDs
   - Creates or updates source-specific records
   - Links to organization if available
   - Creates service-at-location records
   - Handles phone numbers and languages
   - Creates schedules for service locations
   - Maintains versions for all records

## Source-Specific Records

The reconciler now maintains separate records for each scraper's view of an entity:

1. **Source-Specific Tables**:
   - `location_source`: Stores source-specific location data
   - `organization_source`: Stores source-specific organization data
   - `service_source`: Stores source-specific service data

2. **Canonical Records**:
   - The original tables (`location`, `organization`, `service`) now serve as canonical/merged records
   - The `is_canonical` column in the `location` table indicates if a record is a merged view

3. **Merging Strategy**:
   - The `MergeStrategy` class implements strategies for merging source records into canonical records
   - Current strategies include:
     * For names: Use the most common value (majority vote)
     * For descriptions: Use the longest non-empty description
     * For coordinates: Use the most recent values
     * For other fields: Use the first non-empty value

## Data Structures

The reconciler uses TypedDict definitions to validate HSDS data:

```python
class ServiceDict(TypedDict):
    name: str
    description: str
    phones: List[Dict[str, Any]]
    languages: List[Dict[str, Any]]
    schedules: List[ScheduleDict]

class OrganizationDict(TypedDict):
    name: str
    description: str
    website: str
    email: str
    year_incorporated: int
    legal_status: str
    uri: str
    phones: List[Dict[str, Any]]
    services: List[ServiceDict]
    organization_identifiers: List[Dict[str, Any]]

class LocationDict(TypedDict):
    name: str
    description: str
    latitude: float
    longitude: float
    addresses: List[Dict[str, Any]]
    phones: List[Dict[str, Any]]
    schedules: List[ScheduleDict]
    accessibility: List[Dict[str, Any]]
```

## Version Tracking

The reconciler maintains a complete history of all records through versioning:

```sql
WITH next_version AS (
    SELECT COALESCE(MAX(version_num), 0) + 1 as version_num
    FROM record_version
    WHERE record_id = :record_id
    AND record_type = :record_type
)
INSERT INTO record_version (
    record_id,
    record_type,
    version_num,
    data,
    created_by,
    source_id
)
SELECT
    :record_id,
    :record_type,
    version_num,
    :data,
    :created_by,
    :source_id
FROM next_version
```

Each version contains:
- Complete record data at that point in time
- Version number
- Creation timestamp
- Creator identifier
- Source metadata
- Source record ID (if applicable)

## API Queries

The following SQL queries can be used by the API to retrieve different views of the data:

### 1. Get Canonical Location with Source Attribution

```sql
SELECT
    l.*,
    json_object_agg(
        ls.scraper_id,
        json_build_object(
            'id', ls.id,
            'name', ls.name,
            'description', ls.description,
            'latitude', ls.latitude,
            'longitude', ls.longitude
        )
    ) AS source_data,
    json_object_agg(
        field_name,
        scraper_id
    ) AS field_sources
FROM
    location l
JOIN
    location_source ls ON l.id = ls.location_id
LEFT JOIN (
    -- This subquery determines which scraper provided each field in the canonical record
    SELECT
        location_id,
        'name' AS field_name,
        scraper_id
    FROM
        location_source ls
    JOIN
        location l ON l.id = ls.location_id
    WHERE
        l.name = ls.name
    UNION ALL
    SELECT
        location_id,
        'description' AS field_name,
        scraper_id
    FROM
        location_source ls
    JOIN
        location l ON l.id = ls.location_id
    WHERE
        l.description = ls.description
    UNION ALL
    SELECT
        location_id,
        'latitude' AS field_name,
        scraper_id
    FROM
        location_source ls
    JOIN
        location l ON l.id = ls.location_id
    WHERE
        l.latitude = ls.latitude
    UNION ALL
    SELECT
        location_id,
        'longitude' AS field_name,
        scraper_id
    FROM
        location_source ls
    JOIN
        location l ON l.id = ls.location_id
    WHERE
        l.longitude = ls.longitude
) AS field_attribution ON field_attribution.location_id = l.id
WHERE
    l.id = :location_id
    AND l.is_canonical = TRUE
GROUP BY
    l.id
```

### 2. Get All Source Records for a Location

```sql
SELECT
    ls.*,
    s.name AS scraper_name
FROM
    location_source ls
LEFT JOIN
    scraper s ON ls.scraper_id = s.id
WHERE
    ls.location_id = :location_id
```

### 3. Get Locations by Scraper

```sql
SELECT
    l.*
FROM
    location l
JOIN
    location_source ls ON l.id = ls.location_id
WHERE
    ls.scraper_id = :scraper_id
    AND l.is_canonical = TRUE
```

### 4. Get Locations with Multiple Sources

```sql
SELECT
    l.*,
    COUNT(DISTINCT ls.scraper_id) AS source_count
FROM
    location l
JOIN
    location_source ls ON l.id = ls.location_id
WHERE
    l.is_canonical = TRUE
GROUP BY
    l.id
HAVING
    COUNT(DISTINCT ls.scraper_id) > 1
```

## Metrics

The reconciler tracks several Prometheus metrics:

1. **Job Processing**
   ```python
   RECONCILER_JOBS = Counter(
       "reconciler_jobs_total",
       "Total number of jobs processed by reconciler",
       ["scraper_id", "status"]
   )
   ```

2. **Location Matching**
   ```python
   LOCATION_MATCHES = Counter(
       "reconciler_location_matches_total",
       "Total number of location matches found",
       ["match_type"]  # exact, nearby, none
   )
   ```

3. **Service Records**
   ```python
   SERVICE_RECORDS = Counter(
       "reconciler_service_records_total",
       "Total number of service records created",
       ["has_organization"]
   )
   ```

4. **Service Location Links**
   ```python
   SERVICE_LOCATION_LINKS = Counter(
       "reconciler_service_location_links_total",
       "Total number of service-to-location links created",
       ["location_match_type"]
   )
   ```

5. **Version Tracking**
   ```python
   RECORD_VERSIONS = Counter(
       "reconciler_record_versions_total",
       "Total number of record versions created",
       ["record_type"]
   )
   ```

## Error Handling

The reconciler implements comprehensive error handling:

1. **Job Level**
   - Invalid LLM output → Job marked as failed
   - Missing required fields → Validation error
   - Database errors → Transaction rollback
   - Redis connection issues → Auto-reconnect

2. **Entity Level**
   - Invalid coordinates → Skip location matching
   - Missing references → Skip relationship creation
   - Version conflicts → Use optimistic locking
   - Transaction management → Commit control

3. **Resource Management**
   - Async context managers for cleanup
   - Redis connection health checks
   - Database session management
   - Error metrics tracking

## Configuration

The reconciler can be configured through environment variables:

- `REDIS_URL`: Queue connection string (required)
- `DATABASE_URL`: PostgreSQL connection string
- `LOCATION_MATCH_TOLERANCE`: Coordinate matching precision (default: 0.0001)

Redis client configuration:
```python
redis = Redis.from_url(
    redis_url,
    encoding="utf-8",
    decode_responses=False,
    retry_on_timeout=True,
    socket_keepalive=True,
    health_check_interval=30,
)
```

## Usage

The reconciler can be run as a standalone service:

```bash
# Start the reconciler service
python -m app.reconciler

# With custom interval
python -m app.reconciler --interval 30
```

## Migration

A migration script is provided to populate the source-specific tables from the existing version history:

```bash
# Run a dry run to see what would be migrated
python scripts/migrate_to_source_records.py --dry-run

# Migrate all entities
python scripts/migrate_to_source_records.py

# Migrate only locations
python scripts/migrate_to_source_records.py --entity location
```

## Implementation Steps

To implement the source-specific reconciler:

1. **Apply Database Schema Changes**:
   ```bash
   # Run the schema migration script
   psql -U postgres -d your_database_name -f init-scripts/04-source-specific-records.sql
   ```

2. **Update Reconciler Code**:
   - Replace `app/reconciler/location_creator.py` with the updated version
   - Replace `app/reconciler/version_tracker.py` with the updated version
   - Add the new `app/reconciler/merge_strategy.py` file

3. **Migrate Existing Data**:
   ```bash
   # Run the migration script
   python scripts/migrate_to_source_records.py
   ```

## Future Improvements

Potential enhancements to consider:

1. **Enhanced Matching**
   - Fuzzy name matching for locations
   - Service similarity detection
   - Organization deduplication
   - Address normalization

2. **Performance**
   - Batch processing of jobs
   - Parallel entity processing
   - Optimized database operations
   - Redis pipeline operations

3. **Monitoring**
   - Real-time metrics dashboard
   - Alert thresholds
   - Performance tracking
   - Error rate monitoring

4. **Data Quality**
   - Schema validation
   - Data cleaning
   - Confidence scoring
   - Duplicate detection

5. **Schedule Management**
   - Recurring schedule validation
   - Schedule conflict detection
   - Holiday handling
   - Timezone support

6. **Merging Strategies**
   - Field-by-field priority based on scraper quality
   - Recency-based merging for frequently changing fields
   - Completeness scoring for source records
   - Conflict resolution with confidence scores
   - Manual resolution for critical conflicts
