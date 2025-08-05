# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Command Reference

**IMPORTANT: All commands use bouy - no local dependencies except Docker required!**

```bash
# Initial Setup Commands
./bouy setup                 # Interactive setup wizard (creates .env file)
./bouy --help                # Show help with all commands
./bouy --version             # Show bouy version

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
./bouy scraper --all          # Run all scrapers
./bouy scraper NAME           # Run specific scraper
./bouy scraper scouting-party # Run all scrapers in parallel
./bouy scraper-test NAME      # Test scraper (dry run)

# Service Management
./bouy build                # Build all services
./bouy build app            # Build specific service
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
./bouy up                   # Start services
./bouy test                 # Verify everything works
```

The setup wizard will:
- Create `.env` file from template with interactive prompts
- Configure database passwords
- Set up LLM provider selection (OpenAI vs Claude)
- Handle Claude authentication options (API key vs CLI)
- Configure HAARRRvest repository tokens
- Create backups of existing `.env` files

## Development Commands

### IMPORTANT: Docker-Only Development

**All development commands must use bouy** - no local Python dependencies are required except Docker.

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

# View coverage report in browser
open htmlcov/index.html
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
./bouy up --with-init       # With database initialization

# Start specific services
./bouy up app worker        # Start only app and worker

# Service management
./bouy down                 # Stop all services
./bouy ps                   # List running services
./bouy logs app             # View service logs
./bouy logs -f worker       # Follow worker logs
./bouy shell app            # Open shell in container
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

[rest of the existing file content remains the same...]

## TDD Memories

### Testing Specific Commands
- Use `./bouy exec app poetry run pytest` for running single test files or single tests.