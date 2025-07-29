# Bouy Script Tests

This directory contains comprehensive tests for the `bouy` Docker fleet management script.

## Test Structure

```
tests/
├── test_bouy_unit.py          # Unit tests for individual bouy functions
├── test_bouy_integration.py   # Integration tests with mocked docker compose
├── test_bouy_docker.py        # Tests designed to run inside Docker container
├── test_bouy.sh               # Shell script test runner
└── shell/
    └── fixtures/
        └── mock_compose.sh    # Mock docker compose for testing
```

## Running Tests

### 1. Run all tests via bouy (recommended)
```bash
./bouy test pytest
```

### 2. Run bouy-specific tests only
```bash
# Using pytest directly
poetry run pytest tests/test_bouy_*.py -v

# Using the shell test runner
./tests/test_bouy.sh
```

### 3. Run tests in CI
The tests are automatically run as part of the CI checks:
```bash
./scripts/run-ci-checks.sh
```

## Test Categories

### Unit Tests (`test_bouy_unit.py`)
- Tests individual functions from the bouy script
- Validates output formatting (JSON, text)
- Tests parse_mode function
- Tests dependency checking functions
- Tests input validation

### Integration Tests (`test_bouy_integration.py`)
- Tests complete command workflows
- Uses comprehensive docker compose mocking
- Tests error handling
- Tests different operational modes (dev, prod, test)

### Docker Tests (`test_bouy_docker.py`)
- Designed to run inside the Docker test container
- Tests bouy functionality in the actual Docker environment
- Uses mock responses for docker compose commands

### Shell Tests (`test_bouy.sh`)
- Quick smoke tests for basic functionality
- Can be run standalone
- Tests exit codes and basic command structure

## Test Mode

The bouy script supports a test mode that allows overriding the docker compose command:

```bash
# Enable test mode
export BOUY_TEST_MODE=1

# Specify custom compose command (optional)
export BOUY_TEST_COMPOSE_CMD="/path/to/mock/compose"

# Run bouy commands
./bouy status
```

## Mock Docker Compose

The `mock_compose.sh` script simulates docker compose behavior for testing:
- Returns appropriate JSON for `ps --format json` commands
- Simulates service startup/shutdown
- Provides mock responses for all bouy-supported operations
- Handles database, Redis, and content store checks

## Writing New Tests

When adding new functionality to bouy:

1. Add unit tests for any new functions in `test_bouy_unit.py`
2. Add integration tests for new commands in `test_bouy_integration.py`
3. Update `mock_compose.sh` to handle any new docker compose commands
4. Add shell tests in `test_bouy.sh` for basic smoke testing

## Coverage

The bouy tests are included in the overall test coverage metrics. To see coverage specifically for bouy tests:

```bash
poetry run pytest tests/test_bouy_*.py --cov=. --cov-report=html
```

Note: Since bouy is a shell script, traditional Python coverage tools won't track its execution. The tests focus on behavior verification rather than line coverage.