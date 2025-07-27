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

# Function to check if data repo exists
check_data_repo() {
    if [ ! -d "$DATA_REPO_PATH" ]; then
        warn "HAARRRvest data repository not found at $DATA_REPO_PATH"
        warn "Skipping data population - database will start empty"
        return 1
    fi

    if [ ! -d "$DATA_REPO_PATH/daily" ]; then
        warn "No daily data directory found in HAARRRvest repository"
        warn "Skipping data population - database will start empty"
        return 1
    fi

    return 0
}

# Function to count existing records
count_records() {
    local count=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM organization;" 2>/dev/null || echo "0")
    echo $count
}

# Function to run replay for database population
run_replay() {
    log "Starting database population from HAARRRvest data..."

    # Check if we've already completed initialization
    if [ -f "$INIT_STATE_FILE" ]; then
        local last_run=$(cat "$INIT_STATE_FILE")
        log "Database was previously initialized on $last_run"

        local record_count=$(count_records)
        log "Current record count: $record_count organizations"

        if [ "$record_count" -gt "0" ]; then
            log "Database already contains data, skipping replay"
            return 0
        fi
    fi

    # Count files to process
    local total_files=$(find "$DATA_REPO_PATH/daily" -name "*.json" -type f | wc -l)
    log "Found $total_files JSON files in HAARRRvest repository"

    if [ "$total_files" -eq "0" ]; then
        warn "No JSON files found to process"
        return 0
    fi

    # Run replay with progress tracking
    log "Running replay utility to populate database..."
    log "This may take several minutes depending on data volume..."

    cd /app

    # Use Python unbuffered output for real-time progress
    export PYTHONUNBUFFERED=1

    # Run replay and capture output
    if python -m app.replay --directory "$DATA_REPO_PATH/daily" --pattern "*.json" 2>&1 | while IFS= read -r line; do
        echo "[REPLAY] $line"
    done; then
        log "Replay completed successfully!"

        # Mark initialization as complete
        date -u +"%Y-%m-%d %H:%M:%S UTC" > "$INIT_STATE_FILE"

        # Get final record count
        local final_count=$(count_records)
        log "Database now contains $final_count organizations"

        return 0
    else
        error "Replay failed!"
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
        # Step 4: Run replay to populate data
        if ! run_replay; then
            error "Database population failed"
            exit 1
        fi
    else
        log "Proceeding without data population"
    fi

    # Step 5: Mark as healthy
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