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
./bouy scraper --list       # List all scrapers
./bouy scraper --all        # Run all scrapers
./bouy scraper NAME         # Run specific scraper
./bouy scraper-test NAME    # Test scraper (dry run)

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

### Environment Modes
```bash
# Development mode (default)
./bouy up
./bouy up --dev

# Production mode
./bouy up --prod

# Test mode
./bouy up --test

# With database initialization from HAARRRvest
./bouy up --with-init
./bouy up --dev --with-init
./bouy up --prod --with-init
```

### Managing Container Images
```bash
# Pull all latest container images from GitHub Container Registry
./bouy pull

# Pull specific version tags (e.g., from a release)
./bouy pull v1.2.3

# Pull images with a specific git SHA
./bouy pull abc1234

# Troubleshooting authentication issues
docker login ghcr.io  # Login to GitHub Container Registry first
./bouy pull          # Then retry pulling

# Note: Images are automatically tagged for local docker-compose use
# Example: ghcr.io/.../app-latest → for-the-greater-good-pantry-pirate-radio-app:latest
```

### Running Scrapers
```bash
# List available scrapers
./bouy scraper --list

# Run specific scraper
./bouy scraper nyc_efap_programs

# Run all scrapers
./bouy scraper --all

# Programmatic mode for automation
./bouy --programmatic scraper --list
./bouy --programmatic --quiet scraper nyc_efap_programs
```

### Testing Scrapers
```bash
# Test scrapers without processing (dry run)
./bouy scraper-test --all
./bouy scraper-test nyc_efap_programs
```

### Data Export and Management
```bash
# Export database to SQLite for Datasette
./bouy datasette                    # Run immediate export
./bouy datasette export             # Same as above
./bouy datasette schedule           # Start periodic export scheduler
./bouy datasette status             # Check export status

# Replay recorded JSON files to recreate database records
./bouy replay                       # Show help
./bouy replay --file path/to/file.json          # Replay single file
./bouy replay --directory path/to/dir            # Replay directory
./bouy replay --use-default-output-dir           # Use outputs directory
./bouy replay --use-default-output-dir --dry-run # Preview without executing

# With programmatic output
./bouy --programmatic replay --use-default-output-dir
./bouy --quiet replay --file output.json
```

### Service Management Commands
```bash
# Reconciler (processes LLM job results)
./bouy reconciler                   # Process jobs from queue

# Recorder (saves job results to JSON files)
./bouy recorder                     # Save results to outputs directory

# Content Store (manages deduplication)
./bouy content-store status         # Check content store status
./bouy content-store report         # Generate detailed report
./bouy content-store duplicates     # Find duplicate content
./bouy content-store efficiency     # Analyze storage efficiency

# HAARRRvest Publisher (pushes data to repository)
./bouy haarrrvest                   # Manually trigger publish
./bouy haarrrvest run              # Same as above
./bouy haarrrvest logs             # Follow publisher logs
./bouy haarrrvest status           # Check publisher status

# Claude Authentication (for LLM workers)
./bouy claude-auth                  # Interactive authentication
./bouy claude-auth setup           # Setup authentication
./bouy claude-auth status          # Check auth status
./bouy claude-auth test            # Test connection
./bouy claude-auth config          # Show configuration
```

### CI Checks
```bash
# Run all CI checks
./bouy test

# For GitHub Actions or other CI systems
./bouy --programmatic --quiet test

# With specific output formats
./bouy --json test               # JSON output
./bouy --programmatic test       # Structured logging
./bouy --quiet test              # Minimal output
./bouy --no-color test           # Plain text
```

## Architecture Overview

Pantry Pirate Radio is a distributed microservices system that aggregates food security data from multiple sources, processes it with AI for HSDS compliance, and provides a unified API.

### Data Flow Architecture
```
Scrapers → Redis Queue → LLM Workers → Reconciler → PostgreSQL → API
    ↓                                       ↓
Recorder → JSON Files → HAARRRvest Publisher → HAARRRvest Repository
```

### Key Architectural Patterns

#### 1. **Job-Based Processing Pipeline**
- All data flows through Redis-based job queues
- Jobs have metadata (scraper_id, source_type, priority) and data payloads
- Workers process jobs asynchronously with retry logic
- Dead letter queue captures failed jobs for analysis

#### 2. **HSDS Schema Alignment**
- AI-powered normalization using LLM providers (OpenAI/Claude)
- Confidence scoring with weighted field validation:
  - Top-level fields: 0.15-0.25 deduction for missing
  - Entity fields: 0.10-0.20 deduction for missing
  - Required fields enforced by entity type
- Structured output with hallucination detection
- Field coherence validation ensures data quality

