# Data Publishing Pipeline

This document describes the automated data publishing pipeline that organizes, syncs, and exports food resource data for public consumption.

## Overview

The data publishing pipeline is a comprehensive solution that:

1. **Organizes** recorder output files by date and scraper
2. **Syncs** data to a separate Git repository for distribution
3. **Rebuilds** the database from recorded JSON files
4. **Exports** data to SQLite for use with Datasette

## Components

### Master Script: `publish-data.sh`

The main orchestration script that runs all pipeline steps:

```bash
./scripts/publish-data.sh [OPTIONS]

Options:
  --days N          Number of days to sync (default: 7)
  --no-rebuild      Skip database rebuild
  --no-export       Skip datasette export
  --no-push         Don't push to remote repository
  --data-repo PATH  Path to data repository
  --help            Show help message
```

### GitHub Action: `publish-data.yml`

Automated workflow that runs the pipeline:
- **Schedule**: Daily at 4 AM UTC
- **Manual trigger**: Via GitHub Actions UI
- **Artifacts**: SQLite database and reports

## Pipeline Steps

### Step 1: File Organization Verification

- Verifies the recorder's date-based directory structure
- Counts files in daily and latest directories
- Warns about any legacy flat-structure files

### Step 2: Data Repository Sync

- Clones or updates the data repository
- Syncs daily data for configured number of days
- Resolves symlinks to copy actual latest files
- Generates statistics and README

### Step 3: Database Rebuild

- Uses the replay tool to process JSON files
- Recreates database records from saved job results
- Processes data chronologically by date
- Handles errors gracefully

### Step 4: Datasette Export

- Exports PostgreSQL data to SQLite
- Generates metadata for Datasette
- Creates optimized database for exploration
- Includes all HSDS-compliant tables

### Step 5: Finalization

- Commits all changes to data repository
- Generates update report with statistics
- Pushes to remote repository
- Creates summary artifacts

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `OUTPUT_DIR` | Recorder output directory | `outputs/` |
| `DATA_REPO_PATH` | Path to data repository | `../HAARRRvest` |
| `DATA_REPO_URL` | Git URL for data repo | GitHub SSH URL |
| `DAYS_TO_SYNC` | Number of days to process | `7` |
| `REBUILD_DATABASE` | Rebuild DB from JSON | `true` |
| `EXPORT_DATASETTE` | Export to SQLite | `true` |
| `PUSH_TO_REMOTE` | Push changes to Git | `true` |

### GitHub Secrets

Required secrets for GitHub Actions:

- `DATA_REPO_TOKEN`: Personal access token with write access to data repository

## Local Development

### Running Locally

```bash
# Basic run - sync last 7 days
./scripts/publish-data.sh

# Sync last 30 days without pushing
./scripts/publish-data.sh --days 30 --no-push

# Skip database operations (sync only)
./scripts/publish-data.sh --no-rebuild --no-export

# Use custom data repository path
./scripts/publish-data.sh --data-repo /path/to/data-repo
```

### Testing the Pipeline

```bash
# Dry run without pushing
PUSH_TO_REMOTE=false ./scripts/publish-data.sh

# Test with minimal data
DAYS_TO_SYNC=1 ./scripts/publish-data.sh --no-push

# Verbose output for debugging
export DEBUG=1
./scripts/publish-data.sh
```

## Data Repository Structure

The pipeline creates this structure in the data repository:

```
HAARRRvest/
├── README.md              # Auto-generated documentation
├── STATS.md              # Data statistics
├── LAST_UPDATE.md        # Update report
├── daily/                # Daily data by date
│   └── YYYY-MM-DD/
│       ├── summary.json
│       ├── scrapers/
│       │   └── {scraper_id}/
│       └── processed/
├── latest/               # Most recent per scraper
│   └── {scraper_id}_latest.json
└── sqlite/               # Datasette files
    ├── pantry_pirate_radio.sqlite
    └── metadata.json
```

## Monitoring

### GitHub Actions Dashboard

Monitor pipeline runs at:
```
https://github.com/For-The-Greater-Good/pantry-pirate-radio/actions/workflows/publish-data.yml
```

### Success Indicators

- Workflow completes with green checkmark
- Data repository shows recent commits
- SQLite artifact is generated
- No issues created

### Failure Handling

- Automatic issue creation on failure
- Detailed logs in GitHub Actions
- Artifacts preserved for debugging
- Partial sync is safe (idempotent)

## Datasette Deployment

After SQLite generation, data can be explored using Datasette:

### Local Datasette

```bash
# Install datasette
pip install datasette

# Run locally
datasette pantry_pirate_radio.sqlite

# With plugins
datasette pantry_pirate_radio.sqlite \
  --plugins datasette-cluster-map \
  --plugins datasette-vega
```

### Cloud Deployment Options

1. **Fly.io** (Recommended)
   ```bash
   fly launch --image datasette/datasette
   fly volumes create data --size 1
   fly deploy
   ```

2. **Vercel**
   - Use datasette-publish-vercel
   - Serverless deployment

3. **Google Cloud Run**
   - Containerized deployment
   - Auto-scaling

## Troubleshooting

### Common Issues

**Database Connection Failed**
- Check DATABASE_URL is set correctly
- Verify PostgreSQL is running
- Check network connectivity

**Git Push Failed**
- Verify DATA_REPO_TOKEN has write access
- Check repository permissions
- Ensure SSH keys are configured

**Replay Tool Errors**
- Check JSON file validity
- Verify job completion status
- Review error logs

**SQLite Export Failed**
- Check disk space
- Verify PostgreSQL permissions
- Review table structures

### Debug Mode

Enable verbose logging:
```bash
export DEBUG=1
export VERBOSE=1
./scripts/publish-data.sh
```

## Performance Considerations

- **Sync Window**: Limit days to sync for faster runs
- **Database Size**: Monitor SQLite file size
- **Git History**: Periodically clean old data
- **Concurrent Runs**: Prevented by GitHub Actions

## Security

- Data repository can be public or private
- No sensitive data in published files
- Git history preserved for audit
- Access controlled via GitHub permissions

## Future Enhancements

1. **Incremental Updates**: Only sync changed files
2. **Data Validation**: Pre-sync data quality checks
3. **Multiple Formats**: CSV, Parquet exports
4. **API Generation**: Static JSON API
5. **Automated Backups**: S3/GCS archives
6. **Data Versioning**: Semantic versioning for datasets