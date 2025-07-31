#!/bin/bash

# Docker-based CI checks script
# This runs all CI checks using Docker containers

# Initialize error tracking
errors=0
error_list=""

# Check if we should use bouy or fallback to direct docker commands
if [ -x "./bouy" ]; then
    DOCKER_CMD="./bouy test"
else
    echo "bouy not found, using direct docker commands"
    DOCKER_CMD="docker run --rm -v $(pwd):/app -w /app --env-file .env.test pantry-pirate-radio-test:latest poetry run"

    # Ensure test image is built
    if ! docker image inspect pantry-pirate-radio-test:latest &> /dev/null; then
        echo "Building test image..."
        docker build -f .docker/images/app/Dockerfile --target test -t pantry-pirate-radio-test:latest .
    fi
fi

# Function to run a check and track its status
run_check() {
    local check_name="$1"
    echo -e "\n=== Running $check_name ==="
    shift
    if ! $@; then
        errors=$((errors + 1))
        error_list="$error_list\n- $check_name failed"
    fi
}

echo "Running CI checks using Docker..."

# If using bouy, run all checks at once
if [ "$DOCKER_CMD" = "./bouy test" ]; then
    echo -e "\n=== Running All CI Checks ==="
    if ! $DOCKER_CMD; then
        echo -e "\nCI checks failed!"
        exit 1
    else
        echo -e "\nAll checks passed successfully!"
        exit 0
    fi
fi

# Otherwise, run checks individually
# Pre-commit style checks
echo -e "\n=== Running Pre-commit Style Checks ==="
run_check "YAML Check" $DOCKER_CMD pre-commit run check-yaml --all-files
run_check "TOML Check" $DOCKER_CMD pre-commit run check-toml --all-files
run_check "Large Files Check" $DOCKER_CMD pre-commit run check-added-large-files --all-files
run_check "Trailing Whitespace" $DOCKER_CMD pre-commit run trailing-whitespace --all-files

# Code Formatting and Linting
echo -e "\n=== Running Code Formatting and Linting ==="
run_check "Black (formatter)" $DOCKER_CMD black --check app tests
run_check "Ruff (linter)" $DOCKER_CMD ruff check app tests

# Type Checking
run_check "MyPy (type checker)" $DOCKER_CMD mypy app tests

# Tests with Coverage
run_check "Pytest with Coverage" $DOCKER_CMD pytest --ignore=docs --ignore=tests/test_integration --cov=app --cov-report=term-missing --cov-report=xml --cov-report=json --cov-branch

# Coverage Check with Ratcheting
run_check "Coverage Ratcheting" docker run --rm -v $(pwd):/app -w /app pantry-pirate-radio-test:latest bash scripts/coverage-check.sh

# Dead Code Check
run_check "Dead Code Check" $DOCKER_CMD vulture app tests .vulture_whitelist --min-confidence 80

# Security Checks
echo -e "\n=== Running Security Checks ==="
run_check "Bandit" $DOCKER_CMD bandit -r app
run_check "Safety Check" $DOCKER_CMD safety check
run_check "Pip Audit" $DOCKER_CMD pip-audit

# Complexity Check
run_check "Complexity Check" $DOCKER_CMD xenon --max-absolute F --max-modules F --max-average E app

echo -e "\nCI checks completed!"

# Report results
if [ $errors -gt 0 ]; then
    echo -e "\nThe following checks failed:$error_list"
    echo -e "\nTotal failures: $errors"
    exit 1
else
    echo -e "\nAll checks passed successfully!"
    exit 0
fi