# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

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
docker-compose up -d

# Start specific service
docker-compose up -d app worker recorder reconciler

# View logs
docker-compose logs -f [service_name]

# Scale workers
docker-compose up -d --scale worker=3

# Run FastAPI server locally
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker Build Commands
```bash
# Build all services (uses multi-stage Dockerfile)
docker-compose build

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

Pantry Pirate Radio is a distributed food security data aggregation system implementing the OpenReferral Human Services Data Specification (HSDS). The system consists of multiple containerized services that work together to scrape, process, and serve food resource data.

### Docker Architecture

The project uses a **consolidated multi-stage Dockerfile** that builds all services from a single source. This approach provides:

- **Consistent base configuration** across all services
- **Efficient layer caching** for faster builds
- **Simplified maintenance** with single Dockerfile
- **Optimized images** with production/development separation

#### Docker Stages:
- `base` - Common dependencies (Python, Poetry, system packages)
- `production-base` - Production dependencies only
- `development-base` - All dependencies including dev tools
- `app` - FastAPI application service
- `worker` - RQ worker service (LLM processing)
- `recorder` - Job result archival service
- `scraper` - Data collection service
- `test` - Testing environment with dev dependencies
- `datasette-exporter` - Data export service

### Core Services

- **FastAPI App** (`app/main.py`): API server serving HSDS-compliant endpoints
- **Worker Pool** (`app/llm/queue/worker.py`): LLM-based data processing workers
- **Recorder Service** (`app/recorder/`): Job result archival and persistence
- **Reconciler Service** (`app/reconciler/`): Data consistency and versioning
- **Scrapers** (`app/scraper/`): Data collection from various sources
- **Database**: PostgreSQL with PostGIS for geographic data
- **Cache**: Redis for job queues and caching

### Key Components

#### Scrapers (`app/scraper/`)
- Individual scrapers for different data sources (NYC EFAP, FoodHelpline.org, etc.)
- Each scraper inherits from `ScraperJob` base class
- Scrapers write results to Redis queue for processing
- Base utilities in `utils.py` for geocoding and grid generation
- Test framework in `test_scrapers.py` for validation

#### LLM Processing (`app/llm/`)
- HSDS data alignment using AI models (`hsds_aligner/`)
- Supports OpenAI and Claude providers (`providers/`)
- Queue-based job processing with Redis (`queue/`)
- Confidence scoring and validation feedback loops
- Schema conversion system for structured output

#### Data Models (`app/models/hsds/`)
- Complete HSDS v3.1.1 implementation using Pydantic
- Geographic data handling with PostGIS
- Request/response models for API endpoints
- Type-safe validation throughout the system

#### Reconciler Service (`app/reconciler/`)
- Processes LLM outputs into HSDS-compliant database records
- Maintains version history for all records (`version_tracker.py`)
- Handles location matching and deduplication (`location_creator.py`)
- Creates organizations, services, and relationships (`organization_creator.py`, `service_creator.py`)
- Source-specific records with merge strategies (`merge_strategy.py`)

#### Recorder Service (`app/recorder/`)
- Archives job results to JSON files in `outputs/`
- Compresses raw data archives in `archives/`
- Provides audit trail for all processing
- Utilities in `utils.py` for file management

#### API Layer (`app/api/`)
- RESTful endpoints following HSDS specification
- Geographic search with bounding boxes and radius
- Pagination, filtering, and sorting capabilities
- CORS enabled, no authentication required (public data only)

### Data Flow

1. **Scrapers** collect data from sources → Redis queue
2. **Workers** process jobs using LLM providers → Database
3. **Reconciler** ensures data consistency and versioning
4. **Recorder** archives raw data and results
5. **API** serves processed data to clients

## Important Implementation Details

### HSDS Compliance
- Full OpenReferral HSDS v3.1.1 implementation
- Complete schema validation using Pydantic models
- Required fields enforcement and relationship integrity
- Taxonomy mapping for services, accessibility, and languages
- Geographic data validation with PostGIS

### LLM Integration
- Schema-guided HSDS alignment with confidence scoring
- Validation feedback loops with retry logic
- Support for structured output formats
- Field coherence validation and hallucination detection
- Caching system for improved performance
- **Two LLM providers supported:**
  - **OpenAI/OpenRouter**: HTTP API-based provider using OpenAI-compatible endpoints
  - **Claude**: CLI-based provider using the Claude Code SDK for direct Anthropic API access

### Testing Strategy
- Unit tests with pytest and asyncio support
- Integration tests for service interactions
- Property-based testing with Hypothesis
- VCR.py for HTTP request mocking
- Minimum 90% test coverage required
- Scraper testing framework for validation

### Type Safety
- Strict mypy configuration with comprehensive type checking
- All functions must have type annotations
- Pydantic models for data validation
- TypedDict definitions for structured data
- Optional types properly handled

### Code Style
- Black formatting (88 character line length)
- Ruff linting with security checks (bandit integration)
- PEP 8 compliance with specific overrides for tests
- Docstrings required for all public functions
- Structured logging with correlation IDs

### Geographic Constraints
- Continental US coverage only (25°N-49°N, -125°W to -67°W)
- PostGIS spatial indexing and queries
- Coordinate validation and clamping
- Large area partitioning for search optimization
- Grid generation utilities for comprehensive coverage

### Database Design
- PostgreSQL with PostGIS extensions
- Version tracking for all records
- Source-specific records with canonical merging
- Spatial indexing for geographic queries
- Automated backup system with retention policies

### Performance Considerations
- Async/await throughout the codebase
- Connection pooling for database and Redis
- Response caching with geographic tiles
- Batch processing for large datasets
- Queue-based job processing for scalability

### Security
- No authentication required (public data only)
- Rate limiting based on fair use
- Input validation and sanitization
- Security headers in API responses
- Bandit security scanning integrated

## Service-Specific Implementation Notes

### Scraper Development
- Inherit from `ScraperJob` base class
- Implement `scrape()` method for data collection
- Use `ScraperUtils` for queue management and grid generation
- Use `GeocoderUtils` for address geocoding with fallbacks
- Include comprehensive error handling and logging
- Follow rate limiting best practices

### LLM Processing
- Use HSDS aligner for schema compliance
- Implement confidence scoring and validation
- Handle structured output formats
- Include retry logic for failed alignments
- Cache responses for improved performance

#### Claude Provider Configuration
- **Environment**: Set `LLM_PROVIDER=claude` and optionally `ANTHROPIC_API_KEY`
- **Model Selection**: Use any Claude model (e.g., `claude-sonnet-4-20250514`)
- **Features**: Native structured output support, high-quality responses
- **Implementation**: Uses Claude Code SDK via subprocess calls
- **CLI Integration**: Leverages the `claude` CLI command for API access
- **Docker Support**: Node.js and Claude CLI pre-installed in all service containers
- **Shared Authentication**: Docker volume shares auth state across all scaled worker containers

#### Claude Authentication Setup
The Claude provider supports two authentication methods with shared state across workers:

1. **API Key Authentication** (for programmatic access):
   ```bash
   ANTHROPIC_API_KEY=your_actual_api_key_here
   ```

2. **Claude Max Account Authentication** (recommended for development):
   ```bash
   # Quick setup process
   docker compose up -d
   curl http://localhost:8080/health  # Check auth status
   docker compose exec worker python -m app.claude_auth_manager setup
   curl http://localhost:8080/health  # Verify authentication
   ```

#### Scaling Workers with Shared Authentication
```bash
# Scale to multiple workers - all share the same authentication
docker compose up -d --scale worker=3

