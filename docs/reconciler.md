# Reconciler Service

The reconciler service is responsible for processing HSDS data from LLM outputs and integrating it into the database while maintaining data consistency and versioning. It features advanced geocoding with multi-provider fallback, automatic coordinate validation, and exhaustive correction attempts. This document describes how the reconciler works and its key components.

## Overview

The reconciler takes completed jobs from either the validation service (when `VALIDATOR_ENABLED=true`) or directly from the LLM queue, processes their output to extract HSDS entities, and either creates new records or updates existing ones based on matching criteria. When receiving data from the validator, it leverages pre-calculated confidence scores and validation statuses to make intelligent processing decisions, including rejecting low-confidence locations entirely. It maintains a complete version history of all changes and tracks various metrics about the reconciliation process.

The reconciler now supports source-specific records, allowing it to maintain multiple views of the same entity from different scrapers. This enables the API to provide both a merged view of all data and individual views from each scraper, with clear attribution of which scraper provided each piece of data.

## Data Pipeline Integration

The reconciler's position in the data pipeline depends on the `VALIDATOR_ENABLED` configuration:

**With Validator (default, `VALIDATOR_ENABLED=true`):**
```
Scrapers → Content Store → LLM Queue → LLM Workers → Validator Queue → 
Validator Service (enrichment & scoring) → Reconciler Queue → Reconciler → Database
```

**Without Validator (`VALIDATOR_ENABLED=false`):**
```
Scrapers → Content Store → LLM Queue → LLM Workers → Reconciler Queue → Reconciler → Database
```

## Architecture

The reconciler is built on a hierarchical component structure:

1. **Base Components**
   - `BaseReconciler`: Abstract base class providing database and Redis connections
   - Implements async context management for resource cleanup

2. **Core Components**
   - `JobProcessor`: Handles job queue processing and HSDS data extraction
   - `LocationCreator`: Manages location creation and matching with geocoding validation
   - `OrganizationCreator`: Handles organization and identifier creation
   - `ServiceCreator`: Manages services, phones, languages, and schedules
   - `VersionTracker`: Maintains record version history
   - `MergeStrategy`: Implements strategies for merging source-specific records
   - `GeocodingCorrector`: Validates and corrects geographic coordinates
   - `ReconcilerUtils`: High-level utility wrapper

## Data Flow

1. **Job Processing**
   - Receives jobs from validator queue (when `VALIDATOR_ENABLED=true`) or LLM queue directly
   - Validates job completion status and required fields
   - Extracts validation data (confidence_score, validation_status, validation_notes) from job.data when available
   - Extracts and validates HSDS data using TypedDict schemas
   - Rejects entities with confidence_score below threshold (default: 10)
   - Processes entities in order: organizations → locations → services
   - Creates service-to-location links with schedules
   - Handles phone numbers and languages for all entity types

2. **Location Matching and Geocoding**
   - **Pre-enriched Data from Validator**: When data comes from validator, locations arrive with:
     * Pre-validated and enriched coordinates
     * Confidence scores for quality assessment
     * Validation status (verified/needs_review/rejected)
     * Geocoding source tracking
   - Uses coordinate-based matching with 4-decimal precision (~11m radius)
   - **Low-confidence Location Handling**:
     * Locations marked as "rejected" by validator are skipped entirely
     * Locations with confidence_score < 10 are not created in database
     * Reconciler trusts validator's coordinate enrichment - no additional geocoding
   - When match found:
     * Creates or updates source-specific record for the current scraper
     * Merges all source records to update the canonical record
     * Creates new version to track changes
   - When no match found:
     * Validates coordinates before creation
     * Creates new canonical location with UUID
     * Creates source-specific record for the current scraper
     * Creates addresses with validation
     * Creates accessibility records
     * Creates phone records with languages
     * Creates initial version
     * Stores validation metadata (confidence_score, validation_status, validation_notes, geocoding_source)

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

## Validation Data Integration

