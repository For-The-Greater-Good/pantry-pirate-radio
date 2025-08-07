# Docker Development Environment

This guide covers setting up and using the Docker-based development environment for Pantry Pirate Radio.

## Overview

The development environment uses a unified Docker image architecture with intelligent service routing. Configuration is managed through Docker Compose files located in `.docker/compose/`:
- `base.yml` - Core services configuration (all modes)
- `docker-compose.dev.yml` - Development-specific overrides
- `docker-compose.prod.yml` - Production configuration
- `docker-compose.test.yml` - Test environment settings
- `docker-compose.with-init.yml` - Database initialization with data

## Quick Start

### Using bouy Commands (Recommended)

```bash
# Initial setup wizard (first time only)
./bouy setup                 # Interactive configuration

# Start development services
./bouy up                    # Default dev mode, empty database
./bouy up --dev             # Explicit dev mode
./bouy up --with-init       # Dev mode with populated database

# Service management
./bouy logs app             # View specific service logs
./bouy ps                   # Check service status
./bouy down                 # Stop all services
./bouy clean                # Stop and remove all volumes
```

### Understanding Bouy's Architecture

The bouy script provides intelligent orchestration:

1. **Automatic Image Building**: Checks if unified image exists, builds if needed
2. **Compose File Management**: Selects appropriate compose files based on mode
3. **Environment Loading**: Automatically exports `.env` variables
4. **Output Modes**: Supports normal, programmatic, quiet, and JSON output
5. **Safety Checks**: Validates Docker availability and configuration

Bouy translates high-level commands into proper Docker Compose operations with the correct file combinations and environment settings.

### Development with Pre-populated Data

To start with ~90 days of historical data from HAARRRvest:

```bash
# Using bouy (recommended)
./bouy up --dev --with-init

# Monitor initialization progress
./bouy logs db-init

# Monitor initialization progress (now <5 minutes with SQL dumps)
./bouy logs db-init

# Check service status
./bouy ps  # Check all services including db-init
```

## VSCode DevContainer

The recommended development approach uses VSCode DevContainers:

1. **Open in VSCode**: Open the project folder in VSCode
2. **Reopen in Container**: When prompted, select "Reopen in Container"
3. **Automatic Setup**: DevContainer handles all dependencies and configuration

### DevContainer Features

- Pre-configured Python environment with Poetry
- All required VSCode extensions
- Git configuration mounting
- Automatic dependency installation
- Pre-commit hooks setup

## Service Architecture

### Unified Docker Image Architecture

Pantry Pirate Radio uses a **single unified Docker image** (`pantry-pirate-radio:latest`) for all Python services:

**Benefits**:
- **Build Efficiency**: Single 5-minute build vs 35+ minutes for separate images
- **Cache Optimization**: 80% reduction in disk usage through shared layers
- **Simplified CI/CD**: One build artifact for all services
- **Consistent Dependencies**: Identical Python environment across services
- **Easy Updates**: All services updated with one image rebuild

**Service Selection**:
The `docker-entrypoint.sh` script routes to the appropriate service based on:
1. Command argument (e.g., `["app"]`, `["worker"]`)
2. `SERVICE_TYPE` environment variable
3. Direct command execution for unrecognized services

### Core Services

#### Application Services (Unified Image)
- **app**: FastAPI application
  - Port: 8000
  - Command: `["app"]` → Uvicorn server
  - Dev mode: Hot reload enabled via volume mount
  
- **worker**: LLM processing workers
  - Ports: 8080-8089 (health endpoints)
  - Command: `["worker"]` → RQ worker(s)
  - Scaling: `WORKER_COUNT` for vertical, Docker scale for horizontal
  - Claude integration for LLM queue
  
- **recorder**: Job archival service
  - Command: `["recorder"]` → RQ worker on recorder queue
  - Volumes: Includes `/app/archives` for backups
  
- **reconciler**: Data consistency service
  - Command: `["reconciler"]` → RQ worker on reconciler queue
  
- **scraper**: Data collection service
  - Command: `["scraper"]`
  - Features: Playwright/Chromium for web scraping
  
- **haarrrvest-publisher**: Data publishing service
  - Command: `["publisher"]`
  - Manages Git repository and SQLite generation

#### Infrastructure Services
- **db**: PostgreSQL 15 with PostGIS 3.3
  - Port: 5432
  - Health check: `pg_isready`
  
