# Testing Guide - Pantry Pirate Radio

This comprehensive guide covers testing in the Pantry Pirate Radio project using the bouy toolchain. All testing is performed through Docker containers with the `./bouy` command - no local Python installation required.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Testing Philosophy](#testing-philosophy)
3. [Test Directory Structure](#test-directory-structure)
4. [Running Tests with Bouy](#running-tests-with-bouy)
5. [Test Categories](#test-categories)
6. [Coverage Requirements](#coverage-requirements)
7. [Test Fixtures and Utilities](#test-fixtures-and-utilities)
8. [Environment Variables](#environment-variables)
9. [Debugging Test Failures](#debugging-test-failures)
10. [Writing Effective Tests](#writing-effective-tests)
11. [CI/CD Integration](#cicd-integration)
12. [Common Test Patterns](#common-test-patterns)

## Quick Start

```bash
# Run all CI checks (recommended before commits)
./bouy test

# Run specific test categories
./bouy test --pytest         # Unit and integration tests
./bouy test --mypy          # Type checking
./bouy test --black         # Code formatting
./bouy test --ruff          # Linting
./bouy test --bandit        # Security scanning

# Run specific test files
./bouy test --pytest tests/test_api_endpoints_unit.py

# Run with additional arguments
./bouy test --pytest -- -v -x  # Verbose output, stop on first failure
```

## Testing Philosophy

This project follows **Test-Driven Development (TDD)** principles:

### The TDD Cycle

1. **Red Phase**: Write a failing test that defines desired behavior
2. **Green Phase**: Write minimal code to make the test pass
3. **Refactor Phase**: Improve code while keeping tests passing

### Example TDD Workflow

```bash
# 1. Create test file first
touch tests/test_new_feature.py

# 2. Write failing test
cat > tests/test_new_feature.py << 'EOF'
def test_new_feature_behavior():
    """Test that new feature works as expected."""
    from app.new_feature import process_data
    result = process_data("input")
    assert result == "expected_output"
EOF

# 3. Run test (should fail)
./bouy test --pytest tests/test_new_feature.py

# 4. Implement minimal code to pass
# ... write implementation in app/new_feature.py ...

# 5. Run test again (should pass)
./bouy test --pytest tests/test_new_feature.py

# 6. Refactor and ensure tests still pass
./bouy test --pytest tests/test_new_feature.py

# 7. Run full test suite before committing
./bouy test
```

## Test Directory Structure

```
tests/
├── README_BOUY_TESTS.md           # This file
├── conftest.py                    # Global test configuration
├── fixtures/                      # Shared test fixtures
│   ├── api.py                    # API client fixtures
│   ├── cache.py                  # Redis cache fixtures
│   ├── content_store.py          # Content store fixtures
│   ├── db.py                     # Database fixtures
│   └── websocket.py              # WebSocket fixtures
│
├── bouy_tests/                   # Bouy script tests (run outside Docker)
│   ├── test_bouy_unit.py        # Unit tests for bouy functions
│   ├── test_bouy_integration.py # Integration tests
│   └── test_bouy_setup.py       # Setup wizard tests
│
├── test_api_*.py                 # API endpoint tests
├── test_core/                    # Core functionality tests
│   ├── test_config.py           # Configuration tests
│   ├── test_geocoding.py        # Geocoding service tests
│   └── test_logging.py          # Logging system tests
│
├── test_database/                # Database layer tests
│   ├── test_models.py           # ORM model tests
│   └── test_geo_utils.py        # Geographic utility tests
│
├── test_llm/                     # LLM integration tests
│   ├── test_processor.py        # Job processor tests
│   ├── test_queue.py            # Queue management tests
│   └── test_validation.py       # Response validation tests
│
├── test_reconciler/              # Data reconciliation tests
│   ├── test_reconciler.py       # Main reconciler tests
│   └── test_merge_strategy.py   # Merge strategy tests
│
├── test_scraper/                 # Scraper tests
│   ├── test_*_scraper.py        # Individual scraper tests
│   └── utilities/               # Scraper testing utilities
│
└── test_performance/             # Performance benchmarks
    └── test_benchmarks.py        # Benchmark tests
```

## Running Tests with Bouy

### Basic Test Commands

```bash
# Run all tests and checks (recommended)
./bouy test

# Run specific test types
./bouy test --pytest         # Tests with coverage
./bouy test --mypy          # Type checking
./bouy test --black         # Code formatting
./bouy test --ruff          # Linting
./bouy test --bandit        # Security analysis
./bouy test --coverage      # Coverage analysis
./bouy test --vulture       # Dead code detection
./bouy test --safety        # Dependency vulnerabilities
./bouy test --pip-audit     # Pip security audit
./bouy test --xenon         # Code complexity
```

### Running Specific Tests

```bash
# Test a specific file
./bouy test --pytest tests/test_api_endpoints_unit.py

# Test a specific directory
./bouy test --pytest tests/test_llm/

# Test multiple files
./bouy test --pytest tests/test_api_endpoints_unit.py tests/test_core/

# Test a specific function
./bouy test --pytest -- tests/test_api_endpoints_unit.py::TestAPIEndpoints::test_get_organizations

# Test by pattern matching
./bouy test --pytest -- -k "test_geocoding"
./bouy test --pytest -- -k "test_api or test_reconciler"
```

### Advanced Test Options

```bash
# Verbose output
./bouy test --pytest -- -v

# Extra verbose (show print statements)
./bouy test --pytest -- -vv

# Stop on first failure
./bouy test --pytest -- -x

# Drop to debugger on failure
./bouy test --pytest -- --pdb

# Show local variables on failure
./bouy test --pytest -- -l

# Run last failed tests
./bouy test --pytest -- --lf

# Run failed tests first, then others
./bouy test --pytest -- --ff

# Show slowest N tests
./bouy test --pytest -- --durations=10

# Parallel execution (if pytest-xdist installed)
./bouy test --pytest -- -n auto
```

### Output Formats

```bash
# Normal output (default)
./bouy test --pytest

# Programmatic mode (structured for CI)
./bouy --programmatic test --pytest

# JSON output
./bouy --json test --pytest

# Quiet mode (minimal output)
./bouy --quiet test --pytest

# No color codes (for log files)
./bouy --no-color test --pytest

# Combine modes
./bouy --programmatic --quiet test
```

## Test Categories

### Unit Tests
- Test individual functions and classes in isolation
- Mock external dependencies
- Fast execution
- Example: `test_api_utils_unit.py`

### Integration Tests
- Test interactions between components
- Use real database and Redis connections
- May involve multiple services
- Example: `test_api_integration_simple.py`

### End-to-End Tests
- Test complete workflows
- Include all system components
- Slower but comprehensive
- Example: `test_reconciler/test_reconciler.py`

### Performance Tests
- Benchmark critical operations
- Track performance regressions
- Example: `test_performance/test_benchmarks.py`

## Coverage Requirements

### Viewing Coverage Reports

```bash
# Run tests with coverage
./bouy test --pytest

# Coverage reports are generated in multiple formats:
# - Terminal output (immediate feedback)
# - htmlcov/index.html (detailed HTML report)
# - coverage.xml (for CI tools)
# - coverage.json (for automation)

# View HTML coverage report
open htmlcov/index.html      # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage Configuration

Coverage is configured in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["app"]
omit = [
    "app/__main__.py",
    "app/*/migrations/*",
    "app/scraper/*_scraper.py",  # External dependencies
]

[tool.coverage.report]
show_missing = true
precision = 2
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

### Coverage Goals

- Maintain minimum 80% overall coverage
- Critical paths (API, data processing): 90%+
- New code should include comprehensive tests
- Use `# pragma: no cover` sparingly for unreachable code

## Test Fixtures and Utilities

### Database Fixtures (`fixtures/db.py`)

```python
@pytest.fixture
async def db_session():
    """Provide a transactional database session."""
    # Automatically rolled back after each test
    
@pytest.fixture
def test_organization(db_session):
    """Create a test organization."""
    # Returns a fully configured organization
```

### API Client Fixtures (`fixtures/api.py`)

```python
@pytest.fixture
def api_client():
    """Provide a test API client."""
    # Configured for testing with proper auth
    
@pytest.fixture
def authenticated_client(api_client):
    """API client with authentication."""
    # Pre-authenticated for protected endpoints
```

### Cache Fixtures (`fixtures/cache.py`)

```python
@pytest.fixture
def redis_client():
    """Provide a Redis client for testing."""
    # Isolated namespace per test worker
    
@pytest.fixture
def cache_store(redis_client):
    """Provide a cache store instance."""
    # Cleared after each test
```

## Environment Variables

### Test Environment Variables

```bash
# Automatically set by bouy test commands
TESTING=true                    # Enable test mode
TEST_DB_SCHEMA=test_${worker}  # Isolated DB schema
TEST_REDIS_PREFIX=test:${worker}: # Isolated Redis namespace
TEST_LOG_FILE=test_${worker}.log # Separate log files

# Optional configuration
TEST_PARALLEL=true              # Enable parallel test execution
TEST_VERBOSE=true              # Verbose test output
TEST_COVERAGE_MIN=80           # Minimum coverage threshold
```

### Using Environment Variables in Tests

```python
import os
import pytest

@pytest.mark.skipif(
    not os.environ.get("INTEGRATION_TESTS"),
    reason="Integration tests disabled"
)
def test_external_service():
    """Test that requires external service."""
    pass

def test_with_env_config():
    """Test using environment configuration."""
    debug_mode = os.environ.get("DEBUG", "false").lower() == "true"
    assert not debug_mode  # Should be false in tests
```

## Debugging Test Failures

### Using Test Suite Monitor

For comprehensive test analysis, use the @agent-test-suite-monitor:

```bash
# After test failures
@agent-test-suite-monitor "Debug failing authentication tests"

# For specific test investigation
@agent-test-suite-monitor "Run only pytest tests for the API module"

# For performance analysis
@agent-test-suite-monitor "Check test execution times and identify slow tests"
```

### Interactive Debugging

```bash
# Drop into debugger on failure
./bouy test --pytest -- --pdb

# Set breakpoint in test code
def test_complex_logic():
    import pdb; pdb.set_trace()  # Breakpoint
    result = complex_function()
    assert result == expected

# Use ipdb for better experience
def test_with_ipdb():
    import ipdb; ipdb.set_trace()  # Enhanced debugger
```

### Viewing Test Logs

```bash
# Run tests with captured output
./bouy test --pytest -- -s

# View test logs from container
./bouy logs app | grep TEST

# Check test-specific log files
./bouy exec app cat /app/test_master.log
```

### Common Debugging Commands

```bash
# Re-run last failed tests
./bouy test --pytest -- --lf

# Run specific problematic test
./bouy test --pytest -- tests/test_file.py::test_function -vvs

# Check test environment
./bouy exec app python -c "import os; print(os.environ.get('TESTING'))"

# Verify database connection
./bouy exec app python -c "from app.database import engine; print(engine.url)"
```

## Writing Effective Tests

### Test Naming Conventions

```python
# Use descriptive test names
def test_api_returns_404_for_nonexistent_organization():
    """Test that API returns 404 for non-existent organization."""
    pass

# Group related tests in classes
class TestOrganizationAPI:
    def test_create_organization_with_valid_data(self):
        pass
    
    def test_create_organization_with_invalid_data_returns_400(self):
        pass
```

### Test Structure (AAA Pattern)

```python
def test_calculate_distance():
    """Test distance calculation between two points."""
    # Arrange - Set up test data
    point1 = (37.7749, -122.4194)  # San Francisco
    point2 = (34.0522, -118.2437)  # Los Angeles
    
    # Act - Execute the function
    distance = calculate_distance(point1, point2)
    
    # Assert - Verify the result
    assert 540 < distance < 560  # ~550 km
```

### Using Fixtures Effectively

```python
@pytest.fixture
def sample_organization_data():
    """Provide sample organization data."""
    return {
        "name": "Test Food Bank",
        "description": "A test organization",
        "email": "test@example.com",
        "latitude": 37.7749,
        "longitude": -122.4194,
    }

def test_create_organization(api_client, sample_organization_data):
    """Test creating an organization via API."""
    response = api_client.post("/organizations", json=sample_organization_data)
    assert response.status_code == 201
    assert response.json()["name"] == sample_organization_data["name"]
```

### Mocking External Dependencies

```python
from unittest.mock import Mock, patch

@patch("app.services.geocoding.geocode_address")
def test_geocoding_fallback(mock_geocode):
    """Test geocoding with fallback behavior."""
    # Configure mock
    mock_geocode.side_effect = [None, {"lat": 37.7749, "lon": -122.4194}]
    
    # Test fallback behavior
    result = process_address_with_fallback("123 Main St")
    
    # Verify mock was called twice (primary + fallback)
    assert mock_geocode.call_count == 2
    assert result["lat"] == 37.7749
```

### Parametrized Tests

```python
import pytest

@pytest.mark.parametrize("input_value,expected", [
    ("", False),
    ("invalid-email", False),
    ("test@example.com", True),
    ("user+tag@domain.co.uk", True),
])
def test_email_validation(input_value, expected):
    """Test email validation with various inputs."""
    assert is_valid_email(input_value) == expected
```

## CI/CD Integration

### GitHub Actions Integration

Tests run automatically in CI with these jobs:

1. **Main Test Job** (`pytest`): Runs inside Docker containers
   - All application tests
   - Coverage reporting
   - Type checking, linting, formatting

2. **Bouy Test Job** (`bouy-tests`): Runs on native runner
   - Tests for the bouy script itself
   - Cannot run inside Docker

### Running CI Tests Locally

```bash
# Simulate CI environment
./bouy --programmatic --quiet test

# Run with JSON output for parsing
./bouy --json test --pytest

# Check specific CI requirements
./bouy test --coverage  # Verify coverage meets threshold
./bouy test --mypy     # Ensure type safety
./bouy test --black    # Check formatting
```

## Common Test Patterns

### Testing Async Code

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_function():
    """Test asynchronous function."""
    result = await async_operation()
    assert result == expected_value

# Alternative using pytest-asyncio fixture
async def test_with_async_fixture(async_client):
    """Test with async fixture."""
    response = await async_client.get("/api/endpoint")
    assert response.status_code == 200
```

### Testing Database Operations

```python
def test_database_transaction(db_session):
    """Test database transaction rollback."""
    # Create test data
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.commit()
    
    # Verify creation
    assert org.id is not None
    
    # Transaction automatically rolled back after test
```

### Testing API Endpoints

```python
def test_api_endpoint_with_auth(authenticated_client):
    """Test protected API endpoint."""
    response = authenticated_client.get("/api/protected")
    assert response.status_code == 200
    assert "data" in response.json()

def test_api_error_handling(api_client):
    """Test API error responses."""
    response = api_client.get("/api/organizations/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"
```

### Testing with Time

```python
from datetime import datetime, timedelta
from freezegun import freeze_time

@freeze_time("2024-01-01 12:00:00")
def test_time_dependent_function():
    """Test function that depends on current time."""
    result = get_current_timestamp()
    assert result == datetime(2024, 1, 1, 12, 0, 0)
```

### Testing File Operations

```python
import tempfile
from pathlib import Path

def test_file_processing():
    """Test file processing functionality."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as f:
        # Write test data
        f.write('{"test": "data"}')
        f.flush()
        
        # Process file
        result = process_json_file(Path(f.name))
        assert result["test"] == "data"
```

## Best Practices

### Do's
- ✅ Write tests before implementation (TDD)
- ✅ Keep tests simple and focused
- ✅ Use descriptive test names
- ✅ Test edge cases and error conditions
- ✅ Use fixtures for common setup
- ✅ Mock external dependencies
- ✅ Run full test suite before committing

### Don'ts
- ❌ Don't test implementation details
- ❌ Don't write tests that depend on test order
- ❌ Don't use production credentials in tests
- ❌ Don't ignore flaky tests
- ❌ Don't commit with failing tests
- ❌ Don't use `time.sleep()` in tests
- ❌ Don't test third-party libraries

## Troubleshooting

### Common Issues and Solutions

**Issue**: Tests pass locally but fail in CI
```bash
# Ensure same environment
./bouy test  # Use bouy, not local poetry
# Check for environment-specific issues
./bouy --programmatic test --pytest
```

**Issue**: Database connection errors
```bash
# Verify database is running
./bouy ps
# Check database logs
./bouy logs db
# Restart services
./bouy down && ./bouy up
```

**Issue**: Coverage below threshold
```bash
# Find uncovered lines
./bouy test --pytest
# View detailed HTML report
open htmlcov/index.html
# Focus on critical paths first
```

**Issue**: Slow test execution
```bash
# Identify slow tests
./bouy test --pytest -- --durations=10
# Run tests in parallel
./bouy test --pytest -- -n auto
# Consider marking slow tests
@pytest.mark.slow
```

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Test-Driven Development Guide](https://testdriven.io/)
- [Python Testing Best Practices](https://realpython.com/pytest-python-testing/)
- Project-specific patterns in existing test files

---

**Remember**: Always use `./bouy test` commands for testing. This ensures consistent environments, proper isolation, and accurate results across all development and CI/CD environments.