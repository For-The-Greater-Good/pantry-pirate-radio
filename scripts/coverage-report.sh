#!/bin/bash
# Generate comprehensive coverage report

set -e

echo "🔍 Generating comprehensive coverage report..."

# Clean previous coverage data
rm -rf htmlcov/ coverage.xml coverage.json .coverage

# Run tests with coverage
echo "Running tests with coverage..."
poetry run pytest --cov=app --cov-report=html --cov-report=xml --cov-report=json --cov-report=term-missing --cov-branch --cov-fail-under=0

# Display coverage summary
echo ""
echo "📊 Coverage Summary:"
echo "===================="
poetry run coverage report --show-missing --sort=Cover

# Check if HTML report was generated
if [ -d "htmlcov" ]; then
    echo ""
    echo "✅ HTML coverage report generated: htmlcov/index.html"
    echo "   Open in browser: file://$(pwd)/htmlcov/index.html"
fi

# Check if XML report was generated
if [ -f "coverage.xml" ]; then
    echo "✅ XML coverage report generated: coverage.xml"
fi

# Check if JSON report was generated
if [ -f "coverage.json" ]; then
    echo "✅ JSON coverage report generated: coverage.json"
fi

echo ""
echo "🎯 Coverage enforcement: Ratcheting mechanism (use scripts/coverage-check.sh)"
echo "Done!"