- **cache**: Redis 7 Alpine
  - Port: 6379
  - Persistence: `redis_data` volume
  

### Optional Services

#### Database Initialization (--with-init flag)
- **db-init**: Populates database from SQL dumps
  - Profile: `with-init` (only runs when specified)
  - Process: Restores latest SQL dump from HAARRRvest
  - Duration: <5 minutes for full database
  - Fallback: Empty database if no dumps available

#### Data Visualization
- **datasette**: Interactive SQLite browser
  - Port: 8001
  - Specialized image with Datasette installed
  - Waits for HAARRRvest publisher to generate SQLite
  
- **rq-dashboard**: Job queue monitor
  - Port: 9181
  - Uses unified image with `["rq-dashboard"]` command
  
- **content-store-dashboard**: Content management UI
  - Port: 5050
  - Uses unified image with `["dashboard"]` command

## Development Workflow

### 1. Database Management

```bash
# Connect to database
./bouy exec db psql -U postgres -d pantry_pirate_radio

# Run migrations (if needed)
./bouy exec app alembic upgrade head

# Check database status
./bouy exec db pg_isready

# View table counts
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT COUNT(*) FROM organization;"

# Manual backup
./bouy exec db pg_dump -U postgres pantry_pirate_radio > backup.sql

# Restore from backup
./bouy exec db psql -U postgres -d pantry_pirate_radio < backup.sql
```

### 2. Running Tests

```bash
# Using bouy (recommended)
./bouy test                   # Run all CI checks
./bouy test --pytest          # Run tests with coverage
./bouy test --mypy            # Type checking
./bouy test --black           # Format code (updates local files)
./bouy test --ruff            # Run linter
./bouy test --bandit          # Security scan

# Run specific test files
./bouy test --pytest tests/test_api.py
./bouy test --pytest tests/test_api.py::TestAPI::test_get_organizations

# Pass additional arguments
./bouy test --pytest -- -v              # Verbose output
./bouy test --pytest -- -x              # Stop on first failure
./bouy test --pytest -- --pdb           # Drop to debugger on failure
./bouy test --pytest -- -k test_name    # Run tests matching pattern
```

### 3. Code Quality

```bash
# Code formatting (modifies files)
./bouy test --black           # Auto-format all code
./bouy test --black app/      # Format specific directory

# Linting and analysis
./bouy test --ruff            # Fast Python linter
./bouy test --mypy            # Static type checking
./bouy test --bandit          # Security vulnerability scan
./bouy test --vulture         # Find dead code
./bouy test --xenon           # Check code complexity

# Dependency security
./bouy test --safety          # Check for known vulnerabilities
./bouy test --pip-audit       # Audit pip packages

# Coverage analysis
./bouy test --pytest          # Generates coverage reports
./bouy test --coverage        # Analyze existing coverage
open htmlcov/index.html       # View HTML coverage report
```

### 4. Debugging

```bash
# View logs
./bouy logs                   # All services
./bouy logs app              # Specific service
./bouy logs app worker       # Multiple services
./bouy logs -f db-init       # Follow logs (real-time)

# Interactive debugging
./bouy shell app             # Bash shell in container
./bouy exec app python       # Python REPL
./bouy exec app ipython      # IPython if installed

# Debug service startup
./bouy --verbose up          # Verbose output
./bouy ps                    # Check service health

# Inspect container
./bouy exec app env          # View environment variables
./bouy exec app ls -la /app  # Check file structure
./bouy exec app pip list     # View installed packages
```

### 5. Running Scrapers

```bash
# List and run scrapers
./bouy scraper --list        # List available scrapers
./bouy scraper nyc_efap_programs  # Run specific scraper
./bouy scraper --all         # Run all scrapers

# Programmatic mode for automation
./bouy --programmatic scraper --list
./bouy --programmatic --quiet scraper nyc_efap_programs
./bouy --programmatic --quiet scraper --all

# Monitor scraper output
./bouy logs scraper          # View scraper logs
```

### 6. Claude Authentication

```bash
# Interactive authentication
./bouy claude-auth           # Full interactive flow
./bouy claude-auth setup     # Setup authentication
./bouy claude-auth status    # Check current status
./bouy claude-auth test      # Test Claude API
./bouy claude-auth config    # Show configuration

# Manual authentication in container
./bouy exec worker python -m app.claude_auth_manager setup
./bouy exec worker python -m app.claude_auth_manager status
./bouy exec worker python -m app.claude_auth_manager test

# Health monitoring
curl http://localhost:8080/health  # Worker health endpoint

# View Claude logs
./bouy logs worker | grep -i claude
```

