#!/bin/bash
# Example script for syncing recorder outputs to a separate data repository
# This demonstrates how to sync the organized data structure to a Git-based data repository

set -e

# Configuration
SOURCE_DIR="${SOURCE_DIR:-outputs}"
DATA_REPO_PATH="${DATA_REPO_PATH:-../HAARRRvest}"
DATA_REPO_URL="${DATA_REPO_URL:-git@github.com:For-The-Greater-Good/HAARRRvest.git}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Data update from recorder service}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting data repository sync...${NC}"

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}Error: Source directory $SOURCE_DIR does not exist${NC}"
    exit 1
fi

# Clone or update data repository
if [ ! -d "$DATA_REPO_PATH" ]; then
    echo -e "${YELLOW}Cloning data repository...${NC}"
    git clone "$DATA_REPO_URL" "$DATA_REPO_PATH"
else
    echo -e "${YELLOW}Updating existing data repository...${NC}"
    cd "$DATA_REPO_PATH"
    git pull origin main
    cd - > /dev/null
fi

# Create necessary directories in data repo
mkdir -p "$DATA_REPO_PATH/daily"
mkdir -p "$DATA_REPO_PATH/sqlite"

# Sync daily data (last 7 days by default)
echo -e "${GREEN}Syncing daily data...${NC}"
DAYS_TO_SYNC="${DAYS_TO_SYNC:-7}"
for i in $(seq 0 $((DAYS_TO_SYNC - 1))); do
    DATE=$(date -d "$i days ago" +%Y-%m-%d 2>/dev/null || date -v -${i}d +%Y-%m-%d)
    if [ -d "$SOURCE_DIR/daily/$DATE" ]; then
        echo "  Syncing $DATE..."
        rsync -av --delete "$SOURCE_DIR/daily/$DATE/" "$DATA_REPO_PATH/daily/$DATE/"
    fi
done

# Handle latest symlink (points to most recent date directory)
echo -e "${GREEN}Creating latest symlink...${NC}"
if [ -L "$SOURCE_DIR/latest" ]; then
    # Get the target of the symlink (should be daily/YYYY-MM-DD)
    latest_target=$(readlink "$SOURCE_DIR/latest")

    # Create a symlink in the data repo
    cd "$DATA_REPO_PATH"
    rm -rf latest  # Remove old symlink or directory if exists
    ln -s "$latest_target" latest
    cd - > /dev/null

    echo "Created latest symlink pointing to: $latest_target"
elif [ -d "$SOURCE_DIR/latest" ]; then
    # Fallback: if latest is a directory (old structure), find the most recent date
    latest_date=$(ls -1 "$DATA_REPO_PATH/daily" | sort -r | head -1)
    if [ -n "$latest_date" ]; then
        cd "$DATA_REPO_PATH"
        rm -rf latest
        ln -s "daily/$latest_date" latest
        cd - > /dev/null
        echo "Created latest symlink pointing to: daily/$latest_date"
    fi
fi

# Generate SQLite database if requested
if [ "${GENERATE_SQLITE:-false}" = "true" ]; then
    echo -e "${GREEN}Generating SQLite database...${NC}"
    python3 - << 'EOF'
import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime

data_repo = os.environ.get('DATA_REPO_PATH', '../pantry-pirate-radio-data')
db_path = Path(data_repo) / 'sqlite' / 'food_resources.db'
db_path.parent.mkdir(exist_ok=True)

