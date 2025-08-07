# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Command Reference

**IMPORTANT: All commands use bouy - no local dependencies except Docker required!**

```bash
# Initial Setup Commands
./bouy setup                 # Interactive setup wizard (creates .env file)
./bouy --help                # Show help with all commands
./bouy help                  # Same as --help
./bouy --version             # Show bouy version (v1.0.0)
./bouy version               # Same as --version

# Essential Commands
./bouy up                    # Start all services
./bouy down                  # Stop all services
./bouy test                  # Run all tests and checks
./bouy logs app              # View service logs
./bouy shell app             # Open shell in container
./bouy ps                    # List running services
./bouy clean                 # Stop and remove volumes

# Testing Commands
./bouy test --pytest         # Run tests only
./bouy test --mypy          # Type checking only
./bouy test --black         # Format checking only
./bouy test --ruff          # Linting only
./bouy test --bandit        # Security scan only
./bouy test --coverage       # Tests with coverage check
./bouy test --vulture        # Dead code detection
./bouy test --safety         # Dependency vulnerability scan
./bouy test --pip-audit      # Pip audit for vulnerabilities
./bouy test --xenon          # Code complexity analysis

# Scraper Commands
./bouy scraper --list         # List all scrapers
./bouy scraper --all          # Run all scrapers sequentially
./bouy scraper NAME           # Run specific scraper
./bouy scraper scouting-party # Run all scrapers in parallel (default: 5 concurrent)
./bouy scraper scouting-party 10 # Run with 10 concurrent scrapers
./bouy scraper-test NAME      # Test scraper (dry run)
./bouy scraper-test --all     # Test all scrapers (dry run)

# Service Management
./bouy build                # Build all services
./bouy build app            # Build specific service
./bouy build --prod worker  # Build for production
./bouy exec app CMD         # Execute command in container
./bouy pull                 # Pull all latest container images
./bouy pull v1.2.3          # Pull specific version tags

# Global Flags (work with all commands)
./bouy --help               # Show help
./bouy --version            # Show version
./bouy --programmatic CMD   # Structured output
./bouy --json CMD           # JSON output (implies --programmatic)
./bouy --quiet CMD          # Minimal output
./bouy --verbose CMD        # Debug output
./bouy --no-color CMD       # No color codes
```

## Initial Setup

### NEW USERS: Interactive Setup Wizard

**For new installations, always start with the setup wizard:**

```bash
./bouy setup                # Interactive setup wizard - creates .env configuration
./bouy up                   # Start services (development mode by default)
./bouy test                 # Verify everything works (runs all CI checks)
```

The setup wizard will:
- Create `.env` file from template with interactive prompts
- Configure database passwords (default: 'pirate')
- Set up LLM provider selection (OpenAI via OpenRouter vs Claude/Anthropic)
- Handle Claude authentication options (API key vs Claude Code CLI)
- Configure HAARRRvest repository tokens (or 'skip' for read-only mode)
- Create timestamped backups of existing `.env` files

## Development Commands

### IMPORTANT: Docker-Only Development

**All development commands must use bouy** - no local Python dependencies are required except Docker.

### Using @agent-test-suite-monitor

**CRITICAL: Use @agent-test-suite-monitor for ALL testing needs. This agent is your dedicated test execution and monitoring system.**

#### When to Use @agent-test-suite-monitor

**Always use @agent-test-suite-monitor in these scenarios:**

1. **After implementing new features or fixing bugs** - to verify your changes work correctly
2. **When tests are failing unexpectedly** - to get detailed failure analysis and diagnostics
3. **Before committing changes** - to ensure all tests pass and code quality standards are met
4. **After making significant code changes** - to verify nothing has been broken
5. **When investigating CI/CD failures** - to reproduce and debug test failures locally
6. **For regular test health checks** - to monitor test suite performance and coverage
7. **When you need to run specific test categories** - the agent runs tests individually for better control

**Examples of using @agent-test-suite-monitor:**
```bash
# After implementing a new feature
@agent-test-suite-monitor "Run full test suite after implementing new user API endpoint"

# When tests fail unexpectedly
@agent-test-suite-monitor "Debug failing authentication tests and provide detailed analysis"

# Before creating a pull request
@agent-test-suite-monitor "Run all test categories individually before PR"

# After refactoring code
@agent-test-suite-monitor "Verify all tests pass after refactoring database models"

# For specific test investigation
@agent-test-suite-monitor "Run only pytest tests for the API module"

# When monitoring test performance
@agent-test-suite-monitor "Check test execution times and identify slow tests"
```

