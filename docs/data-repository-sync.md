# Data Repository Synchronization

This document describes how to sync the recorder service outputs to a separate data repository for public distribution.

## Overview

The `sync-data-repo.sh` script provides an automated way to synchronize the organized recorder outputs to a Git-based data repository. This allows you to:

- Maintain a separate repository for data distribution
- Control which data is made public
- Provide data in multiple formats (JSON, SQLite)
- Track data changes over time with Git

## Script Features

- **Selective sync**: Only syncs recent data (configurable)
- **SQLite generation**: Optionally creates a queryable database
- **Automatic Git management**: Handles cloning, pulling, committing, and pushing
- **Statistics generation**: Creates summary statistics
- **Symlink resolution**: Properly handles latest file symlinks

## Usage

### Basic Sync

```bash
# Sync last 7 days of data
./scripts/sync-data-repo.sh
```

### Custom Configuration

```bash
# Sync last 30 days with SQLite generation
DAYS_TO_SYNC=30 GENERATE_SQLITE=true ./scripts/sync-data-repo.sh

# Use custom paths
SOURCE_DIR=/path/to/outputs \
DATA_REPO_PATH=/path/to/data-repo \
./scripts/sync-data-repo.sh

# Don't push to remote (local sync only)
PUSH_TO_REMOTE=false ./scripts/sync-data-repo.sh
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCE_DIR` | `outputs` | Path to recorder outputs |
| `DATA_REPO_PATH` | `../HAARRRvest` | Path to data repository |
| `DATA_REPO_URL` | GitHub SSH URL | Repository clone URL |
| `DAYS_TO_SYNC` | `7` | Number of days to sync |
| `GENERATE_SQLITE` | `false` | Create SQLite database |
| `PUSH_TO_REMOTE` | `true` | Push changes to remote |
| `COMMIT_MESSAGE` | Auto-generated | Git commit message |

## Data Repository Structure

The sync script organizes data in the following structure:

```
HAARRRvest/
├── README.md              # Auto-generated documentation
├── STATS.md              # Data statistics
├── daily/                # Daily data organized by date
│   └── YYYY-MM-DD/
│       ├── summary.json
│       ├── scrapers/
│       │   └── {scraper_id}/
│       │       └── *.json
│       └── processed/
│           └── *.json
├── latest/               # Most recent data per scraper
│   └── {scraper_id}_latest.json
└── sqlite/               # Optional SQLite database
    └── food_resources.db
```

## Automation

### Cron Job Example

```bash
# Sync daily at 3 AM
0 3 * * * cd /path/to/pantry-pirate-radio && ./scripts/sync-data-repo.sh >> /var/log/data-sync.log 2>&1
```

### GitHub Action Example

```yaml
name: Sync Data Repository

on:
  schedule:
    - cron: '0 3 * * *'  # Daily at 3 AM UTC
  workflow_dispatch:     # Manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Sync data
        env:
          DATA_REPO_URL: ${{ secrets.DATA_REPO_URL }}
          GENERATE_SQLITE: true
        run: |
          ./scripts/sync-data-repo.sh
```

## SQLite Database Schema

When `GENERATE_SQLITE=true`, the script creates a SQLite database with:

### Tables

**scraped_data**
- `id`: Primary key
- `job_id`: Unique job identifier
- `scraper_id`: Source scraper
- `date`: Date of scrape (YYYY-MM-DD)
- `timestamp`: Full timestamp
- `data`: Complete JSON data
- `created_at`: Database insertion time

**daily_summaries**
- `date`: Primary key (YYYY-MM-DD)
- `total_jobs`: Number of jobs that day
- `summary_data`: Complete summary JSON
- `created_at`: Database insertion time

### Sample Queries

```sql
-- Get all NYC EFAP data
SELECT * FROM scraped_data 
WHERE scraper_id = 'nyc_efap_programs'
ORDER BY timestamp DESC;

-- Get job counts by scraper
SELECT scraper_id, COUNT(*) as job_count 
FROM scraped_data 
GROUP BY scraper_id;

-- Get data for specific date range
SELECT * FROM scraped_data 
WHERE date BETWEEN '2025-07-01' AND '2025-07-23';

-- Get latest entry per scraper
SELECT DISTINCT ON (scraper_id) *
FROM scraped_data
ORDER BY scraper_id, timestamp DESC;
```

## Security Considerations

1. **SSH Keys**: Ensure proper SSH key setup for Git operations
2. **Repository Access**: Use read-only deploy keys when possible
3. **Data Filtering**: Consider filtering sensitive data before sync
4. **Rate Limiting**: Be mindful of Git hosting rate limits

## Troubleshooting

### Common Issues

**Permission Denied**
```bash
# Fix: Ensure SSH key is added
ssh-add ~/.ssh/id_rsa
```

**Repository Not Found**
```bash
# Fix: Check DATA_REPO_URL is correct
# Fix: Ensure you have repository access
```

**No Space Left**
```bash
# Fix: Clean old data before sync
find outputs/daily -mtime +30 -delete
```

## Best Practices

1. **Regular Syncs**: Run frequently to avoid large commits
2. **Monitor Disk Space**: Both source and destination
3. **Backup Important Data**: Before major syncs
4. **Test Locally First**: Use `PUSH_TO_REMOTE=false`
5. **Use Deploy Keys**: For automated systems

## Integration with Data Consumers

The synchronized data repository can be:

1. **Cloned by researchers**: For offline analysis
2. **Accessed via GitHub API**: For programmatic access
3. **Downloaded as archives**: Via GitHub releases
4. **Queried via SQLite**: For complex analysis
5. **Monitored for changes**: Via Git webhooks

## Future Enhancements

1. **Incremental SQLite updates**: Instead of full rebuild
2. **Data compression**: For older entries
3. **Multiple format exports**: CSV, Parquet, etc.
4. **API endpoint generation**: Static JSON API
5. **Data validation**: Before sync
6. **Differential sync**: Only changed files