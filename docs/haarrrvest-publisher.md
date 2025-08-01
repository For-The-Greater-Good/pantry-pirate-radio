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

## Usage

### Starting the Service

```bash
# Start the HAARRRvest publisher service
docker-compose up -d haarrrvest-publisher

# View logs
docker-compose logs -f haarrrvest-publisher

# Trigger immediate processing (restart the service)
docker-compose restart haarrrvest-publisher
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

### Manual Testing

To test the publisher without Docker:

```bash
# Make sure you have DATABASE_URL set
export DATABASE_URL=postgresql://user:pass@localhost:5432/pantry_pirate_radio

# Run the test script
python test_haarrrvest_publisher.py
```

## How It Works

### 1. File Monitoring
- Monitors `outputs/daily/` for new JSON files
- Tracks processed files in `.haarrrvest_publisher_state.json`
- Only processes files from the last N days (configurable)

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

### 3. Data Synchronization
- Copies new files to HAARRRvest repository structure
- Maintains same directory layout (`daily/`, `latest/`)
- Syncs content store to `content_store/` directory for durability
- Updates repository metadata (README.md, STATS.md)
- Includes content store statistics in repository metadata

### 4. Database Operations
- Creates PostgreSQL SQL dumps for fast initialization
- Runs database rebuild if script is available
- Exports PostgreSQL to SQLite using `db-to-sqlite` or Python fallback
- Creates metadata.json for Datasette

### 5. Map Data Generation
- Runs HAARRRvest's `export-locations.py` script
- Generates JSON files in `data/` directory
- Creates state-specific files for performance

### 6. Git Operations
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
# Create a SQL dump manually
docker compose exec app bash /app/scripts/create-sql-dump.sh

# Or from host with database running
POSTGRES_PASSWORD=your_password ./scripts/create-sql-dump.sh
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

## Directory Structure

The service expects:
```
pantry-pirate-radio/
├── outputs/              # Recorder output files
│   ├── daily/
│   └── latest/
├── docs/HAARRRvest/     # HAARRRvest repository
└── scripts/             # Optional rebuild scripts
```

## Troubleshooting

### Service won't start
- Check Docker logs: `docker-compose logs haarrrvest-publisher`
- Verify DATABASE_URL is set in `.env`
- Ensure HAARRRvest repo exists at `docs/HAARRRvest/`

### Git push fails
- Check SSH keys are mounted: `~/.ssh:/root/.ssh:ro`
- Verify DATA_REPO_TOKEN for HTTPS repos
- Ensure repository write permissions

### Map not updating
- Check if SQLite export succeeded
- Verify `export-locations.py` ran successfully
- Look for `data/locations.json` in HAARRRvest repo

### Files not being processed
- Check `.haarrrvest_publisher_state.json` in outputs/
- Remove state file to reprocess all files
- Verify file timestamps are within DAYS_TO_SYNC

## Integration with Scrapers

The publisher works with the existing scraper → recorder → reconciler pipeline:

1. **Scrapers** generate data → saved by **Recorder** to `outputs/`
2. **HAARRRvest Publisher** picks up new files from `outputs/`
3. Creates branch, syncs data, generates SQLite/map data
4. Merges and pushes to HAARRRvest repository
5. HAARRRvest serves data via GitHub Pages

This replaces the previous GitHub Actions workflow with a local, container-based solution that gives you more control over the publishing process.