#### What @agent-test-suite-monitor Does

The test-suite-monitor agent:
- **Runs tests individually by category** (pytest, black, ruff, mypy, bandit) for better control
- **Analyzes test failures** with detailed error reporting and likely causes
- **Tracks changes between test runs** to identify regressions
- **Monitors test performance** and execution times
- **Provides coverage analysis** to identify untested code
- **Suggests specific debugging commands** when tests fail
- **Uses proper output management** (--programmatic, --quiet, --json) for clean results

#### Important Notes

- The agent will NEVER use `./bouy test` without specifying a test type
- It runs each test category separately for clearer results and better failure isolation
- It provides structured failure reports with actionable recommendations
- It tracks test results within the session to identify patterns
- It never modifies code - only reports and analyzes test results

### Test-Driven Development (TDD) Workflow

This project follows Test-Driven Development principles. Always write tests before implementing features:

1. **Red Phase**: Write a failing test that defines the desired behavior
2. **Green Phase**: Write the minimum code necessary to make the test pass
3. **Refactor Phase**: Improve the code while keeping tests passing

#### TDD Process for New Features
```bash
# 1. Create test file first
touch tests/test_new_feature.py

# 2. Write failing test and run with bouy
./bouy test --pytest  # Should fail

# 3. Implement minimal code to pass
# ... write implementation ...

# 4. Run test again
./bouy test --pytest  # Should pass

# 5. Refactor and ensure tests still pass
./bouy test --pytest

# 6. Run full test suite before committing
./bouy test  # Runs all CI checks
```

## Testing with Bouy

### Running All Tests
```bash
./bouy test                  # Run all CI checks (pytest, mypy, black, ruff, bandit)
```

### Running Specific Test Types
```bash
./bouy test --pytest         # Run pytest with coverage
./bouy test --mypy           # Type checking only
./bouy test --black          # Code formatting only
./bouy test --ruff           # Linting only
./bouy test --bandit         # Security scan only
./bouy test --coverage       # Pytest with coverage threshold check
```

### Running Specific Test Files
```bash
# Test a specific file
./bouy test --pytest tests/test_api.py

# Test a directory
./bouy test --pytest tests/test_scraper/

# Multiple files
./bouy test --pytest tests/test_api.py tests/test_reconciler.py
```

### Passing Additional Arguments to Tests

Use `--` to pass arguments to the underlying test command:

```bash
# Verbose output
./bouy test --pytest -- -v

# Run tests matching pattern
./bouy test --pytest -- -k test_name
./bouy test --pytest -- -k "test_api or test_reconciler"

# Stop on first failure
./bouy test --pytest -- -x

# Drop to debugger on failure
./bouy test --pytest -- --pdb

# Show local variables
./bouy test --pytest -- -l

# Run specific test function
./bouy test --pytest -- tests/test_api.py::TestAPI::test_get_organizations

# Combine options
./bouy test --pytest -- -vsx -k test_name
```

### Test Output Formats
```bash
# Normal output (default)
./bouy test --pytest

# Programmatic mode (structured output for CI)
./bouy --programmatic test --pytest

# JSON output
./bouy --json test --pytest

# Quiet mode (minimal output)
./bouy --quiet test --pytest

# No color (for log files)
./bouy --no-color test --pytest

# Combine modes
./bouy --programmatic --quiet test
```

### Coverage Analysis
```bash
# Run tests with coverage check
./bouy test --coverage

# Coverage reports are automatically generated:
# - htmlcov/index.html (HTML report)
# - coverage.xml (XML report for CI)
# - coverage.json (JSON report for automation)

# View coverage report in browser (macOS/Linux)
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Type Checking Specific Files
```bash
# Check specific paths
./bouy test --mypy app/api/
./bouy test --mypy app/api/ app/llm/
```

### Code Formatting
```bash
# Check formatting (updates files automatically)
./bouy test --black

# Check specific paths
./bouy test --black app/api/
```

### Security Scanning
```bash
# Run security scan
./bouy test --bandit

