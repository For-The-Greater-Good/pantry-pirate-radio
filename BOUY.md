# ⚓ Bouy - Docker Fleet Management for Pantry Pirate Radio

Navigate the seas of containers with ease! Bouy is the official Docker fleet management tool for Pantry Pirate Radio, providing a unified interface for all Docker operations.

## Table of Contents
- [Overview](#overview)
- [Installation](#installation)
- [Global Options](#global-options)
- [Commands Reference](#commands-reference)
- [Testing with Bouy](#testing-with-bouy)
- [Programmatic Mode](#programmatic-mode)
- [Common Workflows](#common-workflows)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

## Overview

Bouy (v1.0.0) is a comprehensive bash script that wraps Docker Compose with intelligent defaults, health checks, and developer-friendly features. It's the **only** supported way to interact with the Pantry Pirate Radio Docker environment.

### Key Features
- 🚀 Single command interface for all Docker operations
- 🔍 Automatic health checks and dependency verification
- 📊 Programmatic mode with JSON output for automation
- 🧪 Integrated testing with coverage reporting
- 🔐 Built-in authentication management for LLM providers
- 📝 Structured logging with multiple output formats
- 🛡️ Comprehensive error handling and recovery

## Installation

Bouy comes pre-installed in the repository. No additional setup required!

```bash
# Make sure it's executable
chmod +x ./bouy

# Verify installation
./bouy --version
```

## Global Options

These options can be used with any bouy command:

| Option | Description | Example |
|--------|-------------|---------|
| `--programmatic` | Enable structured output for automation | `./bouy --programmatic up` |
| `--json` | Output in JSON format (implies --programmatic) | `./bouy --json ps` |
| `--verbose` | Enable verbose output | `./bouy --verbose up` |
| `--quiet` | Suppress non-error output | `./bouy --quiet test` |
| `--no-color` | Disable colored output | `./bouy --no-color logs` |
| `--version`, `-v` | Show version information | `./bouy --version` |

### Combining Global Options
```bash
./bouy --programmatic --quiet up            # Minimal structured output
./bouy --json --verbose ps                  # Detailed JSON output
./bouy --programmatic --no-color logs app   # Plain text structured logs
```

## Commands Reference

### Service Management

#### `up` - Start services
```bash
./bouy up                      # Start in dev mode (default)
./bouy up --prod              # Start in production mode
./bouy up --test              # Start in test mode
./bouy up --with-init         # Start with database initialization
./bouy up app worker          # Start specific services only
./bouy up --dev --with-init   # Combine options
```

#### `down` - Stop services
```bash
./bouy down                    # Stop all services
```

#### `ps` - List services
```bash
./bouy ps                      # List running services
./bouy --json ps              # JSON format (for automation)
```

#### `build` - Build services
```bash
./bouy build                   # Build all services
./bouy build app              # Build specific service
./bouy build --prod app       # Build for production
```

#### `clean` - Clean environment
```bash
./bouy clean                   # Stop services and remove volumes
```

### Logs and Debugging

#### `logs` - View logs
```bash
./bouy logs                    # View all logs (follows by default)
./bouy logs app               # View specific service logs
./bouy logs --no-color app    # Plain text logs
./bouy --programmatic logs app # Structured output (doesn't follow)
```

#### `shell` - Open shell
```bash
./bouy shell app              # Open bash/sh in container
./bouy shell worker           # Shell access to worker
```

#### `exec` - Execute commands
```bash
./bouy exec app python --version          # Run command
./bouy exec app ls -la                    # List files
./bouy exec worker poetry show            # Show dependencies
./bouy --programmatic exec app echo test  # No TTY for scripts
```

### Scraper Operations

#### `scraper` - Run scrapers
```bash
./bouy scraper --list                     # List available scrapers
./bouy scraper --all                      # Run all scrapers
./bouy scraper nyc_efap_programs          # Run specific scraper
./bouy --programmatic scraper --list      # Machine-readable list
./bouy --quiet scraper food_bank_for_nyc  # Minimal output
```

#### `scraper-test` - Test scrapers
```bash
./bouy scraper-test --all                 # Test all scrapers (dry run)
./bouy scraper-test nyc_efap_programs     # Test specific scraper
```

### Data Management

#### `reconciler` - Process job results
```bash
./bouy reconciler                         # Run reconciler
./bouy reconciler --force                 # Force processing
```

#### `recorder` - Save job results
```bash
./bouy recorder                           # Save results to JSON
./bouy recorder --output-dir /custom/path # Custom output directory
```

#### `replay` - Replay recorded data
```bash
./bouy replay                             # Show help
./bouy replay --file path/to/file.json    # Replay single file
./bouy replay --directory path/to/dir     # Replay directory
./bouy replay --use-default-output-dir    # Use outputs directory
./bouy replay --dry-run                   # Preview without executing
```

#### `datasette` - Export to SQLite
```bash
./bouy datasette                          # Export immediately
./bouy datasette export                   # Same as above
./bouy datasette schedule                 # Start periodic export
./bouy datasette status                   # Check export status
```

### Content Store

#### `content-store` - Deduplication management
```bash
./bouy content-store status               # Show status
./bouy content-store report               # Detailed report
./bouy content-store duplicates           # Find duplicates
./bouy content-store efficiency           # Analyze efficiency
```

### HAARRRvest Publisher

#### `haarrrvest` - Publish to repository
```bash
./bouy haarrrvest                         # Manual publish
./bouy haarrrvest run                     # Same as above
./bouy haarrrvest logs                    # View logs
./bouy haarrrvest status                  # Check status
```

### Authentication

#### `claude-auth` - Claude authentication
```bash
./bouy claude-auth                        # Interactive auth
./bouy claude-auth setup                  # Setup auth
./bouy claude-auth status                 # Check status
./bouy claude-auth test                   # Test connection
./bouy claude-auth config                 # Show config
```

## Testing with Bouy

Bouy provides comprehensive testing capabilities with multiple options for running tests.

### Running All Tests
```bash
./bouy test                               # Run all CI checks
```

This runs the complete test suite including:
- pytest with coverage
- mypy type checking
- black code formatting
- ruff linting
- bandit security scanning

### Running Specific Test Types
```bash
./bouy test --pytest                      # Run pytest with coverage
./bouy test --mypy                        # Type checking only
./bouy test --black                       # Code formatting check
./bouy test --ruff                        # Linting only
./bouy test --bandit                      # Security scan only
./bouy test --coverage                    # Tests with coverage threshold
```

### Running Specific Test Files
```bash
# Test a specific file
./bouy test --pytest tests/test_api.py

# Test a directory
./bouy test --pytest tests/test_scraper/

# Test multiple files
./bouy test --pytest tests/test_api.py tests/test_reconciler.py
```

### Passing Additional Arguments

Use `--` to pass arguments to the underlying test command:

```bash
# Verbose output
./bouy test --pytest -- -v

# Run tests matching a pattern
./bouy test --pytest -- -k test_name
./bouy test --pytest -- -k "test_api or test_reconciler"

# Stop on first failure
./bouy test --pytest -- -x

# Drop to debugger on failure
./bouy test --pytest -- --pdb

# Show local variables on failure
./bouy test --pytest -- -l

# Run specific test function
./bouy test --pytest -- tests/test_api.py::TestAPI::test_get_organizations

# Combine multiple options
./bouy test --pytest -- -vsx -k test_name
```

### Test Output Formats

```bash
# Normal output (default)
./bouy test --pytest

# Programmatic mode (structured output)
./bouy --programmatic test --pytest

# JSON output (for CI/CD)
./bouy --json test --pytest

# Quiet mode (minimal output)
./bouy --quiet test --pytest

# No color (for log files)
./bouy --no-color test --pytest
```

### Coverage Reports

When running pytest, coverage reports are automatically generated:
- `htmlcov/index.html` - HTML coverage report
- `coverage.xml` - XML report for CI
- `coverage.json` - JSON report for automation

```bash
# Run tests with coverage
./bouy test --pytest

# Run with coverage threshold check
./bouy test --coverage

# View coverage report
open htmlcov/index.html
```

### Type Checking Specific Files

```bash
# Check specific file
./bouy test --mypy app/api/

# Check multiple paths
./bouy test --mypy app/api/ app/llm/
```

### Code Formatting

```bash
# Check formatting
./bouy test --black

# Check specific paths
./bouy test --black app/api/

# Note: Black will update files when run via test
```

### Security Scanning

```bash
# Scan all code
./bouy test --bandit

# Scan with specific severity
./bouy test --bandit -- -ll  # Low severity and above
```

## Programmatic Mode

Programmatic mode provides structured output suitable for automation and CI/CD pipelines.

### Features
- Structured log output to stderr
- Results/data to stdout
- No interactive prompts
- No TTY allocation
- Consistent formatting

### Usage Examples

```bash
# Start services with structured logging
./bouy --programmatic up

# Get service status as JSON
./bouy --json ps

# Run tests with minimal output
./bouy --programmatic --quiet test

# Execute commands without TTY
./bouy --programmatic exec app python --version
```

### Output Format

In programmatic mode, all log output follows this format:
```
[2024-01-25T10:30:45Z] [info] Starting services...
[2024-01-25T10:30:46Z] [success] Services started successfully
```

JSON mode outputs valid JSON to stdout:
```json
{
  "timestamp": "2024-01-25T10:30:45Z",
  "level": "info",
  "message": "Starting services..."
}
```

## Common Workflows

### Starting Fresh Development Environment

```bash
# Clean everything and start fresh
./bouy clean
./bouy up

# Start with populated database from HAARRRvest
./bouy clean
./bouy up --with-init
```

### Daily Development Workflow

```bash
# Start services
./bouy up

# Check everything is running
./bouy ps

# Run tests before making changes
./bouy test --pytest

# Make changes, then run specific tests
./bouy test --pytest tests/test_my_feature.py

# Run all checks before committing
./bouy test

# Check logs if something fails
./bouy logs app
```

### Debugging Failed Services

```bash
# Check service status
./bouy ps

# View logs for failed service
./bouy logs app

# Get shell access to debug
./bouy shell app

# Check database connectivity
./bouy exec app python -c "from app.database import engine; print('DB OK')"

# Restart a specific service
./bouy down
./bouy up app
```

### Running Scrapers

```bash
# List available scrapers
./bouy scraper --list

# Test a scraper without processing
./bouy scraper-test food_bank_for_nyc

# Run the scraper
./bouy scraper food_bank_for_nyc

# Monitor scraper logs
./bouy logs scraper
```

### Working with LLM Providers

```bash
# Setup Claude authentication
./bouy claude-auth

# Check authentication status
./bouy claude-auth status

# Test the connection
./bouy claude-auth test

# Monitor worker logs
./bouy logs worker
```

## CI/CD Integration

### GitHub Actions

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run all tests
        run: ./bouy --programmatic --quiet test

      - name: Check types
        run: ./bouy --programmatic --quiet test --mypy

      - name: Run security scan
        run: ./bouy --programmatic --quiet test --bandit
```

### GitLab CI

```yaml
stages:
  - test
  - deploy

test:
  stage: test
  script:
    - ./bouy --programmatic --quiet test
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml

deploy:
  stage: deploy
  script:
    - ./bouy --programmatic up --prod
  only:
    - main
```

### Jenkins Pipeline

```groovy
pipeline {
    agent any

    stages {
        stage('Test') {
            steps {
                sh './bouy --programmatic --quiet test'
            }
        }

        stage('Type Check') {
            steps {
                sh './bouy --programmatic --quiet test --mypy'
            }
        }

        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh './bouy --programmatic up --prod'
            }
        }
    }

    post {
        always {
            sh './bouy --programmatic down'
        }
    }
}
```

### CircleCI

```yaml
version: 2.1

jobs:
  test:
    docker:
      - image: cimg/base:stable
    steps:
      - checkout
      - setup_remote_docker
      - run:
          name: Run tests
          command: ./bouy --programmatic --quiet test
      - store_test_results:
          path: test-results
      - store_artifacts:
          path: htmlcov

workflows:
  main:
    jobs:
      - test
```

## Troubleshooting

### Common Issues

#### Services won't start
```bash
# Check if ports are in use
./bouy ps

# View detailed logs
./bouy logs

# Check Docker daemon
docker version

# Clean and restart
./bouy clean
./bouy up
```

#### Database connection errors
```bash
# Check database is running
./bouy ps | grep db

# View database logs
./bouy logs db

# Test connection
./bouy exec db pg_isready

# Check schema initialization
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT 1 FROM record_version LIMIT 1;"
```

#### Redis connection errors
```bash
# Check Redis is running
./bouy ps | grep cache

# Test Redis connection
./bouy exec cache redis-cli ping

# View Redis logs
./bouy logs cache
```

#### Test failures
```bash
# Run with verbose output
./bouy test --pytest -- -v

# Run specific failing test
./bouy test --pytest -- tests/test_file.py::test_function -vvs

# Debug with pdb
./bouy test --pytest -- --pdb
```

#### Authentication issues
```bash
# Check Claude auth
./bouy claude-auth status

# Re-authenticate
./bouy claude-auth

# Check environment variables
./bouy exec worker env | grep -E "(ANTHROPIC|OPENROUTER|LLM)"
```

### Debug Mode

For maximum debugging information:
```bash
# Verbose mode with no color
./bouy --verbose --no-color up

# Check what compose files are being used
COMPOSE_FILES="-f docker-compose.yml -f .docker/compose/docker-compose.dev.yml"
docker compose $COMPOSE_FILES config
```

### Health Checks

Bouy automatically performs health checks:
- Database readiness (pg_isready)
- Redis connectivity (redis-cli ping)
- Directory permissions
- Git configuration
- Content store initialization

To manually run health checks:
```bash
# Database
./bouy exec db pg_isready

# Redis
./bouy exec cache redis-cli ping

# Content store
./bouy content-store status
```

## Environment Variables

Bouy respects these environment variables:
- `COMPOSE_PROJECT_NAME` - Override project name (default: pantry-pirate-radio)
- `POSTGRES_PASSWORD` - Database password (default: pirate)
- `BOUY_TEST_MODE` - Enable test mode
- `BOUY_TEST_COMPOSE_CMD` - Override compose command in test mode

## Version History

- **v1.0.0** - Initial release with comprehensive Docker fleet management

## Bouy-API: Advanced Programmatic Interface

For advanced automation and CI/CD integration, `bouy-api` provides additional features:

### Features
- Enhanced JSON output for all commands
- Service health checking with `--wait-healthy`
- Command timeouts with `--timeout`
- Dry-run mode with `--dry-run`
- Structured exit codes for error handling

### Usage
```bash
# Wait for services to be healthy
./bouy-api --json --wait-healthy up app worker

# Execute with timeout
./bouy-api --timeout 300 test pytest

# Dry run to see what would execute
./bouy-api --dry-run up --prod

# Check service health
./bouy-api health app

# Follow logs after starting
./bouy-api --follow-logs up
```

### Exit Codes
- `0` - Success
- `1` - General error
- `2` - Service not running
- `3` - Service not healthy
- `4` - Timeout
- `5` - Command not found

### JSON Output
```bash
# Service status
./bouy-api --json status app

# Test results
./bouy-api --json test pytest

# All services
./bouy-api --json ps
```

## Contributing

When adding new features to bouy:
1. Update this documentation
2. Add tests in `tests/test_bouy_*.py`
3. Update mock_compose.sh for new Docker commands
4. Ensure programmatic mode support
5. Consider if the feature should also be in bouy-api

---

*Navigate with confidence using bouy - your Docker fleet management companion!* ⚓