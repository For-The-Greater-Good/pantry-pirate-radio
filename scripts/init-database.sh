#!/bin/bash
# Database Initialization Script
# This script handles the complete database initialization including:
# 1. Waiting for PostgreSQL to be ready
# 2. Running the replay utility to populate data from HAARRRvest
# 3. Providing progress updates and health status

set -e

# Configuration
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-pantry_pirate_radio}"
DB_NAME="${POSTGRES_DB:-pantry_pirate_radio}"
PGPASSWORD="${POSTGRES_PASSWORD}"
DATA_REPO_PATH="${DATA_REPO_PATH:-/data-repo}"
INIT_STATE_FILE="/tmp/db-init-state"
HEALTH_CHECK_FILE="/tmp/db-init-healthy"
DAYS_TO_SYNC="${DB_INIT_DAYS_TO_SYNC:-90}"

# Export for pg tools
export PGPASSWORD

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARN:${NC} $1"
}

# Function to check if PostgreSQL is ready
wait_for_postgres() {
    log "Waiting for PostgreSQL to be ready..."

    until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
        echo -n "."
        sleep 1
    done

    echo ""
    log "PostgreSQL is ready!"
}

# Function to check if database has been initialized with schema
check_db_schema() {
    log "Checking database schema..."

    # Check if core tables exist
    TABLES_EXIST=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('organization', 'location', 'service');" 2>/dev/null || echo "0")

    if [ "$TABLES_EXIST" -eq "3" ]; then
        log "Database schema is initialized"
        return 0
    else
        error "Database schema not properly initialized. Found $TABLES_EXIST/3 expected tables"
        return 1
    fi
}

