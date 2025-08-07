# Pantry Pirate Radio Examples

This directory contains comprehensive examples and documentation for using Pantry Pirate Radio with the `bouy` command-line tool. All examples are designed to be copy-paste ready and work out of the box.

## Directory Structure

- `sample_data/` - Example HSDS-compliant data files
- `scraper_output/` - Example scraper output at different processing stages
- `api_responses/` - Example API response formats
- `integrations/` - Integration examples for different programming languages
  - `curl_examples.sh` - REST API examples using curl
  - `python_client.py` - Python client implementation
  - `javascript_client.js` - JavaScript/Node.js client
  - `postman_collection.json` - Postman collection for API testing
- `docker-automation.py` - Example of automating bouy commands programmatically

## Table of Contents

1. [Quick Start Examples](#quick-start-examples)
2. [Development Workflow Examples](#development-workflow-examples)
3. [API Usage Examples](#api-usage-examples)
4. [Scraper Running Examples](#scraper-running-examples)
5. [Data Reconciliation Examples](#data-reconciliation-examples)
6. [HAARRRvest Publishing Examples](#haarrrvest-publishing-examples)
7. [Testing Examples](#testing-examples)
8. [Common Use Cases](#common-use-cases)
9. [Advanced Scenarios](#advanced-scenarios)
10. [Troubleshooting Examples](#troubleshooting-examples)

---

## Quick Start Examples

### Initial Setup for New Users

```bash
# Step 1: Run interactive setup wizard
./bouy setup

# Expected output:
# ⚓ Bouy v1.0.0 - Docker Fleet Management ⚓
# 🚀 Starting interactive setup wizard...
# 
# Creating .env configuration file...
# Enter database password [pirate]: 
# Select LLM provider (1=OpenAI via OpenRouter, 2=Claude/Anthropic) [1]: 
# ...configuration prompts continue...
# ✅ Setup complete! Your .env file has been created.

# Step 2: Start all services
./bouy up

# Expected output:
# 🐳 Starting services in development mode...
# ✅ Creating network pantry-pirate-radio_default
# ✅ Creating pantry-pirate-radio_postgres_1
# ✅ Creating pantry-pirate-radio_redis_1
# ✅ Creating pantry-pirate-radio_app_1
# ✅ Creating pantry-pirate-radio_worker_1
# ✅ All services started successfully!

# Step 3: Verify everything works
./bouy test

# Expected output:
# 🧪 Running all test categories...
# ✅ pytest: 123 passed in 45.67s
# ✅ mypy: Success: no issues found in 42 source files
# ✅ black: All done! ✨ 🍰 ✨
# ✅ ruff: All checks passed!
# ✅ bandit: No issues identified
```

### Check Service Status

```bash
# List running services
./bouy ps

# Expected output:
# NAME                           STATUS    PORTS
# pantry-pirate-radio_app_1      running   0.0.0.0:8000->8000/tcp
# pantry-pirate-radio_worker_1   running   
# pantry-pirate-radio_redis_1    running   0.0.0.0:6379->6379/tcp
# pantry-pirate-radio_postgres_1 running   0.0.0.0:5432->5432/tcp

# Get JSON output for automation
./bouy --json ps

# Expected output (one service per line):
# {"name":"pantry-pirate-radio_app_1","status":"running","ports":"0.0.0.0:8000->8000/tcp"}
# {"name":"pantry-pirate-radio_worker_1","status":"running","ports":""}
# {"name":"pantry-pirate-radio_redis_1","status":"running","ports":"0.0.0.0:6379->6379/tcp"}
# {"name":"pantry-pirate-radio_postgres_1","status":"running","ports":"0.0.0.0:5432->5432/tcp"}
```

---

## Development Workflow Examples

### Starting Development Environment

```bash
# Start with development mode (default)
./bouy up

# Start with database initialization
./bouy up --with-init

# Start specific services only
./bouy up app worker

# Start in production mode
./bouy up --prod

# Start in test mode
./bouy up --test
```

### Viewing Logs

```bash
# View all service logs (follows by default)
./bouy logs

# View specific service logs
./bouy logs app

# View worker logs with explicit follow
./bouy logs -f worker

# View logs without following (one-time output)
./bouy logs app | head -50
```

### Accessing Service Shells

```bash
# Open shell in app container
./bouy shell app

# Expected prompt:
# root@app-container:/app#

# Execute specific commands
./bouy exec app python --version
# Python 3.11.4

./bouy exec app pip list | grep -i django
# Django 4.2.7

# Run Django management commands
./bouy exec app python manage.py migrate
./bouy exec app python manage.py createsuperuser
```

### Building and Rebuilding Services

```bash
# Build all services
./bouy build

# Build specific service
./bouy build app

# Build for production
./bouy build --prod worker

# Pull latest images
./bouy pull

# Pull specific version
./bouy pull v1.2.3
```

---

## API Usage Examples

### Using curl to Access the API

```bash
# Start services first
./bouy up

# Search for food services near a location
curl -X GET "http://localhost:8000/api/v1/services/search?q=food&lat=37.7749&lon=-122.4194&radius=5" \
  -H "Accept: application/json" | jq

# Expected output:
# {
#   "services": [
#     {
#       "id": "srv_123",
#       "name": "Community Food Pantry",
#       "description": "Free food distribution every Tuesday",
#       "latitude": 37.7751,
#       "longitude": -122.4180,
#       "distance_km": 0.3
#     }
#   ],
#   "total": 15,
#   "page": 1
# }

# Get organization details
curl -X GET "http://localhost:8000/api/v1/organizations/org_456" \
  -H "Accept: application/json" | jq

# List all services
curl -X GET "http://localhost:8000/api/v1/services?page=1&limit=10" \
  -H "Accept: application/json" | jq
```

### Accessing API Documentation

```bash
# Start services
./bouy up

# Open API documentation in browser
open http://localhost:8000/docs     # macOS
xdg-open http://localhost:8000/docs # Linux

# The Swagger UI provides interactive API documentation
```

### Using the Python Client Example

```bash
# Run the Python client example
./bouy exec app python examples/integrations/python_client.py

# Or copy the client into your own project
cp examples/integrations/python_client.py /your/project/
```

---

## Scraper Running Examples

### List Available Scrapers

```bash
./bouy scraper --list

# Expected output:
# Available scrapers:
#   - example_scraper
#   - food_bank_scraper
#   - community_center_scraper
#   - shelter_scraper
#   - meal_program_scraper
```

### Run Individual Scrapers

```bash
# Run a specific scraper
./bouy scraper food_bank_scraper

# Expected output:
# 🏴‍☠️ Running scraper: food_bank_scraper
# ⚙️  Initializing scraper...
# 🔍 Scraping https://example-foodbank.org...
# ✅ Found 25 locations
# 📝 Processing with LLM...
# 💾 Saving to database...
# ✅ Scraper completed successfully!

# Test a scraper without processing (dry run)
./bouy scraper-test food_bank_scraper

# Expected output:
# 🧪 Testing scraper: food_bank_scraper (dry run)
# ⚙️  Initializing scraper...
# 🔍 Would scrape: https://example-foodbank.org
# ✅ Scraper test completed (no data saved)
```

### Run Multiple Scrapers

```bash
# Run all scrapers sequentially
./bouy scraper --all

# Expected output:
# 🏴‍☠️ Running all scrapers sequentially...
# [1/5] Running example_scraper...
# ✅ example_scraper completed
# [2/5] Running food_bank_scraper...
# ✅ food_bank_scraper completed
# ...

# Run all scrapers in parallel (default: 5 concurrent)
./bouy scraper scouting-party

# Run with custom concurrency
./bouy scraper scouting-party 10

# Expected output:
# 🏴‍☠️ Launching scouting party with 10 concurrent scrapers!
# ⚡ Starting parallel execution...
# ✅ All scrapers completed in 2m 34s
```

### Test All Scrapers

```bash
# Test all scrapers without saving data
./bouy scraper-test --all

# Expected output:
# 🧪 Testing all scrapers (dry run)...
# [1/5] Testing example_scraper...
# ✅ PASS
# [2/5] Testing food_bank_scraper...
# ✅ PASS
# ...
# 🎉 All scraper tests passed!
```

---

## Data Reconciliation Examples

### Run Data Reconciliation

```bash
# Run reconciler with default settings
./bouy reconciler

# Expected output:
# 🔄 Starting data reconciliation...
# 📊 Processing 1,234 records...
# 🔍 Deduplicating organizations...
# ✅ Merged 45 duplicate organizations
# 🔍 Geocoding missing addresses...
# ✅ Geocoded 123 locations
# 🔍 Validating phone numbers...
# ✅ Standardized 567 phone numbers
# ✅ Reconciliation complete!

# Force processing even if recently run
./bouy reconciler --force

# Run with verbose output
./bouy --verbose reconciler
```

### Check Reconciliation Status

```bash
# View reconciler logs
./bouy logs reconciler

# Check last reconciliation run
./bouy exec app python -c "
from app.reconciler import get_last_run_status
print(get_last_run_status())
"
```

---

## HAARRRvest Publishing Examples

### Publish Data to HAARRRvest

```bash
# Trigger manual publishing run
./bouy haarrrvest

# Expected output:
# 🚢 Starting HAARRRvest publisher...
# 📦 Preparing data for export...
# 📊 Found 1,234 organizations, 5,678 services
# 🔄 Converting to HSDS format...
# 📤 Publishing to HAARRRvest repository...
# ✅ Successfully published dataset version 2024.01.15

# Alternative command
./bouy haarrrvest run
```

### Monitor Publishing Process

```bash
# Follow publisher logs
./bouy haarrrvest logs

# Expected output:
# [2024-01-15 10:30:00] INFO: Starting publishing cycle
# [2024-01-15 10:30:01] INFO: Querying database for changes
# [2024-01-15 10:30:05] INFO: Processing 250 new records
# [2024-01-15 10:30:10] INFO: Validation passed
# [2024-01-15 10:30:15] INFO: Publishing to repository
# [2024-01-15 10:30:20] INFO: Publishing complete

# Check publisher status
./bouy haarrrvest status

# Expected output:
# HAARRRvest Publisher Status:
# - Last run: 2024-01-15 10:30:20
# - Status: SUCCESS
# - Records published: 250
# - Next scheduled run: 2024-01-16 02:00:00
```

---

## Testing Examples

### Run All Tests

```bash
# Run complete test suite (pytest, mypy, black, ruff, bandit)
./bouy test

# Expected output:
# 🧪 Running all test categories...
# 
# Running pytest...
# ======================== test session starts ========================
# collected 234 items
# tests/test_api.py::TestAPI::test_search_endpoint PASSED      [  1%]
# tests/test_api.py::TestAPI::test_organization_get PASSED     [  2%]
# ...
# ======================== 234 passed in 45.67s ========================
# ✅ pytest passed
# 
# Running mypy...
# Success: no issues found in 42 source files
# ✅ mypy passed
# 
# Running black...
# All done! ✨ 🍰 ✨
# 42 files left unchanged.
# ✅ black passed
# 
# Running ruff...
# All checks passed!
# ✅ ruff passed
# 
# Running bandit...
# No issues identified.
# ✅ bandit passed
# 
# 🎉 All tests passed!
```

### Run Specific Test Types

```bash
# Run only pytest
./bouy test --pytest

# Run only type checking
./bouy test --mypy

# Run only formatting check
./bouy test --black

# Run only linting
./bouy test --ruff

# Run only security scan
./bouy test --bandit

# Run with coverage analysis
./bouy test --coverage
```

### Run Specific Test Files

```bash
# Test a specific file
./bouy test --pytest tests/test_api.py

# Test a directory
./bouy test --pytest tests/test_scraper/

# Test multiple files
./bouy test --pytest tests/test_api.py tests/test_reconciler.py
```

### Run Tests with Options

```bash
# Verbose output
./bouy test --pytest -- -v

# Stop on first failure
./bouy test --pytest -- -x

# Run tests matching pattern
./bouy test --pytest -- -k "test_search"

# Run specific test function
./bouy test --pytest -- tests/test_api.py::TestAPI::test_search_endpoint

# Show local variables on failure
./bouy test --pytest -- -l

# Drop to debugger on failure
./bouy test --pytest -- --pdb

# Combine multiple options
./bouy test --pytest -- -vsx -k "test_api"
```

### Advanced Testing

```bash
# Run dead code detection
./bouy test --vulture

# Run dependency vulnerability scan
./bouy test --safety

# Run pip audit
./bouy test --pip-audit

# Run code complexity analysis
./bouy test --xenon

# Check specific paths with mypy
./bouy test --mypy app/api/ app/llm/

# Format specific paths with black
./bouy test --black app/api/
```

### Test Output Formats

```bash
# Programmatic mode for CI/CD
./bouy --programmatic test --pytest

# JSON output
./bouy --json test --pytest

# Quiet mode
./bouy --quiet test

# No color output (for log files)
./bouy --no-color test

# Combine modes
./bouy --programmatic --quiet test
```

---

## Common Use Cases

### Case 1: Daily Development Workflow

```bash
# Morning: Start services and check status
./bouy up
./bouy ps
./bouy logs app | tail -20

# Make code changes...

# Test your changes
./bouy test --pytest tests/test_my_feature.py

# Check formatting and linting
./bouy test --black
./bouy test --ruff

# Run full test suite before committing
./bouy test

# Evening: Stop services
./bouy down
```

### Case 2: Debugging a Failed Scraper

```bash
# Test the scraper first
./bouy scraper-test problematic_scraper

# Check scraper logs
./bouy logs worker | grep -i error

# Open shell to debug
./bouy shell worker
# Inside container:
python -m app.scrapers.problematic_scraper --debug

# Run with verbose output
./bouy --verbose scraper problematic_scraper
```

### Case 3: Updating Production Data

```bash
# Start production environment
./bouy up --prod

# Run all scrapers
./bouy scraper --all

# Run reconciliation
./bouy reconciler

# Publish to HAARRRvest
./bouy haarrrvest

# Check results
./bouy exec app python -c "
from app.models import Organization
print(f'Total organizations: {Organization.objects.count()}')
"
```

### Case 4: Setting Up Claude Authentication

```bash
# Interactive setup
./bouy claude-auth

# Check current status
./bouy claude-auth status

# Test connection
./bouy claude-auth test

# View configuration
./bouy claude-auth config
```

---

## Advanced Scenarios

### Scenario 1: Automated Data Pipeline

```bash
#!/bin/bash
# automated_pipeline.sh

# Start services
./bouy up --prod

# Wait for services to be ready
sleep 10

# Run scrapers in parallel
./bouy scraper scouting-party 10

# Wait for scrapers to complete
while ./bouy --json ps | grep -q worker.*running; do
    sleep 5
done

# Run reconciliation
./bouy reconciler --force

# Publish to HAARRRvest
./bouy haarrrvest

# Generate report
./bouy content-store report > daily_report.txt

echo "Pipeline completed successfully!"
```

### Scenario 2: Continuous Testing During Development

```bash
#!/bin/bash
# watch_and_test.sh

# Watch for file changes and run tests
while true; do
    # Wait for file changes
    inotifywait -r -e modify app/ tests/
    
    # Clear screen
    clear
    
    # Run relevant tests
    echo "🔄 Changes detected, running tests..."
    ./bouy test --pytest -- -x
    
    if [ $? -eq 0 ]; then
        echo "✅ Tests passed!"
    else
        echo "❌ Tests failed!"
    fi
done
```

### Scenario 3: Data Recording and Replay

```bash
# Record scraper results to JSON
./bouy recorder
# Runs job and saves to outputs/job_results_TIMESTAMP.json

# Use custom output directory
./bouy recorder --output-dir /backup/scraper-results

# Replay a specific recording
./bouy replay --file outputs/job_results_20240115_103000.json

# Replay all recordings in directory
./bouy replay --directory outputs/

# Use default output directory
./bouy replay --use-default-output-dir

# Preview replay without executing
./bouy replay --dry-run --file outputs/job_results_20240115_103000.json
```

### Scenario 4: Content Store Analysis

```bash
# Check content store status
./bouy content-store status

# Expected output:
# Content Store Status:
# - Total items: 5,432
# - Storage used: 234 MB
# - Last update: 2024-01-15 10:30:00
# - Compression ratio: 3.2:1

# Generate detailed report
./bouy content-store report

# Expected output:
# Content Store Report
# ====================
# Organizations: 1,234
# Services: 2,345
# Locations: 1,853
# ...

# Find duplicate content
./bouy content-store duplicates

# Analyze storage efficiency
./bouy content-store efficiency
```

### Scenario 5: Programmatic Control with Python

```python
#!/usr/bin/env python3
# control_fleet.py

import subprocess
import json

def run_bouy_command(args):
    """Run bouy command and return JSON output."""
    result = subprocess.run(
        ['./bouy', '--json'] + args,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    
    # Parse JSON output (one object per line)
    services = []
    for line in result.stdout.strip().split('\n'):
        if line:
            services.append(json.loads(line))
    return services

# Get service status
services = run_bouy_command(['ps'])
for service in services:
    print(f"{service['name']}: {service['status']}")

# Start services if not running
if not any(s['status'] == 'running' for s in services):
    subprocess.run(['./bouy', 'up'], check=True)
```

---

## Troubleshooting Examples

### Problem: Services Won't Start

```bash
# Check for port conflicts
lsof -i :8000
lsof -i :5432
lsof -i :6379

# Clean up and restart
./bouy clean
./bouy up

# Check Docker status
docker ps -a
docker logs pantry-pirate-radio_app_1
```

### Problem: Tests Failing

```bash
# Run tests with verbose output
./bouy test --pytest -- -vvs

# Run specific failing test
./bouy test --pytest -- tests/test_api.py::TestAPI::test_failing -vvs --pdb

# Check test environment
./bouy shell app
pytest --version
pip list | grep -E "pytest|django"
```

### Problem: Scraper Not Working

```bash
# Test scraper first
./bouy scraper-test problematic_scraper

# Check worker logs
./bouy logs worker | tail -100

# Debug in shell
./bouy shell worker
python -c "from app.scrapers import problematic_scraper; problematic_scraper.test()"

# Check Redis queue
./bouy exec redis redis-cli
> KEYS *
> LLEN default
```

### Problem: Database Issues

```bash
# Check database connection
./bouy exec app python -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
    print('Database connected!')
"

# Run migrations
./bouy exec app python manage.py migrate

# Check migration status
./bouy exec app python manage.py showmigrations

# Access database directly
./bouy exec postgres psql -U postgres -d pantrypirate
```

### Problem: Memory or Performance Issues

```bash
# Check container resource usage
docker stats

# Check specific service
docker stats pantry-pirate-radio_app_1

# View detailed logs
./bouy logs app | grep -i error
./bouy logs worker | grep -i memory

# Restart specific service
docker restart pantry-pirate-radio_worker_1
```

---

## Integration Examples

### Using with CI/CD

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Start services
        run: ./bouy up --test
      
      - name: Run tests
        run: ./bouy --programmatic --quiet test
      
      - name: Stop services
        run: ./bouy down
```

### Using with Make

```makefile
# Makefile
.PHONY: start stop test clean

start:
	./bouy up

stop:
	./bouy down

test:
	./bouy test

clean:
	./bouy clean

dev: start
	./bouy logs

scrape:
	./bouy scraper --all
	./bouy reconciler
	./bouy haarrrvest
```

### Using with Docker Compose Override

```yaml
# docker-compose.override.yml
version: '3.8'

services:
  app:
    environment:
      - DEBUG=True
      - LOG_LEVEL=DEBUG
    volumes:
      - ./custom_config:/app/custom_config
```

---

## Tips and Best Practices

1. **Always use bouy commands** - Never use `docker` or `docker-compose` directly
2. **Check service status** - Run `./bouy ps` before running commands
3. **Use programmatic mode for scripts** - Add `--programmatic` or `--json` for automation
4. **Follow test-driven development** - Write tests first, then implementation
5. **Use dry-run for testing** - Test scrapers with `scraper-test` before running
6. **Monitor logs** - Keep `./bouy logs` running in a separate terminal
7. **Clean up regularly** - Use `./bouy clean` to free up space
8. **Use appropriate environment** - Dev for development, prod for production data
9. **Backup before major changes** - The setup wizard creates automatic backups
10. **Read error messages** - Bouy provides detailed error messages and suggestions

---

## Additional Resources

- [API Documentation](http://localhost:8000/docs) - Interactive Swagger UI (when services are running)
- [Integration Examples](./integrations/) - Language-specific client examples
- [Sample Data](./sample_data/) - HSDS-compliant example data
- [Docker Automation](./docker-automation.py) - Programmatic control example

---

## Getting Help

```bash
# Show help for bouy
./bouy --help

# Show version
./bouy --version

# Check setup status
./bouy claude-auth status

# View detailed logs
./bouy --verbose COMMAND

# Get JSON output for debugging
./bouy --json COMMAND
```

For more information, see the main project documentation or run `./bouy --help` for the latest command options.