## Environment Configuration

### Development Environment Variables

The development environment configuration (from `.docker/compose/docker-compose.dev.yml`):

```bash
# Database (defaults from .env or inline)
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-pirate}
POSTGRES_DB=pantry_pirate_radio
DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASSWORD:-pirate}@db:5432/pantry_pirate_radio

# Redis
REDIS_URL=${REDIS_URL:-redis://cache:6379/0}

# Development flags
DEBUG=1
PYTHONPATH=/app

# Compose project name (for consistent networking)
COMPOSE_PROJECT_NAME=pantry-pirate-radio
```

### Custom Configuration

Use `./bouy setup` for interactive configuration or create `.env` manually:

```bash
# Database
POSTGRES_PASSWORD=pirate
POSTGRES_USER=postgres
POSTGRES_DB=pantry_pirate_radio

# LLM Provider
LLM_PROVIDER=claude              # or 'openai'
ANTHROPIC_API_KEY=your_key       # For Claude API
OPENROUTER_API_KEY=your_key      # For OpenAI

# HAARRRvest Repository
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_token       # Or 'skip' for read-only
PUBLISHER_PUSH_ENABLED=false    # Set 'true' only in production

# Worker Configuration
WORKER_COUNT=2                   # Workers per container
QUEUE_NAME=llm                  # Queue to process
CLAUDE_HEALTH_SERVER=true       # Enable health checks

# Development
DEBUG=1
PYTHONPATH=/app
```

## Common Tasks

### Starting Fresh

```bash
# Clean and restart
./bouy clean                  # Remove all data and volumes
./bouy up                     # Start fresh (dev mode by default)
./bouy up --with-init        # Start with populated database

# Check everything is running
./bouy ps
./bouy --json ps             # JSON output for scripts
```

### Switching Between Empty and Populated Database

```bash
# Start with populated database
./bouy clean                  # Clear existing data
./bouy up --with-init        # Start with HAARRRvest data

# Start with empty database
./bouy clean                  # Clear existing data
./bouy up                     # Start fresh

# Monitor initialization
./bouy logs db-init          # Watch database population
./bouy logs haarrrvest-publisher  # Watch data sync
```

### Updating Dependencies

```bash
# Update dependencies
./bouy exec app poetry update           # Update all packages
./bouy exec app poetry add package      # Add new package
./bouy exec app poetry remove package   # Remove package
./bouy exec app poetry lock             # Update lock file

# Export updated dependencies to host
./bouy exec app cat poetry.lock > poetry.lock
./bouy exec app cat pyproject.toml > pyproject.toml

# Rebuild services
./bouy build                  # Build all services
./bouy build app             # Build unified image only

# Force rebuild without cache
docker compose -f .docker/compose/base.yml build --no-cache app

# The unified image is used by these services:
# - app (FastAPI server)
# - worker (LLM processing)
# - recorder (job archival)
# - reconciler (data consistency)
# - scraper (data collection)
# - haarrrvest-publisher (data publishing)
# - rq-dashboard (monitoring)
# - content-store-dashboard (content UI)
# - db-init (database initialization)

# Verify image
docker images | grep pantry-pirate-radio
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run Tests
  run: |
    ./bouy --programmatic --quiet test

- name: Check Types
  run: |
    ./bouy --programmatic --quiet test --mypy

- name: Run Linter
  run: |
    ./bouy --programmatic --quiet test --ruff
```

### Jenkins Pipeline Example
```groovy
stage('Test') {
    steps {
        sh './bouy --programmatic --quiet test'
    }
}

stage('Deploy') {
    steps {
        sh './bouy --programmatic up --prod'
    }
}
```

### GitLab CI Example
```yaml
test:
  script:
    - ./bouy --programmatic --quiet test

deploy:
  script:
    - ./bouy --programmatic up --prod
```

## Troubleshooting

### Container Won't Start

```bash
# Check service status and health
./bouy ps
./bouy ps | grep -E "(unhealthy|restarting)"

# View detailed logs
./bouy logs app              # Specific service
./bouy logs | tail -100      # Last 100 lines of all logs

# Verbose startup for debugging
./bouy --verbose up

# Check Docker resources
docker system df             # Disk usage
docker system prune -a       # Clean up (careful!)

# Rebuild if image is corrupted
./bouy build app
```