# Check health across all workers
curl http://localhost:8080/health  # Worker 1
curl http://localhost:8081/health  # Worker 2
curl http://localhost:8082/health  # Worker 3

# Authenticate once, applies to all workers
docker compose exec worker python -m app.claude_auth_manager setup
```

#### Authentication Management Commands
```bash
# Check authentication status
docker compose exec worker python -m app.claude_auth_manager status

# Run interactive setup
docker compose exec worker python -m app.claude_auth_manager setup

# Test Claude request
docker compose exec worker python -m app.claude_auth_manager test

# View config files
docker compose exec worker python -m app.claude_auth_manager config

# Alternative: Direct Claude CLI
docker compose exec worker claude
```

#### Claude Failsafe and Retry System
The Claude provider includes intelligent failsafes and retry mechanisms:

**Authentication Failsafe:**
- Automatically detects when Claude is not authenticated
- Jobs are safely queued and retried every 5 minutes
- Clear error messages guide you to run authentication setup
- After 1 hour of failed auth attempts, jobs will fail with clear instructions

**Quota Management:**
- Automatically detects when Claude Max quota is exceeded
- Implements exponential backoff retry strategy:
  - 1st retry: 1 hour delay
  - 2nd retry: 1.5 hours delay
  - 3rd retry: 2.25 hours delay
  - Maximum delay: 4 hours
- Jobs are safely preserved and automatically retry when quota refills

**Configuration:**
```bash
# Claude retry settings (optional, these are the defaults)
CLAUDE_QUOTA_RETRY_DELAY=3600        # Initial delay when quota exceeded (1 hour)
CLAUDE_QUOTA_MAX_DELAY=14400         # Maximum delay (4 hours)
CLAUDE_QUOTA_BACKOFF_MULTIPLIER=1.5  # Exponential backoff multiplier
```

**Container Management:**
```bash
# Check auth status from inside container
docker compose exec worker python -m app.claude_auth_manager status

