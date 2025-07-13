#!/bin/bash

# Initialize error tracking
errors=0
error_list=""

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

echo "Running CI checks locally..."

# Pre-commit style checks
echo -e "\n=== Running Pre-commit Style Checks ==="
run_check "YAML Check" poetry run pre-commit run check-yaml --all-files
run_check "TOML Check" poetry run pre-commit run check-toml --all-files
run_check "Large Files Check" poetry run pre-commit run check-added-large-files --all-files
run_check "Trailing Whitespace" poetry run pre-commit run trailing-whitespace --all-files

# Code Formatting and Linting
echo -e "\n=== Running Code Formatting and Linting ==="
run_check "Black (formatter)" poetry run black --check app tests
run_check "Ruff (linter)" poetry run ruff check app tests

# Type Checking
run_check "MyPy (type checker)" poetry run mypy app tests

# Tests with Coverage
run_check "Pytest with Coverage" poetry run pytest --ignore=docs --ignore=tests/test_integration --cov=app --cov-report=term-missing --cov-report=xml --cov-report=json --cov-branch

# Coverage Check with Ratcheting
run_check "Coverage Ratcheting" bash scripts/coverage-check.sh

# Dead Code Check
run_check "Dead Code Check" poetry run vulture app tests .vulture_whitelist --min-confidence 80

# Security Checks
echo -e "\n=== Running Security Checks ==="
run_check "Bandit" poetry run bandit -r app
run_check "Safety Check" poetry run safety check
run_check "Pip Audit" poetry run pip-audit

# Complexity Check
run_check "Complexity Check" poetry run xenon --max-absolute F --max-modules F --max-average E app

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
