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
        # Check if jq is available
        if command -v jq >/dev/null 2>&1; then
            # Use jq for proper JSON escaping
            echo '{}' | jq -c --arg ts "$timestamp" --arg lv "$level" --arg msg "$message" \
                '{timestamp: $ts, level: $lv, message: $msg}'
        else
            # Fallback to basic escaping with warning
            if [ "$JQ_WARNING_SHOWN" != "1" ]; then
                echo "[WARNING] jq is not installed. JSON output may be malformed. Install jq with: apt-get install jq (or brew install jq on macOS)" >&2
                export JQ_WARNING_SHOWN=1
            fi
            # Basic escaping - handle quotes, newlines, tabs, and backslashes
            message="${message//\\/\\\\}"
            message="${message//\"/\\\"}"
            message="${message//$'\n'/\\n}"
            message="${message//$'\t'/\\t}"
            echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}"
        fi
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

    maybe_add_passthrough_overlay
}

# Parse KEY=value lines from stdin, export valid ones, and record their names
# in BOUY_ENV_KEYS. Must be called WITHOUT a pipe (use <<< or < file) so the
# exports land in the current shell, not a subshell.
load_env_lines() {
    local key value
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        if [[ ! "$key" =~ ^[[:space:]]*# ]] && [[ -n "$key" ]]; then
            key=$(echo "$key" | xargs)
            if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
                # Trim only surrounding whitespace from the value so a
                # "KEY = value" line yields "value" while quotes/content
                # are preserved verbatim. Plain "KEY=value" is unaffected.
                value="${value#"${value%%[![:space:]]*}"}"
                value="${value%"${value##*[![:space:]]}"}"
                export "$key=$value"
                BOUY_ENV_KEYS="${BOUY_ENV_KEYS:+$BOUY_ENV_KEYS }$key"
            fi
        fi
    done
}

# Emit valueless `-e KEY` flags so docker run passes each var through from the
# current environment (used by the 1Password test path; no temp file needed).
build_env_flags() {
    local k
    for k in "$@"; do
        printf -- '-e %s ' "$k"
    done
}

# Determine the active environment from CLI args: explicit --prod/--test flag
# wins; otherwise the `test` command implies test mode; default dev.
detect_mode() {
    local mode="dev" arg
    for arg in "$@"; do
        case "$arg" in
            --prod) echo "prod"; return 0 ;;
            --test) echo "test"; return 0 ;;
        esac
    done
    if [ "$1" = "test" ]; then
        mode="test"
    fi
    echo "$mode"
}

# Map a mode to its on-disk override file (which always wins over 1Password).
override_file_for_mode() {
    case "$1" in
        test) echo ".env.test" ;;
        prod) echo ".env.prod" ;;
        *)    echo ".env" ;;
    esac
}

# Resolve the 1Password pointer into OP_ACCOUNT/OP_VAULT/OP_ITEM.
# Precedence: existing environment variable > config/op.conf > built-in default.
resolve_op_pointer() {
    local file_account="" file_vault="" file_item=""
    if [ -f config/op.conf ]; then
        # shellcheck disable=SC1091
        file_account=$(grep -E '^OP_ACCOUNT=' config/op.conf | cut -d= -f2-)
        file_vault=$(grep -E '^OP_VAULT=' config/op.conf | cut -d= -f2-)
        file_item=$(grep -E '^OP_ITEM=' config/op.conf | cut -d= -f2-)
    fi
    OP_ACCOUNT="${OP_ACCOUNT:-${file_account:-plentiful.1password.com}}"
    OP_VAULT="${OP_VAULT:-${file_vault:-Pantry Pirate Radio}}"
    OP_ITEM="${OP_ITEM:-${file_item:-bouy-env}}"
    export OP_ACCOUNT OP_VAULT OP_ITEM
}

# Single mockable seam for the 1Password CLI. Tests set BOUY_OP_CMD to a stub.
op_cli() {
    "${BOUY_OP_CMD:-op}" "$@"
}