# With custom severity
./bouy test --bandit -- -ll  # Low severity and above
```

### CI/CD Testing Examples
```bash
# GitHub Actions / CI pipelines
./bouy --programmatic --quiet test              # All checks, minimal output
./bouy --programmatic --quiet test --pytest     # Just tests
./bouy --programmatic --quiet test --mypy       # Just type checking
./bouy --json test --pytest                     # JSON test results

# Combine with error checking
./bouy --programmatic --quiet test || exit 1
```

### Development Setup
```bash
# Start all services (no local dependencies needed)
./bouy up                    # Development mode (default)
./bouy up --prod            # Production mode
./bouy up --test            # Test mode
./bouy up --with-init       # With database initialization
./bouy up --dev --with-init # Combine options

# Start specific services
./bouy up app worker        # Start only app and worker

# Service management
./bouy down                 # Stop all services
./bouy ps                   # List running services
./bouy logs                 # View all logs (follows by default)
./bouy logs app             # View service logs
./bouy logs -f worker       # Follow worker logs (explicit follow)
./bouy shell app            # Open shell in container (bash or sh)
./bouy exec app python --version  # Execute command
./bouy clean                # Stop and remove volumes

# Build services
./bouy build                # Build all services
./bouy build app            # Build specific service
./bouy build --prod worker  # Build for production

# Programmatic mode for automation
./bouy --json ps            # Get service status as JSON
./bouy --quiet up           # Start with minimal output
./bouy --programmatic exec app python -c "print('test')"
```

## Testing Guidelines

### IMPORTANT: Always Use ./bouy test Commands
- **ALWAYS use `./bouy test --pytest` for running tests** - do NOT use `./bouy exec app poetry run pytest`
- For specific test files: `./bouy test --pytest tests/test_api.py`
- For specific test functions: `./bouy test --pytest -- tests/test_api.py::TestAPI::test_function`
- The `./bouy test` command properly handles test environments, coverage, and dependencies

## Additional Commands

### HAARRRvest Publisher
```bash
./bouy haarrrvest             # Manually trigger publishing run
./bouy haarrrvest run         # Same as above
./bouy haarrrvest logs        # Follow publisher logs
./bouy haarrrvest status      # Check publisher service status
```

### Content Store Management
```bash
./bouy content-store status      # Show content store status
./bouy content-store report      # Generate detailed report
./bouy content-store duplicates  # Find duplicate content
./bouy content-store efficiency  # Analyze storage efficiency
```

### Data Recording and Replay
```bash
./bouy recorder                          # Save job results to JSON
./bouy recorder --output-dir /custom/path # Custom output directory
./bouy replay --file FILE                # Replay single JSON file
./bouy replay --directory DIR            # Replay all files in directory
./bouy replay --use-default-output-dir   # Use default outputs directory
./bouy replay --dry-run                  # Preview without executing
```

### Claude Authentication
```bash
./bouy claude-auth           # Interactive Claude authentication
./bouy claude-auth setup     # Setup Claude authentication
./bouy claude-auth status    # Check authentication status
./bouy claude-auth test      # Test Claude connection
./bouy claude-auth config    # Show Claude configuration
```

### Data Reconciliation
```bash
./bouy reconciler            # Run reconciler
./bouy reconciler --force    # Force processing
```

### Data Viewing and Endpoints
When services are running, the following endpoints are available:
- **API**: http://localhost:8000 (REST API)
- **API Docs**: http://localhost:8000/docs (Interactive Swagger UI)
- **Datasette Viewer**: http://localhost:8001 (in production mode only)
- **RQ Dashboard**: http://localhost:9181 (job queue monitoring)

Datasette provides:
- SQL interface to explore published HAARRRvest data
- Read-only access to the SQLite database
- Data export in various formats (CSV, JSON)

## Memories

### Test Command Notes
- Do not use 2>&1 in bouy test commands, it gets interpreted incorrectly
- Always use `./bouy test --pytest` for running tests, not `./bouy exec app poetry run pytest`
- Test commands automatically handle test environments, coverage, and dependencies

### Important Instructions
- NEVER create files unless they're absolutely necessary for achieving your goal
- ALWAYS prefer editing an existing file to creating a new one
- NEVER proactively create documentation files (*.md) or README files unless explicitly requested
- Do what has been asked; nothing more, nothing less