# Setup authentication interactively
docker compose exec worker python -m app.claude_auth_manager setup

# Test Claude requests
docker compose exec worker python -m app.claude_auth_manager test

# View configuration files
docker compose exec worker python -m app.claude_auth_manager config

# Get detailed JSON status
docker compose exec worker python -m app.claude_auth_manager status --json
```

**Health Check Endpoints:**
```bash
# Quick health check (requires CLAUDE_HEALTH_SERVER=true)
curl http://localhost:8080/health

# Detailed authentication status
curl http://localhost:8080/auth

# Monitor worker logs for retry information
docker compose logs -f worker
```

**Setup Workflow:**
1. Start containers: `docker-compose up -d`
2. Check status: `curl http://localhost:8080/health`
3. If authentication needed: `docker compose exec worker python -m app.claude_auth_manager setup`
4. Follow the interactive setup wizard
5. Verify: `curl http://localhost:8080/health`

### Reconciler Processing
- Process jobs in dependency order (organizations → locations → services)
- Maintain version history for all changes
- Handle location matching with coordinate-based deduplication
- Create source-specific records with merge strategies
- Implement comprehensive error handling and rollback

### API Development
- Follow HSDS specification for all endpoints
- Implement geographic search with spatial queries
- Include pagination and filtering capabilities
- Add comprehensive error handling with correlation IDs
- Implement response caching for performance

## Common Development Tasks

### Adding a New Scraper
1. Create `your_scraper_name_scraper.py` in `app/scraper/`
2. Inherit from `ScraperJob` base class
3. Implement `scrape()` method
4. Add comprehensive error handling
5. Include documentation in corresponding `.md` file
6. Add tests in `test_scrapers.py`

### Modifying HSDS Models
1. Update Pydantic models in `app/models/hsds/`
2. Run database migrations if schema changes
3. Update API endpoints and responses
4. Add validation tests
5. Update documentation

### Adding LLM Provider
1. Implement `BaseLLMProvider` interface in `app/llm/providers/`
2. Add provider-specific configuration
3. Implement caching and retry logic
4. Add provider to factory method
5. Write integration tests

### Database Schema Changes
1. Create migration script in `init-scripts/`
2. Update SQLAlchemy models if needed
3. Update reconciler logic for new fields
4. Add validation tests
5. Update API responses

### Docker Development Tasks
```bash
# Rebuild specific service after code changes
docker-compose build app && docker-compose up -d app

# Debug service startup issues
docker-compose logs -f [service_name]

# Access running container for debugging
docker-compose exec app bash
docker-compose exec worker bash

# Test Docker build stages
docker build --target production-base -t debug-base .
docker run --rm -it debug-base bash

# Validate multi-stage builds
docker build --target app -t test-app .
docker build --target worker -t test-worker .
docker build --target recorder -t test-recorder .
```

### Debugging Guidelines
- Use structured logging with correlation IDs
- Check Redis queue status: `docker-compose logs -f worker`
- Monitor database queries with SQL logging
- Use Prometheus metrics for system health
- Check individual service logs for detailed errors
- Use `rq-dashboard` for queue monitoring at http://localhost:9181
- Debug Docker builds: `docker build --target [stage] -t debug-[stage] .`
- Check build context: Ensure `.dockerignore` excludes unnecessary files

## Environment Variables

### Required
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string

### Optional
- `OPENROUTER_API_KEY`: For OpenAI/OpenRouter LLM providers
- `ANTHROPIC_API_KEY`: For Claude LLM provider
- `LLM_PROVIDER`: LLM provider to use ("openai" or "claude")
- `LLM_MODEL_NAME`: Default LLM model to use
- `OUTPUT_DIR`: Directory for output files (default: `outputs/`)
- `BACKUP_KEEP_DAYS`: Database backup retention days

## Service URLs (Development)
- FastAPI API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- RQ Dashboard: http://localhost:9181
- Datasette: http://localhost:8001
- Prometheus Metrics: http://localhost:8000/metrics

## Testing
- Run all tests: `poetry run pytest`
- Run with coverage: `poetry run pytest --cov`
- Test scrapers: `python -m app.scraper.test_scrapers --all`
- Integration tests: `poetry run pytest -m integration`

## Key Dependencies
- FastAPI for API framework
- Pydantic for data validation
- SQLAlchemy for database ORM
- Redis for job queues
- PostGIS for geographic data
- OpenAI/Claude for LLM processing
- Prometheus for metrics
- Docker/Docker Compose for containerization
