# Test Environment Setup

This guide explains how to properly configure and run tests in Pantry Pirate Radio, ensuring complete isolation from production data.

## Overview

The test environment uses separate databases and Redis instances to ensure production data safety. Tests are executed through the `bouy` command, which handles all Docker containerization and environment setup automatically.

## Quick Start

```bash
# Run all tests (pytest, mypy, black, ruff, bandit)
./bouy test

# Run only pytest tests
./bouy test --pytest

# Run specific test file
./bouy test --pytest tests/test_api.py

# Run with verbose output
./bouy test --pytest -- -v
```

## Test Isolation Architecture

### Automatic Test Isolation

When you run tests using `./bouy test`, the following isolation mechanisms are automatically applied:

1. **Separate Test Containers**: Uses `docker-compose.test.yml` configuration
2. **Test Database**: Automatically uses `test_pantry_pirate_radio` database
3. **Redis Database Isolation**: Uses Redis database 1 for tests (database 0 for production)
4. **Environment Variable**: Sets `TESTING=true` to enable test-specific behavior
5. **Key Prefixing**: All test data uses prefixed keys (e.g., `test:worker_id:*`)

### Environment Variables

The test environment automatically configures these variables:

```bash
# Set by bouy test command
TESTING=true                          # Enables test mode
TEST_DATABASE_URL=postgresql+psycopg2://postgres:pirate@db:5432/test_pantry_pirate_radio
TEST_REDIS_URL=redis://cache:6379/1   # Database 1 for tests

# Worker isolation (for parallel tests)
TEST_DB_SCHEMA=test_${worker_id}      # Unique schema per test worker
TEST_REDIS_PREFIX=test:${worker_id}:  # Unique prefix per test worker
TEST_LOG_FILE=test_${worker_id}.log   # Separate log files
```

## Running Tests with Bouy

### All Test Categories

```bash
# Run complete test suite (recommended before commits)
./bouy test

# This runs:
# - pytest (with coverage)
# - mypy (type checking)
# - black (formatting)
# - ruff (linting)
# - bandit (security)
```

### Individual Test Categories

```bash
# Unit tests with coverage
./bouy test --pytest

# Type checking
./bouy test --mypy

# Code formatting
./bouy test --black

# Linting
./bouy test --ruff

# Security scanning
./bouy test --bandit

# Coverage threshold check
./bouy test --coverage
```

### Advanced Testing Options

```bash
# Run specific test files
./bouy test --pytest tests/test_api.py
./bouy test --pytest tests/test_scraper/ tests/test_reconciler/

# Pass arguments to pytest
./bouy test --pytest -- -v                    # Verbose output
./bouy test --pytest -- -x                    # Stop on first failure
./bouy test --pytest -- --pdb                 # Drop to debugger on failure
./bouy test --pytest -- -k test_name          # Run tests matching pattern
./bouy test --pytest -- --lf                  # Run last failed tests

# Combine multiple options
./bouy test --pytest -- -vsx -k api          # Verbose, stop on failure, match 'api'

# Type check specific paths
./bouy test --mypy app/api/

# Format specific paths
./bouy test --black app/api/ tests/
```

### Output Formats

```bash
# Standard output (default)
./bouy test --pytest

# Programmatic mode (structured output for CI)
./bouy --programmatic test --pytest

# JSON output
./bouy --json test --pytest

# Quiet mode (minimal output)
./bouy --quiet test --pytest

# No color (for log files)
./bouy --no-color test --pytest
```

## Test Database Management

### Automatic Database Setup

The test database is automatically created and managed when using `./bouy test`:

```bash
# Database is created automatically when running tests
./bouy test --pytest

# The test database (test_pantry_pirate_radio) is:
# - Created if it doesn't exist
# - Isolated from production database
# - Cleaned between test runs
```

### Manual Database Operations

```bash
# Connect to test database
./bouy exec db psql -U postgres -d test_pantry_pirate_radio

# Drop and recreate test database
./bouy exec db psql -U postgres -c "DROP DATABASE IF EXISTS test_pantry_pirate_radio;"
./bouy exec db psql -U postgres -c "CREATE DATABASE test_pantry_pirate_radio;"

# Check test database status
./bouy exec db psql -U postgres -l | grep test_pantry_pirate_radio
```

## Safety Features

### Built-in Protection Mechanisms

1. **Database Name Validation**: Test database URL must contain "test" in the name
2. **URL Comparison**: Test URLs are verified to be different from production URLs
3. **No Direct flushdb()**: Redis tests use key prefixes instead of flushing entire database
4. **Transaction Rollback**: Database changes are rolled back after each test
5. **Worker Isolation**: Parallel test execution uses separate namespaces

### Safety Verification

