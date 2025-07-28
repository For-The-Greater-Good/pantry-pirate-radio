#!/bin/bash
set -e

# Run tests in Docker
echo "Running tests in Docker environment..."

# Build test image if needed
docker compose -f .docker/compose/docker-compose.test.yml build test

# Run tests
docker compose -f .docker/compose/docker-compose.test.yml run --rm test

# Cleanup
docker compose -f .docker/compose/docker-compose.test.yml down -v