The reconciler integrates validation data from the validator service (Issue #366):

1. **Data Extraction**:
   - Checks for validation data in `JobResult.job.data` (enriched by validator)
   - Extracts confidence_score, validation_status, validation_notes for each entity
   - Matches validation data to entities by name and/or coordinates

2. **Entity Matching**:
   - **Organizations**: Matched by exact name
   - **Locations**: Matched by name or coordinates (within 0.0001 tolerance)
   - **Services**: Matched by exact name

3. **Confidence-Based Processing**:
   - **Rejected Status**: Entities with `validation_status = "rejected"` are skipped entirely
   - **Low Confidence**: Default rejection threshold is 10 (configurable via `VALIDATION_REJECTION_THRESHOLD`)
   - **Database Persistence**: All validation fields are stored in the database for future reference

4. **Database Fields**:
   - `confidence_score` (INTEGER 0-100): Data quality confidence score
   - `validation_status` (TEXT): Status can be "verified", "needs_review", or "rejected"
   - `validation_notes` (JSONB): Structured validation results and notes
   - `geocoding_source` (TEXT): Source of geocoding (arcgis, google, nominatim, census, original)

5. **Creator Method Integration**:
   All creator methods (`create_location`, `create_organization`, `create_service`) accept optional validation parameters:
   ```python
   def create_location(
       self,
       name: str,
       description: str,
       latitude: float,
       longitude: float,
       metadata: dict[str, Any],
       organization_id: str | None = None,
       confidence_score: int | None = None,
       validation_status: str | None = None,
       validation_notes: dict[str, Any] | None = None,
       geocoding_source: str | None = None,
   ) -> str | None:
   ```

6. **Example Data Flow**:
   ```python
   # Validator enriches job with validation data
   job.data = {
       "locations": [
           {
               "name": "Food Bank",
               "confidence_score": 85,
               "validation_status": "verified",
               "validation_notes": {"geocoding": "enriched", "address": "validated"},
               "geocoding_source": "arcgis"
           },
           {
               "name": "Low Quality Location",
               "confidence_score": 5,
               "validation_status": "rejected",
               "validation_notes": {"reason": "invalid_address"}
           }
       ]
   }
   
   # Reconciler processes validation data
   # - First location: Created with confidence_score=85, status="verified"
   # - Second location: Skipped entirely (rejected status)
   ```

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

### Core Settings
- `REDIS_URL`: Queue connection string (required)
- `DATABASE_URL`: PostgreSQL connection string
- `LOCATION_MATCH_TOLERANCE`: Coordinate matching precision (default: 0.0001)

### Validation Integration
- `VALIDATOR_ENABLED`: Enable validator service integration (default: true)
- `VALIDATION_REJECTION_THRESHOLD`: Minimum confidence score to accept data (default: 10)
- When `VALIDATOR_ENABLED=true`, reconciler receives pre-validated data from validator queue
- When `VALIDATOR_ENABLED=false`, reconciler processes LLM output directly without validation

### Geocoding Settings
- `GEOCODING_PROVIDER`: Primary geocoding provider (nominatim, google, mapbox)
- `GEOCODING_RATE_LIMIT`: Requests per second (default: 1.0)
- `GEOCODING_CACHE_TTL`: Cache TTL in seconds (default: 2592000 - 30 days)
- `GEOCODING_FALLBACK_ENABLED`: Enable automatic provider fallback (default: true)
- Note: When receiving data from validator, geocoding is typically already done

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

## Usage with Bouy

The reconciler should be managed using bouy commands:

```bash
# Start the reconciler service
./bouy reconciler

# Run reconciler with specific options
./bouy reconciler --force    # Force processing

# View reconciler logs
./bouy logs reconciler

# Check reconciler status
./bouy ps reconciler

# Run geocoding correction batch
./bouy exec reconciler python -m app.reconciler.geocoding_corrector

# Validate all location coordinates
./bouy exec reconciler python -c "from app.reconciler.geocoding_corrector import GeocodingCorrector; from app.database import get_db; gc = GeocodingCorrector(next(get_db())); print(gc.validate_all_locations())"
```

### Monitoring and Debugging

```bash
# Monitor reconciler metrics
./bouy exec reconciler python -c "from app.reconciler.metrics import get_metrics; print(get_metrics())"

# Check for invalid coordinates
./bouy exec reconciler python -c "from app.reconciler.geocoding_corrector import GeocodingCorrector; from app.database import get_db; gc = GeocodingCorrector(next(get_db())); invalid = gc.find_invalid_locations(); print(f'Found {len(invalid)} invalid locations')"

# Run batch correction with limit
./bouy exec reconciler python -c "from app.reconciler.geocoding_corrector import GeocodingCorrector; from app.database import get_db; gc = GeocodingCorrector(next(get_db())); results = gc.batch_correct_locations(limit=10); print(results)"
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

## Geocoding and Coordinate Validation

The reconciler includes sophisticated geocoding correction capabilities:

### Automatic Detection and Correction

1. **Invalid Coordinate Detection**:
   - Zero coordinates (0,0 - null island)
   - Projected coordinates (Web Mercator, State Plane)
   - Out-of-bounds coordinates (outside US/state boundaries)
   - Swapped latitude/longitude values

2. **Multi-Provider Fallback**:
   ```python
   # The system automatically tries providers in order:
   # 1. Primary provider (configured)
   # 2. Secondary providers (fallback)
   # 3. Default coordinates with offset (last resort)
   ```

3. **Validation Process**:
   - Pre-creation validation catches issues early
   - Post-creation batch correction fixes existing data
   - Continuous monitoring tracks geocoding quality

### Using the Geocoding Corrector

```bash
# Find all locations with invalid coordinates
./bouy exec reconciler python -m app.reconciler.geocoding_corrector find

# Correct invalid locations (with limit)
./bouy exec reconciler python -m app.reconciler.geocoding_corrector correct --limit 100

# Validate specific location
./bouy exec reconciler python -m app.reconciler.geocoding_corrector validate --location-id <UUID>

# Get correction statistics
./bouy exec reconciler python -m app.reconciler.geocoding_corrector stats
```

## Future Improvements

Potential enhancements to consider:

1. **Enhanced Matching**
   - Fuzzy name matching for locations
   - Service similarity detection
   - Organization deduplication
   - Address normalization
   - Machine learning-based duplicate detection

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