#### 3. **Geographic Intelligence**
- Continental US grid system (25°N-49°N, -125°W to -67°W)
- PostGIS spatial indexing for fast queries
- Smart grid generation for large area coverage (80-mile diagonal max)
- Bounding box and radius search capabilities

#### 4. **Content-Addressable Storage**
- SHA-256 based deduplication system in `app/content_store/`
- Prevents duplicate LLM processing of identical content
- SQLite index for fast lookups with status tracking
- Stores raw and processed data for traceability
- Configurable via CONTENT_STORE_PATH environment variable

#### 5. **Version Control System**
- Every record maintains complete version history
- Reconciler tracks changes across sources
- Enables rollback and audit capabilities
- Prevents data loss during updates

### Service Responsibilities

#### **Scrapers** (`app/scraper/`)
- Extract data from 12+ food security sources
- Inherit from `ScraperJob` base class
- Generate geographic grids for API-based sources
- Submit jobs to Redis queue with proper metadata
- Handle rate limiting and error recovery

#### **LLM Workers** (`app/llm/`)
- Process jobs from Redis queue
- Apply HSDS schema alignment using AI
- Validate with confidence scoring (min 0.85 required)
- Handle provider-specific authentication:
  - OpenAI: API key authentication
  - Claude: CLI or API key authentication with shared state

#### **Reconciler** (`app/reconciler/`)
- Create canonical records from multiple sources
- Handle entity deduplication using location matching
- Maintain version history with `record_version` table
- Process in order: organizations → locations → services

#### **Recorder** (`app/recorder/`)
- Save all job results as JSON files
- Organize in `outputs/daily/YYYY-MM-DD/` structure
- Maintain `latest/` symlink
- Create daily summary files

#### **API Server** (`app/api/`)
- Provide read-only HSDS-compliant endpoints
- Geographic search with tile-based caching
- Cursor-based pagination
- OpenAPI documentation at `/docs`

#### **HAARRRvest Publisher** (`app/haarrrvest_publisher/`)
- Monitor recorder outputs every 5 minutes
- Create date-based branches (e.g., `data-update-2025-01-25`)
- Sync files to HAARRRvest repository
- Generate SQLite database for Datasette
- Export location data for web maps
- Merge branches to main with proper commit history

### Database Schema
- PostgreSQL with PostGIS extension
- HSDS v3.1.1 compliant schema
- Key tables: organization, service, location, service_at_location
- Spatial indexes on location.coordinates
- Version tracking in record_version table

### Environment Configuration
Key environment variables (see `.env.example`):
- `DATABASE_URL`: PostgreSQL connection
- `REDIS_URL`: Redis connection
- `LLM_PROVIDER`: Choose between 'openai' or 'claude'
- `CONTENT_STORE_PATH`: Content-addressable storage location
- `DATA_REPO_URL`: HAARRRvest repository URL
- `DATA_REPO_TOKEN`: GitHub personal access token
- `REDIS_TTL_SECONDS`: Job result TTL (default: 30 days)

### LLM Provider Details

#### OpenAI Provider
- Uses OpenRouter API for model access
- Requires `OPENROUTER_API_KEY` environment variable
- Supports structured output with JSON schema
- Models: GPT-4o, Claude via OpenRouter, etc.

#### Claude Provider
- Uses Claude Code SDK via subprocess
- Authentication options:
  1. API key via `ANTHROPIC_API_KEY`
  2. CLI authentication (recommended for Claude Max)
- Shared authentication across scaled workers
- Intelligent retry on quota/auth errors:
  - Auth errors: 5-minute retry for 1 hour
  - Quota errors: Exponential backoff (1h → 4h max)

#### Claude Authentication Commands
```bash
# Authenticate Claude (interactive)
./bouy claude-auth

# Check authentication status
./bouy claude-auth status

# Other authentication commands
./bouy claude-auth setup         # Setup authentication
./bouy claude-auth test          # Test connection
./bouy claude-auth config        # Show configuration

# Check health endpoint
curl http://localhost:8080/health
```

### HSDS Validation Details

#### Required Fields by Entity
- **Organization**: name, description, services, phones, organization_identifiers, contacts, metadata
- **Service**: name, description, status, phones, schedules
- **Location**: name, location_type, addresses, phones, accessibility, contacts, schedules, languages, metadata
- **Phone**: number, type, languages

#### Confidence Scoring
- Base score: 1.0
- Deductions for missing fields (0.05-0.25 per field)
- Higher deductions for known/required fields
- Minimum confidence for acceptance: 0.85
- Retry threshold: 0.5

