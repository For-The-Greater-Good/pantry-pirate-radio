# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Test-Driven Development (TDD) Workflow

This project follows Test-Driven Development principles. Always write tests before implementing features:

1. **Red Phase**: Write a failing test that defines the desired behavior
2. **Green Phase**: Write the minimum code necessary to make the test pass
3. **Refactor Phase**: Improve the code while keeping tests passing

#### TDD Process for New Features
```bash
# 1. Create test file first
touch tests/test_new_feature.py

# 2. Write failing test
poetry run pytest tests/test_new_feature.py -v  # Should fail

# 3. Implement minimal code to pass
# ... write implementation ...

# 4. Run test again
poetry run pytest tests/test_new_feature.py -v  # Should pass

# 5. Refactor and ensure tests still pass
poetry run pytest tests/test_new_feature.py -v

# 6. Run full test suite before committing
poetry run pytest
```

### Running Tests
```bash
# Run all tests (coverage included by default)
poetry run pytest

# Run tests with specific coverage reports
poetry run pytest --cov=app --cov-report=html --cov-report=xml --cov-report=json

# Run tests without coverage (if needed)
poetry run pytest --no-cov

# Run specific test file
poetry run pytest tests/test_filename.py

# Run integration tests
poetry run pytest -m integration

# Run async tests
poetry run pytest -m asyncio

# Watch mode - rerun tests on file changes (requires pytest-watch)
poetry run ptw

# Run tests in parallel (requires pytest-xdist)
poetry run pytest -n auto

# Run only tests that failed in the last run
poetry run pytest --lf

# Run tests with verbose output and show local variables on failure
poetry run pytest -vvl
```

### Coverage Analysis
```bash
# Generate comprehensive coverage report
bash scripts/coverage-report.sh

# Check coverage with ratcheting mechanism
bash scripts/coverage-check.sh

# View coverage report in browser
open htmlcov/index.html

# Display coverage summary
poetry run coverage report --show-missing --sort=Cover

# Generate coverage reports in different formats
poetry run coverage html    # HTML report
poetry run coverage xml     # XML report (for CI)
poetry run coverage json    # JSON report (for automation)
```

### Code Quality
```bash
# Type checking
poetry run mypy .

# Code formatting
poetry run black .

# Linting
poetry run ruff .

# Security scan
poetry run bandit -r app/

# Check unused code
poetry run vulture app/
```

### Development Setup
```bash
# Install dependencies
poetry install

# Start all services (uses consolidated Dockerfile with multi-stage builds)
docker compose up -d

# Start specific service
docker compose up -d app worker recorder reconciler

# View logs
docker compose logs -f [service_name]

# Scale workers
docker compose up -d --scale worker=3

# Run FastAPI server locally
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker Build Commands
```bash
# Build all services (uses multi-stage Dockerfile)
docker compose build

# Build specific service target
docker build --target app -t pantry-pirate-radio:app .
docker build --target worker -t pantry-pirate-radio:worker .
docker build --target recorder -t pantry-pirate-radio:recorder .
docker build --target scraper -t pantry-pirate-radio:scraper .
docker build --target test -t pantry-pirate-radio:test .

# Run tests using Docker
docker build --target test -t pantry-pirate-radio:test .
docker run --rm pantry-pirate-radio:test
```

### Running Scrapers
```bash
# List available scrapers
python -m app.scraper --list

# Run specific scraper
python -m app.scraper nyc_efap_programs

# Run all scrapers
python -m app.scraper --all

# Run scrapers in parallel
python -m app.scraper --all --parallel --max-workers 4

# Test scrapers without processing
python -m app.scraper.test_scrapers --all
```

### CI Checks
```bash
# Run all expected CI checks
./scripts/run-ci-checks.sh
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
# Check authentication status
curl http://localhost:8080/health

# Interactive setup
docker-compose exec worker python -m app.claude_auth_manager setup

# Check status
docker-compose exec worker python -m app.claude_auth_manager status

# Test request
docker-compose exec worker python -m app.claude_auth_manager test
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
docker-compose up -d haarrrvest-publisher

# View logs
docker-compose logs -f haarrrvest-publisher

# Trigger immediate processing
docker-compose restart haarrrvest-publisher

# Manual testing without Docker
export DATABASE_URL=postgresql://user:pass@localhost:5432/pantry_pirate_radio
python test_haarrrvest_publisher.py
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
```