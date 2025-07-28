#!/bin/bash
# Wait for HAARRRvest repository to be fully cloned and stable
# This script monitors the repository size to ensure cloning is complete

set -e

DATA_REPO_PATH="${DATA_REPO_PATH:-/data-repo}"
STABILITY_CHECK_INTERVAL="${REPO_STABILITY_CHECK_INTERVAL:-10}"
STABILITY_THRESHOLD="${REPO_STABILITY_THRESHOLD:-3}"
MAX_WAIT_TIME="${REPO_MAX_WAIT_TIME:-1800}"  # 30 minutes max

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARN:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

# Function to count files in repository
count_repo_files() {
    if [ -d "$DATA_REPO_PATH/daily" ]; then
        find "$DATA_REPO_PATH/daily" -name "*.json" -type f 2>/dev/null | wc -l
    else
        echo "0"
    fi
}

# Function to get repository size
get_repo_size() {
    if [ -d "$DATA_REPO_PATH" ]; then
        du -s "$DATA_REPO_PATH" 2>/dev/null | cut -f1
    else
        echo "0"
    fi
}

# Main waiting logic
main() {
    log "Waiting for HAARRRvest repository to be ready at $DATA_REPO_PATH"

    local start_time=$(date +%s)
    local stability_count=0
    local last_size=0
    local last_file_count=0

    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))

        # Check if we've exceeded max wait time
        if [ $elapsed -gt $MAX_WAIT_TIME ]; then
            error "Timeout waiting for repository after ${MAX_WAIT_TIME} seconds"
            exit 1
        fi

        # Check if repository exists
        if [ ! -d "$DATA_REPO_PATH/.git" ]; then
            warn "Repository not yet cloned, waiting..."
            sleep $STABILITY_CHECK_INTERVAL
            continue
        fi

        # Check if clone is in progress
        if [ -f "$DATA_REPO_PATH/.git/index.lock" ]; then
            warn "Git operation in progress (index.lock exists), waiting..."
            sleep $STABILITY_CHECK_INTERVAL
            stability_count=0
            continue
        fi

        # Get current repository state
        local current_size=$(get_repo_size)
        local current_file_count=$(count_repo_files)

        log "Repository status: $current_file_count JSON files, size: ${current_size}KB"

        # Check if repository is stable (no changes)
        if [ "$current_size" -eq "$last_size" ] && [ "$current_file_count" -eq "$last_file_count" ] && [ "$current_file_count" -gt "0" ]; then
            stability_count=$((stability_count + 1))
            log "Repository stable for $stability_count checks"

            if [ $stability_count -ge $STABILITY_THRESHOLD ]; then
                log "Repository is stable and ready!"
                log "Final state: $current_file_count JSON files found"
                exit 0
            fi
        else
            # Repository changed, reset stability counter
            if [ $stability_count -gt 0 ]; then
                warn "Repository changed, resetting stability counter"
            fi
            stability_count=0
        fi

        last_size=$current_size
        last_file_count=$current_file_count

        sleep $STABILITY_CHECK_INTERVAL
    done
}

main