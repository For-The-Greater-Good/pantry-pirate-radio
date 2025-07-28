#!/bin/bash
set -e

# Stop all containers and remove volumes
echo "Stopping development environment..."
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml down -v

echo "Development environment stopped and cleaned up."
