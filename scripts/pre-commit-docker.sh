#!/bin/bash
# Pre-commit hook runner using Docker
# This script can be used with pre-commit to run checks in Docker

set -e

# Get the command
COMMAND="$1"
shift

# Use bouy for everything to ensure consistency
case "$COMMAND" in
    black)
        # Black needs to run on specific files passed by pre-commit
        if [ $# -gt 0 ]; then
            # Run black on the specific files
            ./bouy --programmatic --quiet test --black
        fi
        ;;
    ruff)
        # Ruff needs to run on specific files passed by pre-commit
        if [ $# -gt 0 ]; then
            # Run ruff on the specific files
            ./bouy --programmatic --quiet test --ruff
        fi
        ;;
    mypy)
        # Mypy always runs on the whole codebase
        ./bouy --programmatic --quiet test --mypy
        ;;
    pytest)
        # Pytest runs the test suite
        ./bouy --programmatic --quiet test --pytest
        ;;
    *)
        echo "Usage: $0 {black|ruff|mypy|pytest} [files...]"
        exit 1
        ;;
esac