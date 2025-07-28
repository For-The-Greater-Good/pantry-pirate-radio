#!/bin/bash
# Pre-commit hook runner using Docker
# This script can be used with pre-commit to run checks in Docker

set -e

# Ensure test image is built
if ! docker image inspect pantry-pirate-radio-test:latest &> /dev/null; then
    echo "Building test image..."
    docker build -f .docker/images/app/Dockerfile --target test -t pantry-pirate-radio-test:latest .
fi

# Function to run command in docker
run_in_docker() {
    local cmd="$1"
    docker run --rm \
        -v "$(pwd)":/app \
        -w /app \
        --network pantry-pirate-radio_default \
        --env-file .env.test \
        pantry-pirate-radio-test:latest \
        bash -c "$cmd"
}

# Parse command
case "$1" in
    black)
        run_in_docker "poetry run black ${@:2}"
        ;;
    ruff)
        run_in_docker "poetry run ruff check ${@:2}"
        ;;
    mypy)
        run_in_docker "poetry run mypy ${@:2}"
        ;;
    pytest)
        run_in_docker "poetry run pytest ${@:2}"
        ;;
    *)
        echo "Usage: $0 {black|ruff|mypy|pytest} [args...]"
        exit 1
        ;;
esac