#### Field Validation Types
- Format validation (URI, email, dates, times)
- Type constraints (coordinates, age ranges, financial amounts)
- Enum validation (service status, location types, phone types)
- Relationship validation (services must link to organizations)

### HAARRRvest Publisher Commands
```bash
# Start the publisher service
./bouy up haarrrvest-publisher

# Manually trigger publishing
./bouy haarrrvest                # Run publisher immediately
./bouy haarrrvest run           # Same as above

# Monitor publisher
./bouy haarrrvest logs          # Follow publisher logs
./bouy haarrrvest status        # Check publisher status

# View logs
./bouy logs haarrrvest-publisher

# Check service status
./bouy ps
```

## TDD Memories

### TDD Philosophy and Best Practices
- **TDD Rule**: Write a failing test before any production code - if you're tempted to code first, you're about to build the wrong thing. Tests aren't validation, they're specification: they force you to define exactly what success looks like before you get seduced by clever implementations that solve the wrong problem. Every line of untested code is a liability waiting to break in production, and every test written after the fact is just wishful thinking disguised as quality assurance. The red-green-refactor cycle isn't just methodology, it's discipline - it keeps you honest about what you're actually building versus what you think you're building. When you write tests first, you're not just preventing bugs, you're preventing entire categories of design mistakes that would otherwise plague your codebase for months.
- TDD Rule: Write a failing test before any production code - if you're tempted to code first, you're about to build the wrong thing.

### Commit Philosophy
- **Atomic Commits Rule**: Each commit must represent one complete, logical change that could stand alone - if you can't describe your commit in a single sentence without using "and", you're committing too much. Atomic commits aren't just good practice, they're your future self's lifeline: they make git bisect actually useful, code reviews focused and meaningful, and rollbacks surgical instead of catastrophic. When you bundle multiple changes into one commit, you're not saving time, you're creating archaeological puzzles for whoever has to debug your code later. The discipline of atomic commits forces you to think in discrete problem-solving steps rather than chaotic coding sessions, and each commit becomes a breadcrumb trail showing exactly how you solved each piece of the puzzle. Mixed commits are technical debt in disguise - they look efficient in the moment but cost exponentially more when you need to understand, revert, or cherry-pick changes months later.
- **Commit-As-You-Go TDD Rule**: Commit at every stage of the red-green-refactor cycle - failing test, passing implementation, and clean refactor each deserve their own atomic commit because your git history should tell the story of how you solved the problem, not just what the final solution looks like. Waiting until "everything is done" to commit is like writing a book and only saving it at the end - you're one power outage away from losing hours of thoughtful work. Each TDD phase commit creates a safety net: if your refactoring goes sideways, you can instantly return to working code; if your implementation gets too complex, you can restart from the clean failing test. The three-commit TDD rhythm creates a narrative that future developers (including yourself) can follow: "here's what they wanted to achieve, here's how they made it work, here's how they made it clean." When you commit continuously through TDD, you're not just saving your work, you're creating a masterclass in problem-solving that turns your git log into executable documentation of your thought process.

### Docker Compose Naming
- It's "docker compose" (space), not "docker-compose" (hyphen)

## Pre-commit Hooks

All pre-commit hooks run in Docker containers via bouy. No local Python installation required!

```bash
# Install pre-commit hooks (one-time setup)
pre-commit install

# Run all hooks manually
pre-commit run --all-files

# Skip hooks for a commit (use sparingly!)
git commit --no-verify -m "Emergency fix"
```

### Hook Configuration
The `.pre-commit-config.yaml` is configured to run all Python tools via `bouy`:
- **black-docker**: Code formatting via `./bouy --programmatic --quiet test --black`
- **ruff-docker**: Linting via `./bouy --programmatic --quiet test --ruff`
- **mypy-docker**: Type checking via `./bouy --programmatic --quiet test --mypy`
- **pytest-docker**: Test suite via `./bouy --programmatic --quiet test --pytest`

All hooks use bouy's programmatic mode for consistent Docker execution.

## CLI and Development Tools

### CLI Tools
- **gh is available. it's much preferable to trying to interact with github.com**

### Advanced Automation: bouy-api

For CI/CD and advanced automation, use `bouy-api` which provides:
- Enhanced JSON output for all commands
- Service health checking with `--wait-healthy`
- Command timeouts with `--timeout`
- Dry-run mode with `--dry-run`
- Structured exit codes (0-5) for error handling

```bash
# Wait for services to be healthy before continuing
./bouy-api --json --wait-healthy up app worker

# Run tests with timeout and JSON output
./bouy-api --json --timeout 300 test pytest

# Check service health
./bouy-api health app

# Dry run to preview commands
./bouy-api --dry-run up --prod
```