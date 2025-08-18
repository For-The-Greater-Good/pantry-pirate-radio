# HAARRRvest Publisher Service

The HAARRRvest Publisher Service is a dedicated service that monitors recorder outputs and publishes them to the HAARRRvest repository with branch-based workflows.

## Key Features

- **Automatic Monitoring**: Checks for new files every 5 minutes
- **Immediate Processing**: Runs on startup for manual triggering
- **Branch-Based Publishing**: Creates date-based branches (e.g., `data-update-2025-01-25`)
- **Merge Commits**: Merges branches to main with proper commit history
- **Content Store Sync**: Automatically backs up content deduplication store
- **SQL Dump Generation**: Creates PostgreSQL dumps for fast initialization
- **SQLite Export**: Generates SQLite database for Datasette
- **Map Data Generation**: Runs HAARRRvest's location export for web maps
- **State Tracking**: Remembers processed files to avoid duplicates
- **Repository Sync**: Always pulls latest changes before processing
- **Confidence Score Export**: Includes validation confidence scores and status in all exported data
- **Automatic Data Filtering**: Excludes low-confidence locations (< 10) from public data

## Usage

### Starting the Service

```bash
# Start all services including the HAARRRvest publisher
./bouy up

# View publisher logs
./bouy haarrrvest logs

# Check publisher service status
./bouy haarrrvest status

# Manually trigger publishing run
./bouy haarrrvest run

# The service runs automatically:
# - On startup (processes pending files immediately)
# - Every 5 minutes (configurable via PUBLISHER_CHECK_INTERVAL)
# - Creates date-based branches for safety
```

### Configuration

Add to your `.env` file:

```bash
# HAARRRvest repository settings (use HTTPS for security)
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_personal_access_token  # Required for private repos

# Publishing settings
PUBLISHER_CHECK_INTERVAL=300  # Check every 5 minutes (in seconds)
DAYS_TO_SYNC=7               # Sync last 7 days of data

# CRITICAL: Push permission - MUST be explicitly enabled for production
# Default is 'false' to prevent accidental pushes from dev environments
PUBLISHER_PUSH_ENABLED=false  # Set to 'true' ONLY for production deployments
```

⚠️ **IMPORTANT**: The publisher will NOT push to remote by default. You must explicitly set `PUBLISHER_PUSH_ENABLED=true` for production deployments that should push data to HAARRRvest.

### Testing the Publisher

```bash
# Run tests for the publisher service
./bouy test --pytest tests/test_haarrrvest_publisher.py

# Test in dry-run mode (no actual pushes)
# Ensure PUBLISHER_PUSH_ENABLED=false in .env
./bouy haarrrvest run

# Check the logs to verify processing
./bouy haarrrvest logs

# Verify files were processed
./bouy exec app cat outputs/.haarrrvest_publisher_state.json
```

## How It Works

### 1. File Monitoring
- Monitors `outputs/daily/` for new JSON files
- Tracks processed files in `.haarrrvest_publisher_state.json`
- Only processes files from the last N days (configurable via `DAYS_TO_SYNC`)
- Runs every 5 minutes by default (configurable via `PUBLISHER_CHECK_INTERVAL`)

### 2. Repository Safety
- Always pulls latest changes from origin/main before starting
- Stashes any uncommitted changes automatically
- Checks for existing branches (local and remote)
- Adds timestamp to branch name if conflict exists
- Never force-pushes or overwrites

### 3. Branch Creation
- Creates a branch named `data-update-YYYY-MM-DD`
- If branch exists, appends time: `data-update-YYYY-MM-DD-HHMMSS`
- All changes are committed to this branch first
- Prevents accidental commits to main

### 4. Data Synchronization
- Copies new files to HAARRRvest repository structure
- Maintains same directory layout (`daily/`, `latest/`)
- Syncs content store to `content_store/` directory for durability
- Updates repository metadata (README.md, STATS.md)
- Includes content store statistics in repository metadata
- **Confidence Score Metrics**: README.md automatically includes average confidence scores and high-confidence location counts

### 5. Database Operations
- Creates PostgreSQL SQL dumps for fast initialization
- Runs database rebuild if script is available
- Exports PostgreSQL to SQLite using `db-to-sqlite` or Python fallback
- Creates metadata.json for Datasette

### 6. Map Data Generation
- Runs HAARRRvest's `export-locations.py` script
- Generates JSON files in `data/` directory
- Creates state-specific files for performance
- **Data Filtering**: Automatically excludes rejected locations (confidence_score < 10) from exports
- **Validation Data Export**: Includes confidence scores and validation metadata in exported data

### 7. Git Operations
- Commits all changes to the feature branch
- Merges to main with `--no-ff` (creates merge commit)
- Pushes to remote repository
- Deletes the feature branch

## SQL Dump Integration

The HAARRRvest publisher generates PostgreSQL dumps for fast database initialization:

### How It Works

1. **Frequent Generation**: Creates SQL dumps on every pipeline run (startup, every 5 minutes, and shutdown)
2. **Fast Initialization**: Reduces init time from 30+ minutes to <5 minutes
3. **Git-Friendly**: Uncompressed SQL files allow git to track changes efficiently
4. **Rotation**: Keeps last 24 hours of dumps with `latest.sql` symlink
5. **Graceful Shutdown**: Creates final SQL dump on service shutdown to preserve state
6. **Safety Checks**: Prevents creating dumps from empty/corrupted databases

### Safety Features

The publisher includes ratcheting safety checks to prevent data loss:

- **Ratcheting Threshold**: Tracks the highest known record count and prevents creating dumps with significantly fewer records
- **Percentage-Based Check**: Allows dumps only if record count is at least 90% of the previous maximum (configurable)
- **Initial Dump Protection**: Uses minimum threshold (default: 100) when no ratchet file exists
- **Override Option**: Set `ALLOW_EMPTY_SQL_DUMP=true` to bypass all safety checks
- **Commit Prevention**: Skips git commit if dump fails safety checks
- **High Water Mark Tracking**: Automatically updates maximum record count when database grows

The ratchet file (`.record_count_ratchet`) is stored in the `sql_dumps/` directory and tracks:
- `max_record_count`: Highest known database record count
- `updated_at`: When the high water mark was set
- `updated_by`: Which tool updated it (publisher or manual script)

Environment variables:
- `SQL_DUMP_MIN_RECORDS`: Minimum records for initial dump (default: 100)
- `SQL_DUMP_RATCHET_PERCENTAGE`: Threshold as percentage of max (default: 0.9 = 90%)
- `ALLOW_EMPTY_SQL_DUMP`: Override all safety checks (default: false)

### Benefits

- **6x Faster**: Initialize databases in minutes instead of hours
- **Reliable**: Single file restore vs processing thousands of JSON files
- **Version Control**: Git can track changes in uncompressed SQL files
- **Continuous Backup**: SQL dumps created every 5 minutes capture database evolution
- **Versioned**: Daily dumps allow point-in-time restoration

### Manual SQL Dump Creation

```bash
# Create a SQL dump manually using bouy
./bouy exec app bash /app/scripts/create-sql-dump.sh

# View existing SQL dumps
./bouy exec app ls -la /data-repo/sql_dumps/

# Check the latest dump symlink
./bouy exec app readlink /data-repo/sql_dumps/latest.sql
```

### Using SQL Dumps for Initialization

The `db-init` service automatically detects and uses SQL dumps:

```bash
# SQL dumps are used in this order:
1. HAARRRvest/sql_dumps/latest.sql (symlink to most recent)
2. HAARRRvest/sql_dumps/pantry_pirate_radio_YYYY-MM-DD_HH-MM-SS.sql (newest first)
3. If no dumps available, database remains empty
```

**Note**: JSON replay has been removed for consistency. Use SQL dumps for database initialization.

## Confidence Score Export

