#!/bin/bash
set -e

# Stop all containers and remove volumes
echo "Stopping development environment..."
docker compose down -v

echo "Development environment stopped and cleaned up."
