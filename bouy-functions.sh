#!/bin/bash
# Bouy Functions - Extracted functions for testing
# This file contains only the functions from bouy script, without the main execution logic

# Output functions for programmatic mode
output() {
    local level="$1"
    local message="$2"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    if [ $QUIET -eq 1 ] && [ "$level" != "error" ] && [ "$level" != "result" ]; then
        return
    fi

    if [ $JSON_OUTPUT -eq 1 ]; then
        # Escape quotes in message for JSON
        message="${message//\"/\\\"}"
        echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}"
    elif [ $PROGRAMMATIC_MODE -eq 1 ]; then
        echo "[$timestamp] [$level] $message" >&2
    elif [ "$level" = "result" ]; then
        # Results always go to stdout
        echo "$message"
    else
        # Normal mode - colored output to stderr
        if [ $NO_COLOR -eq 0 ]; then
            case "$level" in
                error)
                    echo -e "\033[31m[ERROR]\033[0m $message" >&2
                    ;;
                warning)
                    echo -e "\033[33m[WARNING]\033[0m $message" >&2
                    ;;
                info)
                    echo -e "\033[34m[INFO]\033[0m $message" >&2
                    ;;
                success)
                    echo -e "\033[32m[SUCCESS]\033[0m $message" >&2
                    ;;
                *)
                    echo "$message" >&2
                    ;;
            esac
        else
            echo "[$level] $message" >&2
        fi
    fi
}

# Parse environment mode
parse_mode() {
    local mode="dev"
    for arg in "$@"; do
        case $arg in
            --dev)
                mode="dev"
                ;;
            --prod)
                mode="prod"
                ;;
            --test)
                mode="test"
                ;;
            --with-init)
                COMPOSE_FILES="$COMPOSE_FILES -f .docker/compose/docker-compose.with-init.yml"
                ;;
        esac
    done

    case $mode in
        dev)
            COMPOSE_FILES="$COMPOSE_FILES -f .docker/compose/docker-compose.dev.yml"
            ;;
        prod)
            COMPOSE_FILES="$COMPOSE_FILES -f .docker/compose/docker-compose.prod.yml"
            ;;
        test)
            COMPOSE_FILES="$COMPOSE_FILES -f .docker/compose/docker-compose.test.yml"
            ;;
    esac
}

# Helper function to check database schema
check_database_schema() {
    local db_name="${1:-pantry_pirate_radio}"
    output info "Checking database schema in $db_name..."

    # Check if record_version table exists (indicates schema is initialized)
    if $COMPOSE_CMD $COMPOSE_FILES exec -T db psql -U postgres -d "$db_name" -c "SELECT 1 FROM record_version LIMIT 1;" >/dev/null 2>&1; then
        output success "Database schema is initialized"
        return 0
    else
        output warning "Database schema not initialized"
        return 1
    fi
}

# Helper function to check Redis connectivity
check_redis_connectivity() {
    output info "Checking Redis connectivity..."

    if $COMPOSE_CMD $COMPOSE_FILES exec -T cache redis-cli ping >/dev/null 2>&1; then
        output success "Redis is accessible"
        return 0
    else
        output error "Redis is not accessible"
        return 1
    fi
}

# Helper function to check database connectivity
check_database_connectivity() {
    output info "Checking database connectivity..."

    if $COMPOSE_CMD $COMPOSE_FILES exec -T db pg_isready -U postgres >/dev/null 2>&1; then
        output success "Database is accessible"
        return 0
    else
        output error "Database is not accessible"
        return 1
    fi
}

# Helper function to check content store
check_content_store() {
    output info "Checking content store..."

    if $COMPOSE_CMD $COMPOSE_FILES exec -T worker test -d "/app/data/content_store" 2>/dev/null && \
       $COMPOSE_CMD $COMPOSE_FILES exec -T worker test -f "/app/data/content_store/content_store.db" 2>/dev/null; then
        output success "Content store is configured"
        return 0
    else
        output warning "Content store not configured"
        return 1
    fi
}

# Helper function to check service status
check_service_status() {
    local service="$1"
    if $COMPOSE_CMD $COMPOSE_FILES ps --format json "$service" 2>/dev/null | grep -q '"State":"running"'; then
        return 0
    else
        return 1
    fi
}

# Validate scraper name
validate_scraper_name() {
    local name="$1"
    # Only allow alphanumeric, underscore, and dash
    if [[ "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        return 0
    else
        return 1
    fi
}

# Helper function to check Docker
check_docker() {
    if ! which docker >/dev/null 2>&1; then
        output error "Docker is not installed or not in PATH"
        return 1
    fi

    if ! docker version >/dev/null 2>&1; then
        output error "Docker daemon is not running"
        return 1
    fi

    return 0
}

# Helper function to wait for database to be ready
wait_for_database() {
    output info "Waiting for database to be ready..."
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if $COMPOSE_CMD $COMPOSE_FILES exec -T db pg_isready -U postgres >/dev/null 2>&1; then
            output success "Database is ready!"
            return 0
        fi
        attempt=$((attempt + 1))
        if [ $attempt -eq $max_attempts ]; then
            output error "Database failed to become ready"
            return 1
        fi
        echo "Waiting for database... (attempt $attempt/$max_attempts)"
        sleep 2
    done
}

# Helper function to check if directory exists and is writable
check_directory_writable() {
    local dir_path="$1"
    local service="$2"

    output info "Checking directory: $dir_path"

    # Check if directory exists in container
    if $COMPOSE_CMD $COMPOSE_FILES exec -T "$service" test -d "$dir_path" 2>/dev/null; then
        # Check if writable
        if $COMPOSE_CMD $COMPOSE_FILES exec -T "$service" test -w "$dir_path" 2>/dev/null; then
            output success "Directory is writable: $dir_path"
            return 0
        else
            output error "Directory is not writable: $dir_path"
            return 1
        fi
    else
        output warning "Directory does not exist: $dir_path"
        # Try to create it
        if $COMPOSE_CMD $COMPOSE_FILES exec -T "$service" mkdir -p "$dir_path" 2>/dev/null; then
            output success "Created directory: $dir_path"
            return 0
        else
            output error "Failed to create directory: $dir_path"
            return 1
        fi
    fi
}

# Helper function to initialize database schema
init_database_schema() {
    local db_name="${1:-pantry_pirate_radio}"
    output info "Initializing database schema in $db_name..."

    for init_script in ./init-scripts/*.sql; do
        if [ -f "$init_script" ]; then
            script_name=$(basename "$init_script")
            output info "Running $script_name..."
            $COMPOSE_CMD $COMPOSE_FILES exec -T db psql -U postgres -d "$db_name" -f "/docker-entrypoint-initdb.d/$script_name" 2>&1 | grep -v "NOTICE:" || true
        fi
    done
    output success "Database schema initialized"
}

# Helper function to check git configuration
check_git_config() {
    local service="$1"
    output info "Checking git configuration..."

    # Check git user.name
    if ! $COMPOSE_CMD $COMPOSE_FILES exec -T "$service" git config --global user.name >/dev/null 2>&1; then
        output warning "Git user.name not set, using default"
        $COMPOSE_CMD $COMPOSE_FILES exec -T "$service" git config --global user.name "Pantry Pirate Radio" || true
    fi

    # Check git user.email
    if ! $COMPOSE_CMD $COMPOSE_FILES exec -T "$service" git config --global user.email >/dev/null 2>&1; then
        output warning "Git user.email not set, using default"
        $COMPOSE_CMD $COMPOSE_FILES exec -T "$service" git config --global user.email "pantry-pirate-radio@example.com" || true
    fi

    output success "Git configuration verified"
}