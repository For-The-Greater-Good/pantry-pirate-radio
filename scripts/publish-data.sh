#!/bin/bash
# Master script for publishing data to the data repository
# This script:
# 1. Organizes recorder output files
# 2. Syncs files to data repository
# 3. Uses replay tool to rebuild database
# 4. Runs datasette exporter

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/outputs}"
DATA_REPO_PATH="${DATA_REPO_PATH:-$PROJECT_ROOT/../HAARRRvest}"
DATA_REPO_URL="${DATA_REPO_URL:-git@github.com:For-The-Greater-Good/HAARRRvest.git}"
SQLITE_OUTPUT="${SQLITE_OUTPUT:-$DATA_REPO_PATH/sqlite/pantry_pirate_radio.sqlite}"
DAYS_TO_SYNC="${DAYS_TO_SYNC:-7}"
REBUILD_DATABASE="${REBUILD_DATABASE:-true}"
EXPORT_DATASETTE="${EXPORT_DATASETTE:-true}"
PUSH_TO_REMOTE="${PUSH_TO_REMOTE:-true}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Check dependencies
check_dependencies() {
    log "Checking dependencies..."

    # Check for required commands
    for cmd in git python3 rsync; do
        if ! command -v $cmd &> /dev/null; then
            error "$cmd is required but not installed"
            exit 1
        fi
    done

    # Check for Python environment
    if [ ! -d "$PROJECT_ROOT/.virtualenvs" ] && [ ! -f "$PROJECT_ROOT/.venv/bin/python" ]; then
        if ! command -v poetry &> /dev/null; then
            error "Poetry is required but not installed"
            exit 1
        fi
    fi

    # Check database connection
    if [ -z "$DATABASE_URL" ]; then
        error "DATABASE_URL environment variable not set"
        exit 1
    fi

    log "All dependencies satisfied"
}

# Step 1: Organize files (already done by recorder, but verify structure)
organize_files() {
    log "Step 1: Verifying file organization..."

    if [ ! -d "$OUTPUT_DIR" ]; then
        error "Output directory $OUTPUT_DIR does not exist"
        exit 1
    fi

    # Count files in new structure
    daily_count=$(find "$OUTPUT_DIR/daily" -name "*.json" 2>/dev/null | wc -l || echo 0)
    latest_count=$(find "$OUTPUT_DIR/latest" -name "*.json" 2>/dev/null | wc -l || echo 0)

    info "Found $daily_count daily files and $latest_count latest symlinks"

    # If we have old flat structure files, organize them
    flat_files=$(find "$OUTPUT_DIR" -maxdepth 1 -name "*.json" 2>/dev/null | wc -l || echo 0)
    if [ $flat_files -gt 0 ]; then
        warn "Found $flat_files files in old flat structure. Consider migrating them."
    fi

    log "File organization verified"
}

# Step 2: Sync to data repository
sync_to_repo() {
    log "Step 2: Syncing to data repository..."

    # Use the existing sync script
    if [ -f "$SCRIPT_DIR/sync-data-repo.sh" ]; then
        # Export variables for the sync script
        export SOURCE_DIR="$OUTPUT_DIR"
        export DATA_REPO_PATH="$DATA_REPO_PATH"
        export DATA_REPO_URL="$DATA_REPO_URL"
        export DAYS_TO_SYNC="$DAYS_TO_SYNC"
        export PUSH_TO_REMOTE="$PUSH_TO_REMOTE"
        export GENERATE_SQLITE="false"  # We'll generate it separately with datasette

        "$SCRIPT_DIR/sync-data-repo.sh"
    else
        error "sync-data-repo.sh not found in $SCRIPT_DIR"
        exit 1
    fi

    log "Data repository sync completed"
}

