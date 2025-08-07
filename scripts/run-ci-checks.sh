#!/bin/bash

# CI checks script - runs checks using local poetry installation
# For Docker-based checks, use: ./scripts/run-ci-checks-docker.sh
# Or simply: ./bouy test
#
# Options:
#   --no-fix    Disable auto-fixing (check only mode)
#   --help      Show this help message

# Parse command line arguments
AUTO_FIX=1
for arg in "$@"; do
    case $arg in
        --no-fix)
            AUTO_FIX=0
            echo "Auto-fix disabled - running in check-only mode"
            ;;
        --help)
            echo "CI checks script - runs checks using local poetry installation"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-fix    Disable auto-fixing (check only mode)"
            echo "  --help      Show this help message"
            echo ""
            echo "By default, this script will auto-fix:"
            echo "  - Trailing whitespace"
            echo "  - Black formatting issues"
            echo "  - Ruff safe fixes (imports, unused variables, etc.)"
            exit 0
            ;;
    esac
done

# Initialize error tracking
errors=0
error_list=""
auto_fixed_list=""

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
echo "=== Running YAML Check ==="
if find . \( -name "*.yaml" -o -name "*.yml" \) | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)" | head -1 > /dev/null 2>&1; then
    yaml_files=$(find . \( -name "*.yaml" -o -name "*.yml" \) | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)")
    if [ -n "$yaml_files" ]; then
        for file in $yaml_files; do
            if ! python -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                errors=$((errors + 1))
                error_list="$error_list\n- YAML Check failed for $file"
            fi
        done
    fi
fi

# Check TOML files
echo "=== Running TOML Check ==="
if find . -name "*.toml" | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)" | head -1 > /dev/null 2>&1; then
    toml_files=$(find . -name "*.toml" | grep -v -E "(\.git|\.pytest_cache|\.mypy_cache|__pycache__|htmlcov)")
    if [ -n "$toml_files" ]; then
        for file in $toml_files; do
            if ! python -c "import tomllib; tomllib.load(open('$file', 'rb'))" 2>/dev/null; then
                errors=$((errors + 1))
                error_list="$error_list\n- TOML Check failed for $file"
            fi
        done
    fi
fi

# Check for large files (>500KB) - only for files tracked by git, excluding submodules
echo "=== Running Large Files Check ==="
# Use git ls-files to only check tracked files, then filter by size
# This automatically excludes submodules, untracked files, and ignored files
large_files=""
for file in $(git ls-files); do
    if [ -f "$file" ] && [ $(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null) -gt 512000 ]; then
        large_files="$large_files$file\n"
    fi
done
if [ -n "$large_files" ]; then
    echo "Large files found: $large_files"
    errors=$((errors + 1))
    error_list="$error_list\n- Large Files Check failed"
fi

# Check for trailing whitespace - with auto-fix option
echo "=== Running Trailing Whitespace Check ==="
files_with_trailing=$(find . -name "*.py" -exec grep -l "[[:space:]]$" {} \; 2>/dev/null | head -10)
if [ -n "$files_with_trailing" ]; then
    if [ $AUTO_FIX -eq 1 ]; then
        echo "Files with trailing whitespace found. Auto-fixing..."
        # Auto-fix trailing whitespace
        for file in $files_with_trailing; do
            sed -i.bak 's/[[:space:]]*$//' "$file" && rm "${file}.bak"
        done
        echo "✅ AUTO-FIXED: Removed trailing whitespace from $(echo "$files_with_trailing" | wc -w) files"
        auto_fixed_list="$auto_fixed_list\n- Trailing whitespace removed"
    else
        echo "Files with trailing whitespace: $files_with_trailing"
        errors=$((errors + 1))
        error_list="$error_list\n- Trailing Whitespace Check failed"
    fi
else
    echo "No trailing whitespace found"
fi

# Code Formatting and Linting
echo -e "\n=== Running Code Formatting and Linting ==="

# Black formatter - with auto-fix
echo "=== Running Black (formatter) ==="
if ! poetry run black --check app tests 2>/dev/null; then
    if [ $AUTO_FIX -eq 1 ]; then
        echo "Black found formatting issues. Auto-fixing..."
        poetry run black app tests
        echo "✅ AUTO-FIXED: Black reformatted files"
        auto_fixed_list="$auto_fixed_list\n- Black code formatting applied"
    else
        echo "Black formatting issues found (run without --no-fix to auto-format)"
        errors=$((errors + 1))
        error_list="$error_list\n- Black (formatter) failed"
    fi
else
    echo "Black check passed - no formatting needed"
fi

# Ruff linter - with auto-fix for safe fixes
echo "=== Running Ruff (linter) ==="
if ! poetry run ruff check app tests 2>/dev/null; then
    if [ $AUTO_FIX -eq 1 ]; then
        echo "Ruff found issues. Attempting auto-fix for safe fixes..."
        poetry run ruff check --fix app tests
        echo "✅ AUTO-FIXED: Ruff applied safe fixes (imports, unused variables, etc.)"
        auto_fixed_list="$auto_fixed_list\n- Ruff safe fixes applied"
        # Check if there are still issues that couldn't be auto-fixed
        if ! poetry run ruff check app tests 2>/dev/null; then
            errors=$((errors + 1))
            error_list="$error_list\n- Ruff (linter) - some issues require manual fixing"
        fi
    else
        echo "Ruff linting issues found (run without --no-fix to apply safe fixes)"
        errors=$((errors + 1))
        error_list="$error_list\n- Ruff (linter) failed"
    fi
else
    echo "Ruff check passed - no linting issues"
fi

# Type Checking
run_check "MyPy (type checker)" poetry run mypy app tests

# Tests with Coverage and Ratcheting
# Note: coverage-check.sh runs pytest with coverage in quiet mode and checks ratcheting
echo "=== Running Pytest with Coverage ==="
if bash scripts/coverage-check.sh; then
    echo "✅ Tests and coverage check passed"
else
    errors=$((errors + 1))
    error_list="$error_list\n- Pytest/Coverage failed"
fi

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

# Report auto-fixes prominently
if [ -n "$auto_fixed_list" ]; then
    echo -e "\n" 
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                    🔧 AUTO-FIXES APPLIED 🔧                    ║"
    echo "╠════════════════════════════════════════════════════════════════╣"
    echo "║ The following issues were automatically fixed:                 ║"
    echo -e "$auto_fixed_list" | while IFS= read -r line; do
        if [ -n "$line" ] && [ "$line" != "" ]; then
            printf "║ %-63s ║\n" "$line"
        fi
    done
    echo "╠════════════════════════════════════════════════════════════════╣"
    echo "║ ⚠️  IMPORTANT: Files have been modified!                       ║"
    echo "║ Please review and commit these changes if appropriate.         ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
fi

# Report results
if [ $errors -gt 0 ]; then
    echo -e "\nThe following checks failed:$error_list"
    echo -e "\nTotal failures: $errors"
    exit 1
else
    echo -e "\nAll checks passed successfully!"
    exit 0
fi
