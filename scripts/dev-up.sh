#!/bin/bash
set -e

# Build and start the development environment
echo "Building and starting development environment..."
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml up --build -d

# Wait for services to be healthy
echo "Waiting for services to be ready..."
until docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml exec db pg_isready -U pantry > /dev/null 2>&1; do
    echo "Waiting for database..."
    sleep 2
done

until docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml exec cache redis-cli ping > /dev/null 2>&1; do
    echo "Waiting for cache..."
    sleep 2
done

echo "Services are ready!"
echo "API is running at http://localhost:8000"
echo "API docs at http://localhost:8000/docs"

# Show logs
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml logs -f app
