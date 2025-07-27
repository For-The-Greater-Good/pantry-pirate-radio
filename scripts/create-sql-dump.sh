#!/bin/bash
# Create SQL dump of the Pantry Pirate Radio database
# This script creates a compressed PostgreSQL dump for fast database initialization

set -e

# Configuration
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-pantry_pirate_radio}"
DB_NAME="${POSTGRES_DB:-pantry_pirate_radio}"
PGPASSWORD="${POSTGRES_PASSWORD}"
OUTPUT_DIR="${SQL_DUMP_DIR:-./sql_dumps}"

# Export for pg tools
export PGPASSWORD

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
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

# Function to check if PostgreSQL is accessible
check_postgres() {
    log "Checking PostgreSQL connection..."

    if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        error "Cannot connect to PostgreSQL at $DB_HOST:$DB_PORT"
        error "Please ensure database is running and credentials are correct"
        exit 1
    fi

    log "PostgreSQL connection successful"
}

# Function to get database size
get_db_size() {
    local size=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT pg_database_size('$DB_NAME');" 2>/dev/null || echo "0")
    echo $((size / 1024 / 1024)) # Return size in MB
}

# Function to get record count
get_record_count() {
    local count=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM organization;" 2>/dev/null || echo "0")
    echo $count
}

# Main function
main() {
    log "Starting SQL dump creation for Pantry Pirate Radio database"

    # Check PostgreSQL connection
    check_postgres

    # Get database info
    local db_size_mb=$(get_db_size)
    local record_count=$(get_record_count)

    log "Database size: ${db_size_mb} MB"
    log "Organization records: ${record_count}"

    # Load or check ratchet file
    local ratchet_file="$OUTPUT_DIR/.record_count_ratchet"
    local max_known_count=0

    if [ -f "$ratchet_file" ]; then
        # Parse JSON ratchet file
        max_known_count=$(python3 -c "import json; print(json.load(open('$ratchet_file'))['max_record_count'])" 2>/dev/null || echo "0")
        log "Previous maximum record count: $max_known_count"
    fi

    # Safety check with ratcheting threshold
    local allow_empty="${ALLOW_EMPTY_SQL_DUMP:-false}"
    local ratchet_percentage="${SQL_DUMP_RATCHET_PERCENTAGE:-0.9}"

    if [ "$max_known_count" -gt 0 ]; then
        # Calculate threshold as percentage of max known count
        local threshold=$(python3 -c "print(int($max_known_count * $ratchet_percentage))")

        if [ "$record_count" -lt "$threshold" ]; then
            warn "Database has only $record_count records"
            warn "This is below $(python3 -c "print($ratchet_percentage * 100)")% of maximum known count ($max_known_count)"
            warn "Threshold: $threshold records"

            if [ "$allow_empty" != "true" ]; then
                error "Refusing to create dump to prevent data loss"
                error "To override, set ALLOW_EMPTY_SQL_DUMP=true"
                exit 1
            else
                warn "ALLOW_EMPTY_SQL_DUMP is set, proceeding despite low record count"
            fi
        fi
    else
        # No ratchet file - use minimum threshold
        local min_threshold="${SQL_DUMP_MIN_RECORDS:-100}"

        if [ "$record_count" -lt "$min_threshold" ]; then
            warn "Database has only $record_count records (minimum: $min_threshold)"

            # Check if we have existing dumps (legacy check)
            if ls "$OUTPUT_DIR"/pantry_pirate_radio_*.sql >/dev/null 2>&1; then
                error "Existing SQL dumps found but no ratchet file"

                if [ "$allow_empty" != "true" ]; then
                    error "Refusing to create dump. To override, set ALLOW_EMPTY_SQL_DUMP=true"
                    exit 1
                else
                    warn "ALLOW_EMPTY_SQL_DUMP is set, proceeding despite low record count"
                fi
            else
                warn "Creating initial dump with $record_count records"
            fi
        fi
    fi

    # Update ratchet if current count is higher
    if [ "$record_count" -gt "$max_known_count" ]; then
        log "New record count high water mark: $record_count"
        python3 -c "
import json
from datetime import datetime
data = {
    'max_record_count': $record_count,
    'updated_at': datetime.now().isoformat(),
    'updated_by': 'create-sql-dump.sh'
}
with open('$ratchet_file', 'w') as f:
    json.dump(data, f, indent=2)
"
    fi

    # Create output directory
    mkdir -p "$OUTPUT_DIR"

    # Generate filename with timestamp
    local dump_filename="pantry_pirate_radio_$(date +'%Y-%m-%d_%H-%M-%S').sql"
    local dump_path="$OUTPUT_DIR/$dump_filename"

    log "Creating SQL dump: $dump_path"
    log "This may take a few minutes..."

    # Create plain SQL dump (uncompressed for git tracking)
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --no-owner \
        --no-privileges \
        --if-exists \
        --clean \
        --verbose 2>&1 > "$dump_path" | while IFS= read -r line; do
        # Show progress
        if echo "$line" | grep -E "(dumping|writing|archiving)" >/dev/null; then
            echo "  $line"
        fi
    done; then
        # Get final file size
        local file_size_mb=$(stat -f%z "$dump_path" 2>/dev/null || stat -c%s "$dump_path" 2>/dev/null)
        file_size_mb=$((file_size_mb / 1024 / 1024))

        log "SQL dump created successfully!"
        log "File: $dump_path"
        log "Size: ${file_size_mb} MB"

        # Create/update latest symlink
        local latest_link="$OUTPUT_DIR/latest.sql"
        if [ -L "$latest_link" ] || [ -e "$latest_link" ]; then
            rm -f "$latest_link"
        fi
        ln -s "$(basename "$dump_path")" "$latest_link"
        log "Updated latest.sql symlink"

        echo
        log "To restore this dump to a new database:"
        log "  1. Create empty database: createdb -h HOST -U USER new_database"
        log "  2. Restore: psql -h HOST -U USER -d new_database < $dump_path"

    else
        error "Failed to create SQL dump!"
        exit 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo
            echo "Create a compressed SQL dump of the Pantry Pirate Radio database"
            echo
            echo "Options:"
            echo "  -h, --help     Show this help message"
            echo "  -o, --output   Output directory (default: ./sql_dumps)"
            echo
            echo "Environment variables:"
            echo "  POSTGRES_HOST     Database host (default: localhost)"
            echo "  POSTGRES_PORT     Database port (default: 5432)"
            echo "  POSTGRES_USER     Database user (default: pantry_pirate_radio)"
            echo "  POSTGRES_DB       Database name (default: pantry_pirate_radio)"
            echo "  POSTGRES_PASSWORD Database password (required)"
            exit 0
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            error "Unknown option: $1"
            echo "Use -h for help"
            exit 1
            ;;
    esac
done

# Check for required password
if [ -z "$PGPASSWORD" ]; then
    error "POSTGRES_PASSWORD environment variable is required"
    exit 1
fi

# Run main function
main