The HAARRRvest publisher includes comprehensive validation and confidence data in all exports (implemented in Issue #368):

### How Confidence Scores Work

1. **Score Range**: 0-100, where higher scores indicate more reliable data
2. **Automatic Filtering**: Locations with confidence_score < 10 are rejected and excluded from exports
3. **Validation Status**: Each location has one of three statuses:
   - `verified`: High confidence, validated data
   - `needs_review`: Medium confidence, may need manual review
   - `rejected`: Low confidence, excluded from exports

### Exported Validation Fields

Each location in the exported data includes:

- **confidence_score**: Numeric score from 0-100 indicating data reliability
- **validation_status**: Current validation state (verified/needs_review/rejected)
- **validation_notes**: Detailed notes about validation decisions and data quality issues
- **geocoding_source**: The geocoding provider used (ArcGIS, Google Maps, Nominatim, Census)

### Data Format Example

```json
{
  "metadata": {
    "generated": "2025-01-17T10:00:00Z",
    "total_locations": 1523,
    "high_confidence_locations": 1205,
    "average_confidence": 78.5,
    "validation_summary": {
      "verified": 1205,
      "needs_review": 318,
      "rejected": 47
    }
  },
  "locations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Community Food Pantry",
      "lat": 40.7128,
      "lng": -74.0060,
      "confidence_score": 95,
      "validation_status": "verified",
      "validation_notes": {
        "geocoding": "High accuracy match",
        "data_completeness": "All required fields present"
      },
      "geocoding_source": "google_maps",
      ...
    }
  ]
}
```

### Repository Metadata Updates

The HAARRRvest README.md is automatically updated with confidence metrics:

- Total locations exported
- Average confidence score across all locations
- Number of high-confidence locations (score ≥ 80)
- Breakdown by validation status
- Data quality trends over time

## Content Store Integration

The HAARRRvest publisher automatically syncs the content deduplication store:

### How It Works

1. **Automatic Detection**: Checks if content store is configured
2. **Incremental Sync**: Only copies new or updated files
3. **Preserves History**: Never deletes existing content store data
4. **Statistics**: Includes deduplication metrics in STATS.md

### Synced Data

```
HAARRRvest/
├── content_store/
│   └── content-store/
│       ├── index.db          # SQLite index of all content
│       └── content/          # SHA-256 organized content files
│           ├── ab/
│           │   └── cd/
│           │       └── abcdef...json
│           └── ...
```

### Benefits

- **Durability**: Content store backed up to Git repository
- **History**: Git tracks all changes to content store
- **Recovery**: Can restore content store from HAARRRvest
- **Analytics**: Track deduplication effectiveness over time

## Map Integration

The HAARRRvest web map interface displays confidence scores with visual indicators:

### Confidence Score Color Coding

Locations on the map are color-coded based on their confidence scores:

- **High Confidence (80-100)**: Green markers with ✅ icon
  - Verified, high-quality data
  - Accurate geocoding from reliable sources
  - Complete information available

- **Medium Confidence (50-79)**: Orange markers with ⚡ icon  
  - Generally reliable but may need review
  - Some data fields may be missing
  - Geocoding confidence is moderate

- **Low Confidence (< 50)**: Red markers with ⚠️ icon
  - Data quality concerns identified
  - May have geocoding issues
  - Requires manual verification

### Location Popups

Each location popup on the map displays:
- Organization and location name
- Full address
- Contact information (phone, website, email)
- **Confidence score with color indicator**
- **Validation status icon**
- **Geocoding source** (when available)
- Description of services

### Data Filtering

The map interface allows users to:
- Filter locations by confidence score range
- Show only verified locations
- Hide locations needing review
- Search within high-confidence locations only

## Directory Structure

The service expects and creates:
```
pantry-pirate-radio/
├── outputs/                          # Recorder output files
│   ├── daily/                       # Daily JSON recordings
│   │   └── YYYY-MM-DD/              # Date-organized data
│   ├── latest/                      # Latest data symlinks
│   └── .haarrrvest_publisher_state.json  # Processing state
├── /data-repo/                      # HAARRRvest repository (Docker volume)
│   ├── daily/                       # Published daily data
│   ├── latest/                      # Published latest data
│   ├── sqlite/                      # SQLite database exports
│   ├── sql_dumps/                   # PostgreSQL dumps
│   ├── content_store/               # Content deduplication store
│   └── data/                        # Map visualization data
└── scripts/                         # Utility scripts
    └── create-sql-dump.sh           # SQL dump generation
```

## Troubleshooting

### Service won't start
- Check Docker logs: `./bouy haarrrvest logs`
- Verify DATABASE_URL is set in `.env`: `grep DATABASE_URL .env`
- Check all services are running: `./bouy ps`
- Verify data-repo volume exists: `docker volume ls | grep data-repo`

### Git push fails
- Check push is enabled: `grep PUBLISHER_PUSH_ENABLED .env` (must be `true`)
- Verify DATA_REPO_TOKEN has `repo` scope for GitHub
- Test token permissions: `curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user/repos`
- Check git configuration: `./bouy exec haarrrvest-publisher git config --list`
- Ensure repository exists and you have write access

### Map not updating
- Check if SQLite export succeeded
- Verify `export-locations.py` ran successfully
- Look for `data/locations.json` in HAARRRvest repo

### Files not being processed
- Check state file: `./bouy exec app cat outputs/.haarrrvest_publisher_state.json`
- Reset state to reprocess: `./bouy exec app rm outputs/.haarrrvest_publisher_state.json`
- Verify files exist: `./bouy exec app ls -la outputs/daily/`
- Check DAYS_TO_SYNC setting: `grep DAYS_TO_SYNC .env`
- Force immediate processing: `./bouy haarrrvest run`

## Integration with Scrapers

The publisher works with the existing scraper → recorder → reconciler pipeline:

1. **Scrapers** generate data → saved by **Recorder** to `outputs/`
2. **Validator** enriches data with confidence scores and validation status (Issue #368)
3. **HAARRRvest Publisher** picks up new files from `outputs/`
4. Creates branch, syncs data, generates SQLite/map data
5. Filters out rejected locations (confidence < 10) automatically
6. Exports validation metadata with all locations
7. Merges and pushes to HAARRRvest repository
8. HAARRRvest serves data via GitHub Pages with confidence indicators

This replaces the previous GitHub Actions workflow with a local, container-based solution that gives you more control over the publishing process.

## Implementation Notes

**Confidence Score Export (Issue #368)**: The validation and confidence scoring functionality was implemented as part of Issue #368. The export functionality automatically includes all validation fields in the database and filters out low-confidence locations to ensure data quality in public datasets.