```bash
# Verify test isolation is properly configured
./bouy exec app bash /app/scripts/verify-test-isolation.sh

# Output shows:
# ✅ TEST_DATABASE_URL is set and different from DATABASE_URL
# ✅ TEST_REDIS_URL is set and different from REDIS_URL
# ✅ Test database name contains 'test'
# ✅ Redis uses different database number
```

## Coverage Reports

### Viewing Coverage

```bash
# Run tests with coverage
./bouy test --pytest

# Coverage reports are generated in multiple formats:
# - Terminal output (shown immediately)
# - coverage.xml (for CI tools)
# - coverage.json (for automation)
# - htmlcov/index.html (interactive HTML report)

# Open HTML coverage report
open htmlcov/index.html       # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage Thresholds

```bash
# Check if coverage meets minimum threshold
./bouy test --coverage

# Default threshold: 80%
# Configure in pyproject.toml:
# [tool.coverage.report]
# fail_under = 80
```

## Debugging Tests

### Interactive Debugging

```bash
# Drop to debugger on failure
./bouy test --pytest -- --pdb

# Show local variables on failure
./bouy test --pytest -- -l

# Run tests with full traceback
./bouy test --pytest -- --tb=long
```

### Test Logs

```bash
# View test output with logging
./bouy test --pytest -- -s          # Don't capture output
./bouy test --pytest -- --log-cli-level=DEBUG  # Show debug logs

# Check test container logs
./bouy logs app --tail 100
```

## Parallel Test Execution

Tests can run in parallel for faster execution:

```bash
# Run tests in parallel (auto-detects CPU cores)
./bouy test --pytest -- -n auto

# Run with specific number of workers
./bouy test --pytest -- -n 4

# Each worker gets isolated:
# - Database schema (test_gw0, test_gw1, etc.)
# - Redis namespace (test:gw0:*, test:gw1:*, etc.)
# - Log file (test_gw0.log, test_gw1.log, etc.)
```

## CI/CD Integration

### GitHub Actions Example

```yaml
# Tests are automatically run in CI with proper isolation
- name: Run tests
  run: |
    ./bouy --programmatic --quiet test
```

### Local CI Simulation

```bash
# Simulate CI environment locally
CI=true SKIP_DB_INIT=true ./bouy test

# Run with same output format as CI
./bouy --programmatic --quiet test
```

## Troubleshooting

### Common Issues and Solutions

1. **Database Connection Errors**
   ```bash
   # Ensure database service is running
   ./bouy ps | grep db
   
   # Restart database if needed
   ./bouy down db && ./bouy up db
   ```

2. **Permission Denied Errors**
   ```bash
   # Ensure Docker daemon is running
   docker ps
   
   # Check Docker permissions
   docker run hello-world
   ```

3. **Test Database Not Created**
   ```bash
   # Manually create test database
   ./bouy exec db psql -U postgres -c "CREATE DATABASE test_pantry_pirate_radio;"
   ```

4. **Redis Connection Errors**
   ```bash
   # Check Redis service
   ./bouy ps | grep cache
   
   # Test Redis connection
   ./bouy exec cache redis-cli ping
   ```

5. **Coverage Report Not Generated**
   ```bash
   # Ensure pytest-cov is installed
   ./bouy exec app pip list | grep pytest-cov
   
   # Run with explicit coverage
   ./bouy test --coverage
   ```

## Best Practices

1. **Always Use Bouy for Tests**: Never run pytest directly; always use `./bouy test`
2. **Run Full Suite Before Commits**: Use `./bouy test` to run all checks
3. **Keep Tests Fast**: Use mocks and fixtures to avoid slow external calls
4. **Clean Test Data**: Ensure tests clean up after themselves
5. **Use Fixtures**: Leverage pytest fixtures for common test data
6. **Test in Isolation**: Each test should be independent and repeatable

## Migration from Legacy Setup

If you previously ran tests without bouy:

1. **Stop all direct pytest commands**
2. **Remove any local test databases** (if created outside Docker)
3. **Use bouy exclusively**: `./bouy test --pytest`
4. **Verify isolation**: `./bouy exec app bash /app/scripts/verify-test-isolation.sh`

## Environment-Specific Notes

### Development Environment

```bash
# Standard test execution
./bouy test --pytest

# Quick test during development
./bouy test --pytest tests/test_current_feature.py
```

### CI Environment

```bash
# CI automatically sets these variables
CI=true
SKIP_DB_INIT=true
TESTING=true

# Tests run with programmatic output
./bouy --programmatic test
```

### Production Environment

```bash
# Never run tests in production!
# Tests should only run in development and CI environments
```

## Related Documentation

- [Database Backup](./database-backup.md) - Backup and restore procedures
- [Architecture](./architecture.md) - System design and component overview
- [Recorder Service](./recorder.md) - Recording and replaying job results
- [CLAUDE.md](../CLAUDE.md) - Development workflow and commands