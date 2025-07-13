#!/bin/bash
set -e

# Install dependencies if needed
poetry install

# Run pre-commit install if not already installed
if [ ! -f ".git/hooks/pre-commit" ]; then
	pre-commit install
fi

# Start FastAPI with hot reload
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
