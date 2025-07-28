# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Command Reference

**IMPORTANT: All commands use docker.sh - no local dependencies except Docker required!**

```bash
# Essential Commands
./docker.sh up                    # Start all services
./docker.sh down                  # Stop all services
./docker.sh test                  # Run all tests and checks
./docker.sh logs app              # View service logs
./docker.sh shell app             # Open shell in container

# Testing Commands
./docker.sh test --pytest         # Run tests only
./docker.sh test --mypy          # Type checking only
./docker.sh test --black         # Format checking only
./docker.sh test --ruff          # Linting only
./docker.sh test --bandit        # Security scan only

# Scraper Commands
./docker.sh scraper --list       # List all scrapers
./docker.sh scraper --all        # Run all scrapers
./docker.sh scraper NAME         # Run specific scraper

# Programmatic Mode (for CI/automation)
./docker.sh --programmatic test  # Structured output
./docker.sh --json ps            # JSON output
./docker.sh --quiet up           # Minimal output
./docker.sh --no-color logs app  # No color codes
```

## Development Commands

### IMPORTANT: Docker-Only Development

**All development commands must use docker.sh** - no local Python dependencies are required except Docker.

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
./docker.sh test --pytest  # Should fail

# 3. Implement minimal code to pass
# ... write implementation ...

# 4. Run test again
./docker.sh test --pytest  # Should pass

# 5. Refactor and ensure tests still pass
./docker.sh test --pytest

# 6. Run full test suite before committing
./docker.sh test  # Runs all CI checks
```

### Running Tests with Docker
```bash
# Run all tests with coverage (runs all CI checks)
./docker.sh test

# Run only pytest with coverage
./docker.sh test --pytest

# Run specific test types
./docker.sh test --mypy      # Type checking only
./docker.sh test --black     # Code formatting only
./docker.sh test --ruff      # Linting only
./docker.sh test --bandit    # Security scan only
./docker.sh test --coverage  # Pytest with coverage check

# Programmatic mode for automation
./docker.sh --programmatic test --pytest          # Structured output
./docker.sh --json ps                             # JSON output
./docker.sh --quiet test --mypy                   # Minimal output
./docker.sh --programmatic --quiet test --black   # Combined flags
```

### Coverage Analysis
```bash
# Run tests with coverage check
./docker.sh test --coverage

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
./docker.sh test

# Run individual checks
./docker.sh test --mypy      # Type checking
./docker.sh test --black     # Code formatting
./docker.sh test --ruff      # Linting
./docker.sh test --bandit    # Security scan

# For programmatic use in CI/CD
./docker.sh --programmatic --quiet test --mypy
./docker.sh --programmatic --quiet test --black
./docker.sh --programmatic --quiet test --ruff
./docker.sh --programmatic --quiet test --bandit
```

### Development Setup
```bash
# Start all services (no local dependencies needed)
./docker.sh up                    # Development mode (default)
./docker.sh up --prod            # Production mode
./docker.sh up --with-init       # With database initialization

# Start specific services
./docker.sh up app worker        # Start only app and worker

# Service management
./docker.sh down                 # Stop all services
./docker.sh ps                   # List running services
./docker.sh logs app             # View service logs
./docker.sh shell app            # Open shell in container
./docker.sh exec app python --version  # Execute command
./docker.sh clean                # Stop and remove volumes

# Programmatic mode for automation
./docker.sh --json ps            # Get service status as JSON
./docker.sh --quiet up           # Start with minimal output
```

### Docker Build Commands
```bash
# Build all services
./docker.sh build

# Build specific service
./docker.sh build app
./docker.sh build worker

# The test image is automatically built when running tests
./docker.sh test  # Builds test image if needed
```

### Running Scrapers
```bash
# List available scrapers
./docker.sh scraper --list

# Run specific scraper
./docker.sh scraper nyc_efap_programs

# Run all scrapers
./docker.sh scraper --all

# Programmatic mode for automation
./docker.sh --programmatic scraper --list
./docker.sh --programmatic --quiet scraper nyc_efap_programs
```

### CI Checks
```bash
# Run all CI checks using Docker
./docker.sh test

# Or use the Docker-based CI script directly
./scripts/run-ci-checks-docker.sh

# For GitHub Actions or other CI systems
./docker.sh --programmatic --quiet test
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
./docker.sh claude-auth

# Check authentication status
curl http://localhost:8080/health

# Alternative manual commands
./docker.sh exec worker python -m app.claude_auth_manager setup
./docker.sh exec worker python -m app.claude_auth_manager status
./docker.sh exec worker python -m app.claude_auth_manager test
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
./docker.sh up haarrrvest-publisher

# View logs
./docker.sh logs haarrrvest-publisher

# Restart to trigger immediate processing
./docker.sh exec haarrrvest-publisher supervisorctl restart all

# Check service status
./docker.sh ps
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
The `.pre-commit-config.yaml` is configured to run all Python tools via `docker.sh`:
- **black-docker**: Code formatting
- **ruff-docker**: Linting
- **mypy-docker**: Type checking
- **pytest-docker**: Test suite

All hooks use `./docker.sh --programmatic --quiet test --TOOL` for consistent Docker execution.