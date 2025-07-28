# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Command Reference

**IMPORTANT: All commands use bouy - no local dependencies except Docker required!**

```bash
# Essential Commands
./bouy up                    # Start all services
./bouy down                  # Stop all services
./bouy test                  # Run all tests and checks
./bouy logs app              # View service logs
./bouy shell app             # Open shell in container

# Testing Commands
./bouy test --pytest         # Run tests only
./bouy test --mypy          # Type checking only
./bouy test --black         # Format checking only
./bouy test --ruff          # Linting only
./bouy test --bandit        # Security scan only

# Scraper Commands
./bouy scraper --list       # List all scrapers
./bouy scraper --all        # Run all scrapers
./bouy scraper NAME         # Run specific scraper

# Programmatic Mode (for CI/automation)
./bouy --programmatic test  # Structured output
./bouy --json ps            # JSON output
./bouy --quiet up           # Minimal output
./bouy --no-color logs app  # No color codes
```

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

# 2. Write failing test and run with Docker
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

### Running Tests with Docker
```bash
# Run all tests with coverage (runs all CI checks)
./bouy test

# Run only pytest with coverage
./bouy test --pytest

# Run specific test types
./bouy test --mypy      # Type checking only
./bouy test --black     # Code formatting only
./bouy test --ruff      # Linting only
./bouy test --bandit    # Security scan only
./bouy test --coverage  # Pytest with coverage check

# Programmatic mode for automation
./bouy --programmatic test --pytest          # Structured output
./bouy --json ps                             # JSON output
./bouy --quiet test --mypy                   # Minimal output
./bouy --programmatic --quiet test --black   # Combined flags
```

### Coverage Analysis
```bash
# Run tests with coverage check
./bouy test --coverage

# Coverage reports are generated in the container and available at:
# - htmlcov/index.html (HTML report)
# - coverage.xml (XML report for CI)
# - coverage.json (JSON report for automation)

# View coverage report in browser
open htmlcov/index.html
```

### Code Quality Checks
```bash
# Run all quality checks
./bouy test

# Run individual checks
./bouy test --mypy      # Type checking
./bouy test --black     # Code formatting
./bouy test --ruff      # Linting
./bouy test --bandit    # Security scan

# For programmatic use in CI/CD
./bouy --programmatic --quiet test --mypy
./bouy --programmatic --quiet test --black
./bouy --programmatic --quiet test --ruff
./bouy --programmatic --quiet test --bandit
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
./bouy shell app            # Open shell in container
./bouy exec app python --version  # Execute command
./bouy clean                # Stop and remove volumes

# Programmatic mode for automation
./bouy --json ps            # Get service status as JSON
./bouy --quiet up           # Start with minimal output
```

### Docker Build Commands
```bash
# Build all services
./bouy build

# Build specific service
./bouy build app
./bouy build worker

# The test image is automatically built when running tests
./bouy test  # Builds test image if needed
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

### CI Checks
```bash
# Run all CI checks using Docker
./bouy test

# Or use the Docker-based CI script directly
./scripts/run-ci-checks-bouy

# For GitHub Actions or other CI systems
./bouy --programmatic --quiet test
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
curl http://localhost:8080/health

# Alternative manual commands
./bouy exec worker python -m app.claude_auth_manager setup
./bouy exec worker python -m app.claude_auth_manager status
./bouy exec worker python -m app.claude_auth_manager test
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

# View logs
./bouy logs haarrrvest-publisher

# Restart to trigger immediate processing
./bouy exec haarrrvest-publisher supervisorctl restart all

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

All pre-commit hooks run in Docker containers. No local Python installation required!

```bash
# Install pre-commit hooks (one-time setup)
pre-commit install

# Run all hooks manually
pre-commit run --all-files

# Run specific hook
pre-commit run black-docker --all-files
pre-commit run mypy-docker --all-files

# Skip hooks for a commit (use sparingly!)
git commit --no-verify -m "Emergency fix"
```

### Hook Configuration
The `.pre-commit-config.yaml` is configured to run all Python tools via `bouy`:
- **black-docker**: Code formatting
- **ruff-docker**: Linting
- **mypy-docker**: Type checking
- **pytest-docker**: Test suite

All hooks use `./bouy --programmatic --quiet test --TOOL` for consistent Docker execution.

## CLI and Development Tools

### CLI Tools
- **gh is available. it's much preferable to trying to interact with github.com**