### Database Connection Issues

```bash
# Verify database is running and healthy
./bouy ps | grep db

# Check database logs for errors
./bouy logs db | grep -E "(ERROR|FATAL)"

# Test connection
./bouy exec db pg_isready -U postgres -d pantry_pirate_radio

# Check environment variables
./bouy exec app env | grep -E "(POSTGRES|DATABASE_URL)"

# Test connection from app container
./bouy exec app python -c "from app.database import get_db_session; print('Connected!')"

# Common fixes
./bouy down              # Stop services
./bouy up db cache       # Start just database and cache
./bouy logs -f db        # Watch for startup completion
./bouy up                # Start remaining services
```

### Slow Initialization

Modern initialization is much faster:
- **SQL Dump Restore**: <5 minutes (default when available)
- **Empty Database**: Instant (fallback if no dumps)

Monitor progress:
```bash
# Watch initialization
./bouy logs -f db-init

# Check HAARRRvest repository status
./bouy logs haarrrvest-publisher | grep -E "(Cloning|Pulling|Ready)"

# Verify SQL dumps exist
./bouy exec haarrrvest-publisher ls -la /data-repo/sql_dumps/

# Check database population
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "
  SELECT 
    schemaname,
    tablename,
    n_live_tup as row_count 
  FROM pg_stat_user_tables 
  ORDER BY n_live_tup DESC;"
```

### Claude Authentication Issues

```bash
# Check authentication status
./bouy claude-auth status

# View detailed Claude logs
./bouy logs worker | grep -i claude

# Manual authentication
./bouy exec worker python -m app.claude_auth_manager setup

# Verify Claude CLI installation
./bouy exec worker which claude
./bouy exec worker claude --version

# Check environment
./bouy exec worker env | grep -E "(LLM_PROVIDER|ANTHROPIC)"
```

## Unified Image Architecture

### How Service Selection Works

The unified image's entrypoint (`/scripts/docker-entrypoint.sh`) routes services:

```bash
# Command-based routing (preferred)
docker run pantry-pirate-radio:latest app         # FastAPI server
docker run pantry-pirate-radio:latest worker      # RQ worker
docker run pantry-pirate-radio:latest publisher   # HAARRRvest

# SERVICE_TYPE environment variable (alternative)
SERVICE_TYPE=app docker run pantry-pirate-radio:latest

# Direct command execution (fallback)
docker run pantry-pirate-radio:latest python script.py
```

**Service Routing Map**:
| Command | Service | Process |
|---------|---------|----------|
| `app`, `api`, `fastapi` | FastAPI | Uvicorn on port 8000 |
| `worker`, `llm-worker` | LLM Worker | Claude-aware RQ worker |
| `simple-worker` | Basic Worker | Standard RQ worker |
| `recorder` | Recorder | RQ worker on recorder queue |
| `reconciler` | Reconciler | RQ worker on reconciler queue |
| `scraper` | Scraper | Python scraper module |
| `publisher` | HAARRRvest | Publisher service |
| `dashboard` | Content Store | Dashboard on port 5050 |
| `rq-dashboard` | RQ Monitor | Dashboard on port 9181 |
| `db-init` | DB Initialize | Init database script |
| `test` | Test Runner | Pytest execution |
| `shell`, `bash` | Interactive | Bash shell |
| Other | Direct Exec | Executes command as-is |

### Benefits of Unified Image

1. **Build Performance**: 
   - Single 5-minute build vs 35+ minutes for separate images
   - Parallel layer caching during build
   - Incremental rebuilds with layer reuse

2. **Storage Efficiency**:
   - 80% reduction in disk usage
   - Single base layer shared across all services
   - Deduplication at Docker layer level

3. **Operational Simplicity**:
   - One image to build, test, and deploy
   - Consistent Python environment everywhere
   - Single dependency update point

4. **Development Experience**:
   - Faster container starts (image already cached)
   - Consistent debugging environment
   - Same tools available in all containers

5. **CI/CD Benefits**:
   - Single build artifact
   - Faster pipeline execution
   - Simplified versioning and tagging

## Performance Optimization

### Resource Management

```bash
# Monitor resource usage
docker stats --no-stream

# Check specific service
docker stats pantry-pirate-radio_worker_1

# Set resource limits (add to docker-compose override)
```

```yaml
# Example: .docker/compose/docker-compose.dev.yml
services:
  worker:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 512M
          cpus: '0.5'
```

### Volume Performance

