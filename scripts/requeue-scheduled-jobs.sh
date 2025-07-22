#!/bin/bash
# Re-queue all scheduled jobs for immediate processing
#
# Usage:
#   ./scripts/requeue-scheduled-jobs.sh                    # Re-queue all jobs
#   ./scripts/requeue-scheduled-jobs.sh --list            # List scheduled jobs
#   ./scripts/requeue-scheduled-jobs.sh --dry-run         # Show what would be done
#   ./scripts/requeue-scheduled-jobs.sh --queue llm       # Process specific queue
#
#   # Run in Docker container:
#   docker compose exec app bash scripts/requeue-scheduled-jobs.sh
#   docker compose exec worker bash scripts/requeue-scheduled-jobs.sh --list

set -e

# Show help if requested
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    echo "Re-queue scheduled jobs for immediate processing"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --list          List scheduled jobs without re-queuing them"
    echo "  --queue QUEUE   Process only a specific queue (llm, reconciler, recorder)"
    echo "  --dry-run       Show what would be done without actually re-queuing"
    echo "  -h, --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                     # Re-queue all scheduled jobs"
    echo "  $0 --list              # List all scheduled jobs"
    echo "  $0 --queue llm         # Re-queue only LLM queue jobs"
    echo "  $0 --dry-run           # Preview what would be re-queued"
    exit 0
fi

# Determine if we're running in a container or locally
if [ -f /.dockerenv ]; then
    echo "Running in Docker container..."
    poetry run python scripts/requeue-scheduled-jobs.py "$@"
else
    echo "Running locally..."

    # Check if poetry is available
    if command -v poetry &> /dev/null; then
        poetry run python scripts/requeue-scheduled-jobs.py "$@"
    else
        echo "Poetry not found. Running with system Python..."
        python scripts/requeue-scheduled-jobs.py "$@"
    fi
fi