# True iff the op binary exists and is signed into the configured account.
onepassword_available() {
    local bin="${BOUY_OP_CMD:-op}"
    command -v "$bin" >/dev/null 2>&1 || return 1
    op_cli account get --account "$OP_ACCOUNT" >/dev/null 2>&1
}

# Print resolved pointer + sign-in + which fields exist. No secret values shown.
op_status() {
    resolve_op_pointer
    output info "1Password account: $OP_ACCOUNT"
    output info "Vault: $OP_VAULT"
    output info "Item:  $OP_ITEM"
    if onepassword_available; then
        output success "Signed in to $OP_ACCOUNT"
    else
        output warning "Not signed in (run: op signin --account $OP_ACCOUNT)"
        return 0
    fi
    local field
    for field in dev test prod; do
        if op_cli read "op://$OP_VAULT/$OP_ITEM/$field" --account "$OP_ACCOUNT" >/dev/null 2>&1; then
            output info "  field '$field': present"
        else
            output info "  field '$field': missing"
        fi
    done
}

# Print a field blob to stdout (or --out FILE only when explicitly requested).
op_pull() {
    resolve_op_pointer
    local field="dev" out=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --field) field="$2"; shift 2 ;;
            --out) out="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    local blob
    blob=$(op_cli read "op://$OP_VAULT/$OP_ITEM/$field" --account "$OP_ACCOUNT") || {
        output error "Could not read op://$OP_VAULT/$OP_ITEM/$field"; return 1; }
    if [ -n "$out" ]; then
        printf '%s' "$blob" > "$out"
        output success "Wrote $field to $out"
    else
        printf '%s\n' "$blob"
    fi
}

# Upload local env file(s) into the 1Password item fields. --field dev|test|prod|all
op_push() {
    resolve_op_pointer
    local field="all"
    while [ $# -gt 0 ]; do
        case "$1" in
            --field) field="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    local fields=()
    case "$field" in
        all) fields=(dev test prod) ;;
        *) fields=("$field") ;;
    esac
    # Ensure the item exists (create empty Secure Note if missing).
    if ! op_cli item get "$OP_ITEM" --vault "$OP_VAULT" --account "$OP_ACCOUNT" >/dev/null 2>&1; then
        op_cli item create --category "Secure Note" --title "$OP_ITEM" \
            --vault "$OP_VAULT" --account "$OP_ACCOUNT" >/dev/null 2>&1 || true
    fi
    local f src content
    for f in "${fields[@]}"; do
        src=$(override_file_for_mode "$f")
        if [ "$f" = "prod" ] && [ ! -f "$src" ] && [ -f .env ]; then
            src=".env"
        fi
        if [ ! -f "$src" ]; then
            output warning "Skipping '$f': $src not found"
            continue
        fi
        content=$(cat "$src")
        if op_cli item edit "$OP_ITEM" --vault "$OP_VAULT" --account "$OP_ACCOUNT" \
            "$f[text]=$content" >/dev/null 2>&1; then
            output success "Pushed $src -> field '$f'"
        else
            output error "Failed to push field '$f'"
        fi
    done
}

# Fetch the blob for <field> (dev|test|prod) from 1Password and export it.
# Reads the whole field with a single op call; the value lives only in memory.
load_env_from_1password() {
    local field="$1" blob
    blob=$(op_cli read "op://$OP_VAULT/$OP_ITEM/$field" --account "$OP_ACCOUNT") || return 1
    [ -n "$blob" ] || return 1
    load_env_lines <<< "$blob"
}

# Commands that never need the application environment (must NOT trigger a
# 1Password biometric prompt when no override file exists).
command_needs_env() {
    case "$1" in
        ""|setup|op|version|help|-h|--help|--version) return 1 ;;
        *) return 0 ;;
    esac
}

