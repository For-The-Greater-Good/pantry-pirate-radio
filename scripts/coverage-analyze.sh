#!/bin/bash
# Coverage analysis script - checks existing coverage reports without re-running tests

set -e

COVERAGE_FILE=".coverage-baseline"
RATCHET_TOLERANCE=2  # Allow 2% drop maximum

echo "🔍 Analyzing existing coverage reports..."

# Check if coverage.json exists
if [ ! -f "coverage.json" ]; then
    echo "❌ Coverage report not found! Please run tests with coverage first."
    echo "   Run: ./bouy test --pytest"
    exit 1
fi

# Extract current coverage percentage
CURRENT_COVERAGE=$(python3 -c "
import json
with open('coverage.json', 'r') as f:
    data = json.load(f)
    print(f\"{data['totals']['percent_covered']:.2f}\")
")

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

# --- Per-path floors: RED-tier modules are held to a higher bar than the
# project aggregate (constitution v1.7.0). The global ratchet alone cannot see a
# single module decaying inside the average — e.g. fetch.py sat at 46% and
# batcher.py's crash-recovery branches can collapse far below the 2% tolerance
# undetected. This is the script CI runs via `./bouy test --coverage`; the floor
# must live HERE, not only in scripts/coverage-check.sh (which CI does not invoke).
#
# PREFIX_FLOORS: every file under the prefix must meet the floor.
# FILE_FLOORS: named RED-tier files (set conservatively at floor(measured) so
# they catch decay without a backfill sprint; ratchet up as coverage grows).
echo "🔍 Checking RED-tier per-file coverage floors ..."
python3 - <<'PYEOF'
import json
import sys

PREFIX_FLOORS = {
    "app/federation/": 95.0,  # crypto/protocol substrate
}
# Explicit manifest per prefix: every listed module MUST appear in coverage.json,
# so a single module silently dropping out (rename/move/exclude) is caught — the
# all-or-nothing prefix guard alone would still pass if any one file remained.
PREFIX_MANIFEST = {
    "app/federation/": [
        "aggregate.py", "canonical.py", "checkpoint.py", "discovery.py",
        "envelope.py", "fetch.py", "identity.py", "log.py", "merkle.py",
        "routes_public.py", "signing.py",
    ],
}
FILE_FLOORS = {
    # app/llm/queue/ economic-takedown RED-tier (durable drain / batch recovery).
    "app/llm/queue/batcher.py": 85.0,
    "app/llm/queue/backend_sqs.py": 86.0,
    "app/llm/queue/batch_result_processor.py": 76.0,
}

with open("coverage.json") as f:
    files = json.load(f).get("files", {})
norm = {p.replace("\\", "/"): info for p, info in files.items()}

failures, missing = [], []

for prefix, floor in PREFIX_FLOORS.items():
    seen = [p for p in norm if prefix in p]
    if not seen:  # no-vacuous-pass: a moved/renamed dir must not silently pass
        missing.append(prefix)
        continue
    for p in seen:
        pct = norm[p]["summary"]["percent_covered"]
        if pct < floor:
            failures.append((p, pct, floor))
    # Per-module manifest: each expected file must be present (not all-or-nothing).
    for mod in PREFIX_MANIFEST.get(prefix, []):
        if not any(p.endswith(prefix + mod) for p in norm):
            missing.append(prefix + mod)

for path, floor in FILE_FLOORS.items():
    match = next((p for p in norm if p.endswith(path)), None)
    if match is None:
        missing.append(path)
        continue
    pct = norm[match]["summary"]["percent_covered"]
    if pct < floor:
        failures.append((match, pct, floor))

for path in sorted(missing):
    print(f"❌ {path}: not present in coverage.json — floor cannot be evaluated")
for path, pct, floor in sorted(failures):
    print(f"❌ {path}: {pct:.2f}% < floor {floor}%")
if failures or missing:
    print("   RED-tier modules must not decay below their floor; add tests.")
    sys.exit(1)
print("✅ All RED-tier per-file coverage floors met")
PYEOF

echo "✅ Coverage check passed!"