#!/bin/bash
# Health check script to verify database is ready with data
# Used by Docker health checks and service dependencies

set -e

# Configuration
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-pantry_pirate_radio}"
DB_NAME="${POSTGRES_DB:-pantry_pirate_radio}"
PGPASSWORD="${POSTGRES_PASSWORD}"
HEALTH_CHECK_FILE="/tmp/db-init-healthy"
TIMEOUT="${DB_READY_TIMEOUT:-300}"  # 5 minutes default

# Export for pg tools
export PGPASSWORD

# Function to check if db-init has marked itself as healthy
check_init_health_file() {
    if [ -f "$HEALTH_CHECK_FILE" ]; then
        return 0
    fi
    return 1
}

# Function to check database connectivity and data
check_database() {
    # First check if we can connect
    if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        return 1
    fi

    # Check if core tables exist
    local tables_exist=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('organization', 'location', 'service');" 2>/dev/null || echo "0")

    if [ "$tables_exist" -ne "3" ]; then
        return 1
    fi

    return 0
}

# Main health check
main() {
    # If called with "init" argument, check the init health file
    if [ "$1" = "init" ]; then
        check_init_health_file
        exit $?
    fi

    # Otherwise, do a full database check
    check_database
    exit $?
}

# If script is called with "wait" argument, wait for readiness
if [ "$1" = "wait" ]; then
    echo "Waiting for database to be ready (timeout: ${TIMEOUT}s)..."

    start_time=$(date +%s)

    while true; do
        if check_init_health_file && check_database; then
            echo "Database is ready!"
            exit 0
        fi

        current_time=$(date +%s)
        elapsed=$((current_time - start_time))

        if [ $elapsed -ge $TIMEOUT ]; then
            echo "Timeout waiting for database to be ready after ${TIMEOUT}s"
            exit 1
        fi

        echo -n "."
        sleep 2
    done
else
    # Run main health check
    main "$@"
fi