# Step 3: Rebuild database using replay tool
rebuild_database() {
    if [ "$REBUILD_DATABASE" != "true" ]; then
        info "Skipping database rebuild (REBUILD_DATABASE=false)"
        return
    fi

    log "Step 3: Rebuilding database from recorded data..."

    cd "$PROJECT_ROOT"

    # Use poetry run instead of activating virtual environment
    # This avoids permission issues with the activate script

    # Run replay tool on the synced data
    info "Running replay tool on daily data..."

    # Process last N days of data
    for i in $(seq 0 $((DAYS_TO_SYNC - 1))); do
        DATE=$(date -d "$i days ago" +%Y-%m-%d 2>/dev/null || date -v -${i}d +%Y-%m-%d)
        DAILY_DIR="$OUTPUT_DIR/daily/$DATE"

        if [ -d "$DAILY_DIR" ]; then
            info "Processing data for $DATE..."
            poetry run python -m app.replay --directory "$DAILY_DIR" --verbose || {
                warn "Failed to process some files for $DATE"
            }
        fi
    done

    log "Database rebuild completed"
}

# Step 4: Export to SQLite using datasette
export_datasette() {
    if [ "$EXPORT_DATASETTE" != "true" ]; then
        info "Skipping datasette export (EXPORT_DATASETTE=false)"
        return
    fi

    log "Step 4: Exporting database to SQLite for Datasette..."

    cd "$PROJECT_ROOT"

    # Ensure output directory exists
    mkdir -p "$(dirname "$SQLITE_OUTPUT")"

    # Use poetry run for Python commands
    # This avoids permission issues with virtual environment activation

    # Run the datasette exporter
    info "Exporting to $SQLITE_OUTPUT..."
    poetry run python -m app.datasette.exporter --output "$SQLITE_OUTPUT" || {
        error "Failed to export database to SQLite"
        exit 1
    }

    # Generate metadata for datasette
    cat > "$DATA_REPO_PATH/sqlite/metadata.json" << EOF
{
  "title": "Pantry Pirate Radio Food Resources",
  "description": "Open data from food resource aggregation system",
  "license": "MIT",
  "license_url": "https://github.com/For-The-Greater-Good/pantry-pirate-radio/blob/main/LICENSE",
  "source": "Pantry Pirate Radio",
  "source_url": "https://github.com/For-The-Greater-Good/pantry-pirate-radio",
  "databases": {
    "pantry_pirate_radio": {
      "description": "Food resource locations following HSDS specification",
      "tables": {
        "organizations": {
          "description": "Organizations providing food assistance"
        },
        "locations": {
          "description": "Physical locations of food resources"
        },
        "services": {
          "description": "Services offered by organizations"
        },
        "service_at_locations": {
          "description": "Links between services and locations"
        }
      }
    }
  }
}
EOF

    log "SQLite export completed"
}

# Step 5: Commit and push data repository changes
finalize_sync() {
    log "Step 5: Finalizing data repository..."

    cd "$DATA_REPO_PATH"

    # Add all changes
    git add -A

    # Check if there are changes
    if git diff --staged --quiet; then
        info "No changes to commit in data repository"
    else
        # Generate commit message with statistics
        STATS=$(cat << EOF
Data update $(date +'%Y-%m-%d %H:%M:%S')

Statistics:
- Days synced: $DAYS_TO_SYNC
- Database rebuilt: $REBUILD_DATABASE
- Datasette export: $EXPORT_DATASETTE

Changes:
$(git diff --staged --stat)
EOF
)

        git commit -m "$STATS"

        if [ "$PUSH_TO_REMOTE" = "true" ]; then
            log "Pushing to remote repository..."
            git push origin main || {
                error "Failed to push to remote repository"
                exit 1
            }
        else
            info "Skipping push to remote (PUSH_TO_REMOTE=false)"
        fi
    fi

    log "Data repository finalized"
}

