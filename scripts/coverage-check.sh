#!/bin/bash
# Coverage check script with ratcheting mechanism

set -e

COVERAGE_FILE=".coverage-baseline"
RATCHET_TOLERANCE=2  # Allow 2% drop maximum

echo "🔍 Running coverage check with ratcheting mechanism..."

# Run tests with coverage
poetry run pytest --ignore=tests/test_integration --cov=app --cov-report=json --cov-report=term-missing --cov-branch --quiet

# Extract current coverage percentage
if [ -f "coverage.json" ]; then
    CURRENT_COVERAGE=$(python3 -c "
import json
with open('coverage.json', 'r') as f:
    data = json.load(f)
    print(f\"{data['totals']['percent_covered']:.2f}\")
")
else
    echo "❌ Coverage report not found!"
    exit 1
fi

# Validate coverage value
if ! [[ "$CURRENT_COVERAGE" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "❌ Invalid coverage value: $CURRENT_COVERAGE"
    exit 1
fi

echo "Current coverage: ${CURRENT_COVERAGE}%"

# Check against baseline (ratcheting)
if [ -f "$COVERAGE_FILE" ]; then
    BASELINE_COVERAGE=$(cat "$COVERAGE_FILE")
    echo "Baseline coverage: ${BASELINE_COVERAGE}%"

    # Validate baseline coverage value
    if ! [[ "$BASELINE_COVERAGE" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        echo "❌ Invalid baseline coverage value: $BASELINE_COVERAGE"
        exit 1
    fi

    # Calculate minimum allowed coverage (baseline - tolerance)
    MIN_ALLOWED=$(python3 -c "print(f'{float(\"$BASELINE_COVERAGE\") - float(\"$RATCHET_TOLERANCE\"):.2f}')")

    if python3 -c "exit(0 if float('$CURRENT_COVERAGE') >= float('$MIN_ALLOWED') else 1)"; then
        echo "✅ Coverage ${CURRENT_COVERAGE}% within acceptable range from baseline ${BASELINE_COVERAGE}%"
    else
        echo "❌ Coverage ${CURRENT_COVERAGE}% has dropped more than ${RATCHET_TOLERANCE}% from baseline ${BASELINE_COVERAGE}%"
        echo "   Minimum allowed: ${MIN_ALLOWED}%"
        echo "   To fix: Increase test coverage or adjust tolerance if justified"
        exit 1
    fi

    # Update baseline if coverage improved
    if python3 -c "exit(0 if float('$CURRENT_COVERAGE') > float('$BASELINE_COVERAGE') else 1)"; then
        # Atomic file operation with proper permissions
        echo "$CURRENT_COVERAGE" > "$COVERAGE_FILE.tmp" && mv "$COVERAGE_FILE.tmp" "$COVERAGE_FILE"
        chmod 644 "$COVERAGE_FILE" 2>/dev/null || true
        echo "✅ Updated coverage baseline to ${CURRENT_COVERAGE}%"
    else
        echo "✅ Coverage maintained at acceptable level"
    fi
else
    # Create baseline file (atomic operation) with proper permissions
    echo "$CURRENT_COVERAGE" > "$COVERAGE_FILE.tmp" && mv "$COVERAGE_FILE.tmp" "$COVERAGE_FILE"
    chmod 644 "$COVERAGE_FILE" 2>/dev/null || true
    echo "✅ Created coverage baseline at ${CURRENT_COVERAGE}%"
fi

echo "✅ Coverage check passed!"