#!/bin/bash
set -e

# Run tests with coverage in the development container
echo "Running tests with coverage..."
docker compose exec app poetry run pytest --cov=app --cov-report=term-missing --cov-report=html "$@"

# Run type checking
echo "Running type checking..."
docker compose exec app poetry run mypy .

# Run linting
echo "Running linting..."
docker compose exec app poetry run ruff check .

# Display coverage summary
echo "Coverage summary:"
docker compose exec app poetry run coverage report --show-missing --sort=Cover
