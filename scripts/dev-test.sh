#!/bin/bash
set -e

# Run tests with coverage in the development container
echo "Running tests with coverage..."
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml exec app poetry run pytest --cov=app --cov-report=term-missing --cov-report=html "$@"

# Run type checking
echo "Running type checking..."
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml exec app poetry run mypy .

# Run linting
echo "Running linting..."
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml exec app poetry run ruff check .

# Display coverage summary
echo "Coverage summary:"
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml exec app poetry run coverage report --show-missing --sort=Cover