# Resolve the environment for this invocation.
# Sets BOUY_ENV_SOURCE = file | 1password | none.
# Precedence: override file on disk wins; otherwise (for env-needing commands)
# 1Password; otherwise a hard error. --no-1password forces the file-only path;
# --1password forces the vault path even if a file exists.
load_environment() {
    local args=("$@") cmd="$1" mode file force="auto" arg
    for arg in "${args[@]}"; do
        case "$arg" in
            --no-1password) force="off" ;;
            --1password) force="on" ;;
        esac
    done
    if [ "${USE_1PASSWORD:-}" = "false" ]; then force="off"; fi
    if [ "${USE_1PASSWORD:-}" = "true" ]; then force="on"; fi

    resolve_op_pointer
    mode=$(detect_mode "${args[@]}")
    file=$(override_file_for_mode "$mode")
    # prod falls back to .env when .env.prod is absent
    if [ "$mode" = "prod" ] && [ ! -f "$file" ] && [ -f .env ]; then
        file=".env"
    fi
    BOUY_ENV_SOURCE="none"

    if [ "$force" != "on" ] && [ -f "$file" ]; then
        load_env_lines < "$file"
        BOUY_ENV_SOURCE="file"
        return 0
    fi

    if [ "$force" = "off" ]; then
        command_needs_env "$cmd" || return 0
        output error "No $file found and --no-1password set. Run './bouy setup' to create it."
        return 1
    fi

    command_needs_env "$cmd" || return 0

    if onepassword_available; then
        if load_env_from_1password "$mode"; then
            BOUY_ENV_SOURCE="1password"
            return 0
        fi
        output error "Failed to read op://$OP_VAULT/$OP_ITEM/$mode. Try './bouy op status'."
        return 1
    fi

    output error "No $file on disk and 1Password is unavailable."
    output error "Sign in (op signin --account $OP_ACCOUNT) or run './bouy setup' to create $file."
    return 1
}

# Write a names-only Docker Compose overlay that passes BOUY env vars through to
# each given service. Contains variable NAMES only — never secret values.
#   $1 = output file, $2 = space-separated keys, $3.. = service names
write_passthrough_overlay() {
    local outfile="$1" keys="$2"; shift 2
    local svc key
    {
        echo "services:"
        for svc in "$@"; do
            echo "  $svc:"
            echo "    environment:"
            for key in $keys; do
                echo "      - \"$key\""
            done
        done
    } > "$outfile"
}

# Service names in the currently-assembled compose configuration.
get_active_services() {
    $COMPOSE_CMD $COMPOSE_FILES config --services 2>/dev/null
}

# When running from 1Password, generate the passthrough overlay once and append
# it to COMPOSE_FILES. No-op for the .env (file) path.
maybe_add_passthrough_overlay() {
    if [ "$BOUY_ENV_SOURCE" != "1password" ]; then
        return 0
    fi
    if [ -n "$OP_PASSTHROUGH_ADDED" ]; then
        return 0
    fi
    local services overlay
    if [ -z "$BOUY_ENV_KEYS" ]; then
        output error "1Password env loaded zero variables; cannot build passthrough overlay."
        return 1
    fi
    if ! services=$(get_active_services) || [ -z "$services" ]; then
        output error "Could not determine active services for 1Password env passthrough (is Docker running and the compose config valid?)."
        return 1
    fi
    overlay=$(mktemp "${TMPDIR:-/tmp}/bouy-op-passthrough.XXXXXX")
    # shellcheck disable=SC2086
    write_passthrough_overlay "$overlay" "$BOUY_ENV_KEYS" $services
    COMPOSE_FILES="$COMPOSE_FILES -f $overlay"
    CLEANUP_TEMP_FILES="$CLEANUP_TEMP_FILES $overlay"
    OP_PASSTHROUGH_ADDED=1
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

# Helper function to prompt for input with default value
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local is_password="${4:-false}"
    local value=""

    if [ ! -t 0 ]; then
        # Non-interactive: read one line. A final line with no trailing
        # newline makes `read` return non-zero (EOF) but still populates
        # $value, so `|| true` keeps that partial read AND stays set -e safe;
        # the empty-value check below falls back to the default at true EOF.
        IFS= read -r value || true
    else
        if [ "$is_password" = "true" ]; then
            echo -n "$prompt [$default]: "
            read -s value || true
            echo  # New line after password input
        else
            read -p "$prompt [$default]: " value || true
        fi
    fi

    if [ -z "$value" ]; then
        value="$default"
    fi

    printf -v "$var_name" '%s' "$value"
    export "$var_name"
}
