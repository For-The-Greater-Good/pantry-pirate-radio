#!/bin/bash
set -e

# Quick development startup script
echo "Starting development environment..."

# Ensure we're using the dev compose files
docker compose \
  -f .docker/compose/base.yml \
  -f .docker/compose/docker-compose.dev.yml \
  up -d

# Wait for services
echo "Waiting for services to be ready..."
sleep 5

# Show logs
echo "Services started! Showing logs (Ctrl+C to exit)..."
docker compose \
  -f .docker/compose/base.yml \
  -f .docker/compose/docker-compose.dev.yml \
  logs -f app worker