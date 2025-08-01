#!/bin/bash

# CI checks script - runs checks using local poetry installation
# For Docker-based checks, use: ./scripts/run-ci-checks-docker.sh
# Or simply: ./bouy test

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
# Check YAML files
if find . -name "*.yaml" -o -name "*.yml" | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)" | head -1 > /dev/null 2>&1; then
    run_check "YAML Check" find . -name "*.yaml" -o -name "*.yml" | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)" | xargs -I {} python -c "import yaml; yaml.safe_load(open('{}'))"
fi
# Check TOML files
if find . -name "*.toml" | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)" | head -1 > /dev/null 2>&1; then
    run_check "TOML Check" find . -name "*.toml" | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)" | xargs -I {} python -c "import tomllib; tomllib.load(open('{}', 'rb'))"
fi
# Check for large files (>500KB)
run_check "Large Files Check" bash -c 'large_files=$(find . -type f -size +500k -not -path "./.git/*" -not -path "./.*" 2>/dev/null | head -10); [ -z "$large_files" ] || (echo "Large files found: $large_files" && false)'
# Check for trailing whitespace
run_check "Trailing Whitespace" bash -c 'files_with_trailing=$(find . -name "*.py" -exec grep -l "[[:space:]]$" {} \; 2>/dev/null | head -10); [ -z "$files_with_trailing" ] || (echo "Files with trailing whitespace: $files_with_trailing" && false)'

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
run_check "Vulture (dead code)" poetry run vulture app tests .vulture_whitelist --min-confidence 80

# Security Checks
echo -e "\n=== Running Security Checks ==="
run_check "Bandit (security)" poetry run bandit -r app
run_check "Safety (vulnerabilities)" poetry run safety check || true  # Safety check can be flaky, don't fail CI
run_check "Pip-audit (vulnerabilities)" poetry run pip-audit || true  # Pip-audit can be flaky, don't fail CI

# Complexity Check
run_check "Xenon (complexity)" poetry run xenon --max-absolute F --max-modules F --max-average E app

# Note: Shell script checks and bouy tests are skipped when running inside Docker
# These are tested separately in the CI pipeline

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