#### macOS Optimization
```yaml
# Use cached or delegated consistency
volumes:
  - .:/app:cached           # Host changes may have delay
  - .:/app:delegated       # Container performance priority
```

#### Linux Performance
```yaml
# Native performance, no special flags needed
volumes:
  - .:/app
```

#### Windows (WSL2)
```bash
# Store code in WSL2 filesystem for best performance
# Avoid mounting from Windows filesystem
cd ~/projects/pantry-pirate-radio
./bouy up
```

## Database Initialization Methods

### Fast SQL-based Initialization (Default)

The system uses compressed SQL dumps for rapid database population:

#### Automatic Process
1. **Daily Dumps**: HAARRRvest publisher creates compressed SQL dumps
2. **Smart Detection**: db-init checks `/data-repo/sql_dumps/` for dumps
3. **Fast Restore**: <5 minutes for complete database
4. **Compression**: Dumps use gzip (~90% size reduction)

#### Manual Operations
```bash
# Create SQL dump manually
./bouy exec db pg_dump -U postgres pantry_pirate_radio | gzip > dump.sql.gz

# Restore from dump
gunzip -c dump.sql.gz | ./bouy exec db psql -U postgres -d pantry_pirate_radio

# View available dumps
./bouy exec haarrrvest-publisher ls -lh /data-repo/sql_dumps/
```

### Performance Comparison

| Method | Time | Storage | Use Case |
|--------|------|---------|----------|
| SQL Dump Restore | <5 min | ~50MB compressed | Production, development |
| Empty Database | Instant | 0 | Testing, CI/CD |
| JSON Replay | Removed | - | Use replay tool if needed |

### Controlling Initialization

```bash
# Skip initialization entirely
SKIP_DB_INIT=true ./bouy up --with-init

# CI/CD mode (auto-skips)
CI=true ./bouy up --with-init

# Force empty database
rm -rf volumes/haarrrvest_repo/sql_dumps/
./bouy up --with-init
```

## Docker Networking

### Service Discovery

Services communicate using container names on the internal network:

```python
# Example: Connecting from app to database
DATABASE_URL = "postgresql://postgres:password@db:5432/pantry_pirate_radio"
REDIS_URL = "redis://cache:6379/0"
```

### Port Mappings

| Service | Internal | External | Purpose |
|---------|----------|----------|----------|
| app | 8000 | 8000 | FastAPI application |
| db | 5432 | 5432 | PostgreSQL database |
| cache | 6379 | 6379 | Redis cache |
| worker | 8080 | 8080-8089 | Health endpoints |
| rq-dashboard | 9181 | 9181 | Queue monitoring |
| datasette | 8001 | 8001 | Data viewer |
| content-store-dashboard | 5050 | 5050 | Content UI |

### Custom Networks

```yaml
# Create isolated network for services
networks:
  backend:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

## Security Considerations

### Development Security

```bash
# Use .env for sensitive data
echo '.env' >> .gitignore

# Rotate credentials regularly
./bouy setup  # Generate new passwords

# Limit port exposure in production
# Edit .docker/compose/docker-compose.prod.yml
```

### Production Hardening

1. **Database Security**:
   - Change default passwords
   - Use SSL/TLS connections
   - Limit network exposure

2. **API Security**:
   - Enable CORS properly
   - Use HTTPS in production
   - Implement rate limiting

3. **Container Security**:
   - Run as non-root user
   - Use read-only filesystems where possible
   - Scan images for vulnerabilities

## Advanced Topics

### Custom Service Development

1. **Add new service to unified image**:
   ```python
   # Edit docker-entrypoint.sh
   case "$SERVICE" in
       my-service)
           echo "Starting my service..."
           exec python -m app.my_service
           ;;
   ```

2. **Create compose overlay**:
   ```yaml
   # .docker/compose/docker-compose.my-service.yml
   services:
     my-service:
       image: pantry-pirate-radio:latest
       command: ["my-service"]
       depends_on:
         db:
           condition: service_healthy
   ```

3. **Update bouy script**:
   ```bash
   # Add to bouy command handling
   my-service)
       ./bouy up my-service
       ;;
   ```

## Next Steps

- [Docker Startup Sequence](docker-startup-sequence.md) - Detailed startup flow
- [Multi-Worker Support](multi-worker-support.md) - Scaling workers
- [Codespaces Setup](codespaces-setup.md) - Cloud development
- [Architecture](architecture.md) - System design