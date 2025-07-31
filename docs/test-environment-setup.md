# Test Environment Setup

This guide explains how to properly configure your test environment to prevent tests from affecting production data.

## Critical: Test Data Isolation

**⚠️ WARNING**: Previous versions of the test suite could accidentally clear production databases. This has been fixed, but you MUST configure test-specific databases to ensure data safety.

## Required Configuration

### 1. Set up Test Environment Variables

Tests now require separate `TEST_DATABASE_URL` and `TEST_REDIS_URL` environment variables. These MUST point to different databases than your production instances.

```bash
# Copy the test environment template
cp .env.test .env

# Edit .env to add test database URLs
# Make sure these are DIFFERENT from your production URLs!

# For local development:
TEST_DATABASE_URL=postgresql+psycopg2://postgres:test@localhost:5432/test_pantry_pirate_radio
TEST_REDIS_URL=redis://localhost:6379/1  # Use DB 1 for tests, DB 0 for production

# For VS Code dev container:
TEST_DATABASE_URL=postgresql+psycopg2://postgres:your_secure_password@db:5432/test_pantry_pirate_radio
TEST_REDIS_URL=redis://cache:6379/1  # Use DB 1 on same Redis instance
```

### 2. Create Test Databases

#### PostgreSQL Test Database
```bash
# Create a separate test database
createdb test_pantry_pirate_radio

# Or using psql
psql -U postgres -c "CREATE DATABASE test_pantry_pirate_radio;"
```

#### Redis Test Database
Redis supports multiple databases (0-15 by default). Use a different database number for tests:
- Production: `redis://localhost:6379/0` (database 0)
- Tests: `redis://localhost:6379/1` (database 1)

### 3. Docker Setup for Tests

If using Docker, create separate test containers:

```yaml
# docker-compose.test.yml
services:
  test_db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: test
      POSTGRES_DB: test_pantry_pirate_radio
    ports:
      - "5433:5432"  # Different port to avoid conflicts

  test_cache:
    image: redis:7-alpine
    ports:
      - "6380:6379"  # Different port to avoid conflicts
```

Then update your test URLs:
```bash
TEST_DATABASE_URL=postgresql+psycopg2://postgres:test@localhost:5433/test_pantry_pirate_radio
TEST_REDIS_URL=redis://localhost:6380/0
```

## Safety Features

The test suite now includes multiple safety checks:

1. **Configuration Validation**: Tests verify that `TEST_DATABASE_URL` and `TEST_REDIS_URL` are different from production URLs
2. **Name Checking**: Test fixtures ensure database/Redis URLs contain "test" in the name
3. **No flushdb()**: Redis fixtures no longer use `flushdb()`. Instead, they use test-specific key prefixes
4. **Key Isolation**: All test data uses prefixed keys (e.g., `test:12345:*`) that are cleaned up after each test

## Running Tests Safely

```bash
# Run all tests
./bouy test --pytest

# Run with verbose output to see safety checks
./bouy test --pytest -- -v

# Run a specific test file
./bouy test --pytest tests/test_specific.py
```

## Troubleshooting

### Error: "TEST_DATABASE_URL is the same as DATABASE_URL!"
- Ensure you've set `TEST_DATABASE_URL` in your .env file
- Verify it points to a different database than `DATABASE_URL`

### Error: "Database URL doesn't appear to be a test database!"
- The test database URL must contain the word "test"
- Example: `test_pantry_pirate_radio` ✓
- Bad example: `pantry_pirate_radio` ✗

### Redis Data Still Being Cleared
- Check that `TEST_REDIS_URL` uses a different database number
- Verify Redis fixtures are using the test prefix properly

## Best Practices

1. **Never share databases**: Test and production databases should be completely separate
2. **Use descriptive names**: Include "test" in database names for clarity
3. **Regular cleanup**: Periodically drop and recreate test databases to avoid bloat
4. **CI/CD isolation**: Ensure CI environments also use separate test databases

## Migration from Old Setup

If you were previously running tests without separate test databases:

1. **Stop all tests immediately**
2. Back up your production data
3. Follow the setup steps above
4. Verify test isolation before running tests again

Remember: Test data isolation is critical for preventing accidental data loss!

## VS Code Dev Container Notes

When using the VS Code dev container:

1. The test database needs to be created manually:
   ```bash
   psql -U postgres -h db -c "CREATE DATABASE test_pantry_pirate_radio"
   ```

2. Use database 1 for Redis tests (database 0 is for development):
   ```bash
   TEST_REDIS_URL=redis://cache:6379/1
   ```

3. The test configuration automatically uses key prefixes to isolate test data

4. Run tests with environment variables:
   ```bash
   export TEST_DATABASE_URL="postgresql+psycopg2://postgres:your_secure_password@db:5432/test_pantry_pirate_radio"
   export TEST_REDIS_URL="redis://cache:6379/1"
   ./bouy test --pytest
   ```

   Note: The test environment is automatically configured when using bouy.