# Setup interactive datasette interface
setup_datasette_interface() {
    log "Setting up interactive Datasette interface..."

    # Copy the template HTML file
    if [ -f "$SCRIPT_DIR/datasette-lite-template.html" ]; then
        cp "$SCRIPT_DIR/datasette-lite-template.html" "$DATA_REPO_PATH/index.html"
        info "Created index.html for GitHub Pages"
    fi

    # Create a simple redirect for explore.html
    cat > "$DATA_REPO_PATH/explore.html" << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Redirecting to Explorer...</title>
    <meta http-equiv="refresh" content="0; url=index.html">
</head>
<body>
    <p>Redirecting to the data explorer...</p>
</body>
</html>
EOF

    log "Interactive interface files created"
}

# Generate summary report
generate_report() {
    log "Generating summary report..."

    REPORT_FILE="$DATA_REPO_PATH/LAST_UPDATE.md"

    cat > "$REPORT_FILE" << EOF
# Last Update Report

**Generated:** $(date)
**Script Version:** 1.0.0

## Configuration
- Days synced: $DAYS_TO_SYNC
- Database rebuilt: $REBUILD_DATABASE
- Datasette export: $EXPORT_DATASETTE
- Pushed to remote: $PUSH_TO_REMOTE

## Data Summary
$(cd "$DATA_REPO_PATH" && find daily -name "*.json" | wc -l) JSON files
$(cd "$DATA_REPO_PATH" && du -sh daily 2>/dev/null | cut -f1 || echo "N/A") total size

## SQLite Database
$(if [ -f "$SQLITE_OUTPUT" ]; then
    echo "- Size: $(du -h "$SQLITE_OUTPUT" | cut -f1)"
    echo "- Tables: $(sqlite3 "$SQLITE_OUTPUT" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "N/A")"
else
    echo "Not generated"
fi)

## Recent Activity
$(cd "$DATA_REPO_PATH" && find daily -name "*.json" -mtime -1 | wc -l) files updated in last 24 hours

## Next Steps
1. View data at: https://github.com/For-The-Greater-Good/pantry-pirate-radio-data
2. Explore with Datasette: \`datasette $SQLITE_OUTPUT\`
3. Query the database: \`sqlite3 $SQLITE_OUTPUT\`
EOF

    info "Report saved to $REPORT_FILE"
}

# Main execution
main() {
    log "Starting data publication pipeline..."

    # Change to project root
    cd "$PROJECT_ROOT"

    # Check dependencies
    check_dependencies

    # Execute steps
    organize_files
    sync_to_repo
    rebuild_database
    export_datasette
    setup_datasette_interface
    finalize_sync
    generate_report

    log "Data publication pipeline completed successfully!"

    # Show final statistics
    echo
    echo -e "${GREEN}=== Publication Summary ===${NC}"
    echo -e "Data repository: ${BLUE}$DATA_REPO_PATH${NC}"
    echo -e "SQLite database: ${BLUE}$SQLITE_OUTPUT${NC}"
    echo -e "Days synced: ${BLUE}$DAYS_TO_SYNC${NC}"
    echo
    echo -e "${GREEN}To explore the data:${NC}"
    echo "1. cd $DATA_REPO_PATH"
    echo "2. datasette $SQLITE_OUTPUT"
    echo
}

# Handle script arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --days)
            DAYS_TO_SYNC="$2"
            shift 2
            ;;
        --no-rebuild)
            REBUILD_DATABASE="false"
            shift
            ;;
        --no-export)
            EXPORT_DATASETTE="false"
            shift
            ;;
        --no-push)
            PUSH_TO_REMOTE="false"
            shift
            ;;
        --data-repo)
            DATA_REPO_PATH="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo
            echo "Options:"
            echo "  --days N          Number of days to sync (default: 7)"
            echo "  --no-rebuild      Skip database rebuild"
            echo "  --no-export       Skip datasette export"
            echo "  --no-push         Don't push to remote repository"
            echo "  --data-repo PATH  Path to data repository"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run main function
main