# Function to check and wait for data repo to be ready
check_data_repo() {
    if [ ! -d "$DATA_REPO_PATH/.git" ]; then
        log "HAARRRvest data repository not found at $DATA_REPO_PATH"
        log "Cloning HAARRRvest repository for database initialization..."
        
        # Get repository URL and token from environment
        local repo_url="${DATA_REPO_URL:-https://github.com/For-The-Greater-Good/HAARRRvest.git}"
        local repo_token="${DATA_REPO_TOKEN}"
        
        # Add token to URL if provided
        if [ -n "$repo_token" ] && [[ "$repo_url" == https://* ]]; then
            # Insert token into HTTPS URL
            repo_url=$(echo "$repo_url" | sed "s|https://|https://${repo_token}@|")
        fi
        
        # Create parent directory if needed
        mkdir -p "$(dirname "$DATA_REPO_PATH")"
        
        # Clone the repository
        if git clone "$repo_url" "$DATA_REPO_PATH"; then
            log "Successfully cloned HAARRRvest repository"
            # After successful clone, wait a moment for filesystem to settle
            sleep 2
            log "HAARRRvest repository is ready"
            return 0
        else
            warn "Failed to clone HAARRRvest repository"
            warn "Skipping data population - database will start empty"
            return 1
        fi
    else
        # Repository already exists
        log "HAARRRvest repository already exists, updating to latest..."
        
        # Enter the repository directory
        cd "$DATA_REPO_PATH"
        
        # Ensure we're on main branch
        if ! git checkout main 2>/dev/null; then
            warn "Failed to checkout main branch"
            warn "Repository may be in an inconsistent state"
            return 1
        fi
        
        # Pull latest changes
        log "Pulling latest changes from origin/main..."
        if git pull origin main; then
            log "Repository updated successfully"
        else
            warn "Failed to pull latest changes"
            warn "Continuing with existing repository state"
        fi
        
        # Return to original directory
        cd - >/dev/null
        
        # Wait for repository to be stable
        if /app/scripts/wait-for-repo-ready.sh; then
            log "HAARRRvest repository is ready"
            return 0
        else
            warn "Failed to verify repository is ready"
            warn "Skipping data population - database will start empty"
            return 1
        fi
    fi
}

# Function to count existing records
count_records() {
    local count=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM organization;" 2>/dev/null || echo "0")
    echo $count
}

# Function to restore from SQL dump
restore_from_sql_dump() {
    log "Looking for SQL dumps in HAARRRvest repository..."

    local sql_dumps_dir="$DATA_REPO_PATH/sql_dumps"
    if [ ! -d "$sql_dumps_dir" ]; then
        log "No sql_dumps directory found, will use JSON replay instead"
        return 1
    fi

    # Look for latest SQL dump
    local latest_dump="$sql_dumps_dir/latest.sql"
    if [ ! -f "$latest_dump" ]; then
        # Look for any SQL dump files
        local dump_files=$(find "$sql_dumps_dir" -name "pantry_pirate_radio_*.sql" -type f | sort -r)
        if [ -z "$dump_files" ]; then
            log "No SQL dump files found"
            return 1
        fi
        # Use the most recent dump
        latest_dump=$(echo "$dump_files" | head -n1)
    fi

    log "Found SQL dump: $(basename "$latest_dump")"

    # Get file size
    local file_size_mb=$(stat -f%z "$latest_dump" 2>/dev/null || stat -c%s "$latest_dump" 2>/dev/null)
    file_size_mb=$((file_size_mb / 1024 / 1024))
    log "SQL dump size: ${file_size_mb} MB"

    # Restore from SQL dump
    log "Restoring database from SQL dump..."
    log "This should take less than 5 minutes..."

    # Drop existing database and recreate
    log "Preparing database for restore..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || true
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" || {
        error "Failed to create database"
        return 1
    }

    # Restore using psql for plain SQL dumps
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" < "$latest_dump" 2>&1 | while IFS= read -r line; do
        # Filter out common warnings
        if echo "$line" | grep -E "(ERROR|FATAL|failed)" >/dev/null; then
            echo "[RESTORE] $line"
        fi
    done; then
        log "SQL dump restored successfully!"

        # Mark initialization as complete
        date -u +"%Y-%m-%d %H:%M:%S UTC" > "$INIT_STATE_FILE"

        # Get final record count
        local final_count=$(count_records)
        log "Database now contains $final_count organizations"

        return 0
    else
        error "SQL dump restore failed!"
        return 1
    fi
}


# Main initialization flow
main() {
    log "Starting database initialization..."

    # Remove old health check file
    rm -f "$HEALTH_CHECK_FILE"

    # Check if we should skip initialization (for CI/testing)
    if [ "${SKIP_DB_INIT}" = "true" ] || [ "${CI}" = "true" ]; then
        log "Skipping database initialization (SKIP_DB_INIT=true or CI=true)"
        touch "$HEALTH_CHECK_FILE"

        # Just wait for postgres and exit
        wait_for_postgres

        if check_db_schema; then
            log "Database schema verified - skipping data population for CI"
            # Keep container running for health checks
            while true; do
                sleep 30
            done
        else
            error "Database schema verification failed"
            exit 1
        fi
    fi

    # Step 1: Wait for PostgreSQL
    wait_for_postgres

    # Step 2: Verify schema
    if ! check_db_schema; then
        error "Database schema verification failed"
        exit 1
    fi

    # Step 3: Check if data repo exists
    if check_data_repo; then
        # Step 4: Restore from SQL dump
        log "Looking for SQL dump to restore..."
        if ! restore_from_sql_dump; then
            warn "No SQL dump available for database initialization"
            warn "To create a SQL dump, run the HAARRRvest publisher or use:"
            warn "  docker compose exec app bash /app/scripts/create-sql-dump.sh"
            log "Database will remain empty - populate it manually if needed"
        fi
    else
        log "Proceeding without data population"
    fi

    # Step 5: Sync content store from repository (replace local)
    if [ -d "$DATA_REPO_PATH/content-store" ]; then
        log "Found content store in repository"
        
        # Ensure the parent directory exists
        mkdir -p /data-repo
        
        # Remove existing local content store to ensure clean sync
        if [ -d "/data-repo/content-store" ]; then
            log "Removing existing local content store to sync from repository..."
            rm -rf /data-repo/content-store
        fi
        
        # Copy from repository (this is the source of truth)
        log "Syncing content store from repository..."
        cp -r "$DATA_REPO_PATH/content-store" /data-repo/
        
        # Verify the sync
        if [ -f "/data-repo/content-store/index.db" ]; then
            # Quick check of the synced content
            local entry_count=$(python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('/data-repo/content-store/index.db')
    cursor = conn.execute('SELECT COUNT(*) FROM content_index')
    print(cursor.fetchone()[0])
    conn.close()
except:
    print('0')
" 2>/dev/null || echo "0")
            log "Content store synced successfully with $entry_count entries"
        else
            log "Content store synced (no index.db found)"
        fi
    else
        log "No content store found in repository at $DATA_REPO_PATH/content-store"
    fi

    # Step 6: Mark as healthy
    touch "$HEALTH_CHECK_FILE"
    log "Database initialization complete!"

    # Keep container running for health checks
    log "Container will stay running for health check purposes..."

    # Simple loop to keep container alive
    while true; do
        sleep 30
        # Periodically verify database is still accessible
        if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
            error "Lost connection to database!"
            rm -f "$HEALTH_CHECK_FILE"
            exit 1
        fi
    done
}

# Run main function
main