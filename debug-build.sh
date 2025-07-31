#!/bin/bash
set -x
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

# Build with base compose file only
echo "Building with base.yml only..."
docker compose -f .docker/compose/base.yml build app

# Build with base + dev compose files
echo "Building with base.yml + dev.yml..."
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml build app