# Create/connect to database
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS scraped_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE,
    scraper_id TEXT,
    date TEXT,
    timestamp TEXT,
    data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_summaries (
    date TEXT PRIMARY KEY,
    total_jobs INTEGER,
    summary_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Index for faster queries
cursor.execute('CREATE INDEX IF NOT EXISTS idx_scraper_date ON scraped_data(scraper_id, date)')

# Import daily data
daily_path = Path(data_repo) / 'daily'
for date_dir in sorted(daily_path.iterdir()):
    if date_dir.is_dir():
        date_str = date_dir.name

        # Import summary
        summary_file = date_dir / 'summary.json'
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
                cursor.execute('''
                    INSERT OR REPLACE INTO daily_summaries (date, total_jobs, summary_data)
                    VALUES (?, ?, ?)
                ''', (date_str, summary['total_jobs'], json.dumps(summary)))

        # Import scraper data
        scrapers_dir = date_dir / 'scrapers'
        if scrapers_dir.exists():
            for scraper_dir in scrapers_dir.iterdir():
                if scraper_dir.is_dir():
                    scraper_id = scraper_dir.name
                    for json_file in scraper_dir.glob('*.json'):
                        with open(json_file) as f:
                            data = json.load(f)
                            cursor.execute('''
                                INSERT OR REPLACE INTO scraped_data
                                (job_id, scraper_id, date, timestamp, data)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (
                                data.get('job_id'),
                                scraper_id,
                                date_str,
                                data.get('job', {}).get('created_at', ''),
                                json.dumps(data)
                            ))

conn.commit()
conn.close()
print(f"SQLite database created at {db_path}")
EOF
fi

# Create README if it doesn't exist
if [ ! -f "$DATA_REPO_PATH/README.md" ]; then
    echo -e "${GREEN}Creating README...${NC}"
    cat > "$DATA_REPO_PATH/README.md" << 'EOF'
# HAARRRvest 🏴‍☠️

A treasure trove of food resource data harvested by Pantry Pirate Radio.

## 🔍 Explore the Data Interactively

### [**Launch Interactive Explorer →**](https://for-the-greater-good.github.io/HAARRRvest/)

Explore the data directly in your browser with SQL queries, no installation required!

## Directory Structure

```
daily/
├── YYYY-MM-DD/
│   ├── summary.json          # Daily summary of all jobs
│   ├── scrapers/
│   │   └── {scraper_id}/     # Scraper-specific results
│   │       └── {job_id}.json # Individual job results
│   └── processed/            # LLM-processed results
│       └── {job_id}.json

latest -> daily/YYYY-MM-DD    # Symlink to most recent date directory

sqlite/
└── food_resources.db         # SQLite database (if generated)
```

## Data Format

Each job result contains:
- Job metadata (ID, timestamp, scraper info)
- Raw scraped data
- Processing status
- Any errors encountered

## Usage

### Accessing Latest Data
The `latest` symlink points to the most recent date directory containing all data from that day.

### Historical Data
The `daily/` directory contains all historical data organized by date.

### SQLite Database
If generated, the SQLite database provides an easy way to query the data:

```sql
-- Get all data for a specific scraper
SELECT * FROM scraped_data WHERE scraper_id = 'nyc_efap_programs';

-- Get summary for a specific date
SELECT * FROM daily_summaries WHERE date = '2025-07-23';

-- Get recent scrapes
SELECT * FROM scraped_data ORDER BY timestamp DESC LIMIT 10;
```

## Update Schedule

This data is automatically synchronized from the main Pantry Pirate Radio system.
Check the commit history for update frequency.
EOF
fi

# Generate data statistics
echo -e "${GREEN}Generating statistics...${NC}"
cat > "$DATA_REPO_PATH/STATS.md" << EOF
# Data Repository Statistics

Generated: $(date)

## Summary
- Total days of data: $(find "$DATA_REPO_PATH/daily" -mindepth 1 -maxdepth 1 -type d | wc -l)
- Total JSON files: $(find "$DATA_REPO_PATH/daily" -name "*.json" | wc -l)
- Total size: $(du -sh "$DATA_REPO_PATH/daily" | cut -f1)

## Scrapers
$(find "$DATA_REPO_PATH/daily" -path "*/scrapers/*" -type d -mindepth 4 -maxdepth 4 |
  awk -F'/' '{print $(NF)}' | sort | uniq -c |
  awk '{printf "- %s: %d files\n", $2, $1}')

## Recent Updates
$(find "$DATA_REPO_PATH/daily" -name "*.json" -mtime -1 | wc -l) files updated in last 24 hours
$(find "$DATA_REPO_PATH/daily" -name "*.json" -mtime -7 | wc -l) files updated in last 7 days
EOF

# Commit and push changes
cd "$DATA_REPO_PATH"
git add -A

# Check if there are changes to commit
if git diff --staged --quiet; then
    echo -e "${YELLOW}No changes to commit${NC}"
else
    echo -e "${GREEN}Committing changes...${NC}"
    git commit -m "$COMMIT_MESSAGE

Updated: $(date)
Files changed: $(git diff --staged --name-only | wc -l)"

    if [ "${PUSH_TO_REMOTE:-true}" = "true" ]; then
        echo -e "${GREEN}Pushing to remote...${NC}"
        git push origin main
    fi
fi

echo -e "${GREEN}Sync completed successfully!${NC}"