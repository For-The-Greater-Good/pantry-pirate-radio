# Docker Development Environment

This guide covers setting up and using the Docker-based development environment for Pantry Pirate Radio.

## Overview

The development environment uses Docker Compose with multiple configuration files:
- `docker-compose.yml` - Base services configuration
- `docker-compose.dev.yml` - Development-specific overrides
- `docker-compose.with-init.yml` - Database initialization configuration

## Quick Start

### Using docker.sh Helper (Recommended)

```bash
# Start development services (empty database)
./docker.sh up --dev

# Start with pre-populated data from HAARRRvest
./docker.sh up --dev --with-init

# View logs
./docker.sh logs app

# Stop services
./docker.sh down
```

### Using Docker Compose Directly

```bash
# Start development services (empty database)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Development with Pre-populated Data

To start with ~90 days of historical data from HAARRRvest:

```bash
# Using docker.sh (recommended)
./docker.sh up --dev --with-init

# Monitor initialization progress
./docker.sh logs db-init

# Or using docker compose directly
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.with-init.yml --profile with-init up -d

# Monitor initialization progress (takes 5-15 minutes)
docker compose logs -f db-init

# Check when initialization is complete
docker compose ps db-init  # Should show "healthy" when done
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

### Core Services

- **app**: FastAPI application (development mode with hot reload)
- **db**: PostgreSQL with PostGIS extensions
- **cache**: Redis for job queuing
- **db-backup**: Automated database backups

### Optional Services (with --profile with-init)

- **db-init**: Populates database from HAARRRvest data
- **haarrrvest-publisher**: Manages data repository

## Development Workflow

### 1. Database Management

```bash
# Connect to database
docker compose exec db psql -U postgres -d pantry_pirate_radio

# Run migrations
docker compose exec app alembic upgrade head

# Create backup
docker compose exec db-backup /backup.sh
```

### 2. Running Tests

```bash
# Using docker.sh with bind-mounted code (recommended)
./docker.sh test                   # Run all CI checks
./docker.sh test --pytest          # Run tests with coverage
./docker.sh test --mypy            # Type checking
./docker.sh test --black           # Format code (updates local files)
./docker.sh test --ruff            # Run linter
./docker.sh test --bandit          # Security scan

# Or run directly in container
docker compose exec app poetry run pytest
docker compose exec app poetry run pytest tests/test_api.py
docker compose exec app poetry run pytest --cov
```

### 3. Code Quality

```bash
# Using docker.sh (updates local files)
./docker.sh test --black           # Format code
./docker.sh test --ruff            # Run linter
./docker.sh test --mypy            # Type checking

# Or run directly
docker compose exec app poetry run black .
docker compose exec app poetry run ruff .
docker compose exec app poetry run mypy .
```

### 4. Debugging

```bash
# Using docker.sh
./docker.sh logs app               # View service logs
./docker.sh logs worker           # View worker logs
./docker.sh shell app             # Shell access
./docker.sh exec app python       # Python REPL

# Or directly
docker compose logs -f app
docker compose logs -f worker
docker compose exec app bash
docker compose exec app python
```

### 5. Running Scrapers

```bash
# Using docker.sh
./docker.sh scraper --list        # List available scrapers
./docker.sh scraper nyc_efap_programs  # Run specific scraper
./docker.sh scraper --all         # Run all scrapers

# Or directly
docker compose exec scraper python -m app.scraper --list
docker compose exec scraper python -m app.scraper nyc_efap_programs
```

### 6. Claude Authentication

```bash
# Authenticate Claude provider
./docker.sh claude-auth

# Or directly
docker compose exec worker claude
```

## Environment Configuration

### Development Defaults

The dev environment uses these defaults (override in `.env`):

```bash
# Database
POSTGRES_PASSWORD=defaultpassword
POSTGRES_DB=pantry_pirate_radio
DATABASE_URL=postgresql+asyncpg://postgres:defaultpassword@db:5432/pantry_pirate_radio

# Redis
REDIS_URL=redis://cache:6379/0

# Development
DEBUG=1
PYTHONPATH=/workspace
```

### Custom Configuration

Create a `.env` file for custom settings:

```bash
# LLM Provider
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your_key_here

# HAARRRvest Repository
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_token
```

## Common Tasks

### Starting Fresh

```bash
# Using docker.sh
./docker.sh clean                  # Remove all data
./docker.sh up --dev              # Start fresh

# Or manually
docker compose down -v
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Switching Between Empty and Populated Database

```bash
# From empty to populated
docker compose down
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.with-init.yml --profile with-init up -d

# From populated to empty
docker compose down -v  # -v removes volumes
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Updating Dependencies

```bash
# Update Poetry dependencies
docker compose exec app poetry update

# Rebuild containers after Dockerfile changes
docker compose build --no-cache
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs app

# Verify environment
docker compose config

# Check file permissions
ls -la docker-compose*.yml
```

### Database connection issues

```bash
# Verify database is running
docker compose ps db

# Check database logs
docker compose logs db

# Test connection
docker compose exec db pg_isready
```

### Slow initialization

The db-init process can take 5-30 minutes depending on:
- Amount of historical data
- System performance
- Network speed for cloning HAARRRvest

Monitor progress:
```bash
# Watch initialization logs
docker compose logs -f db-init

# Check database record count
docker compose exec db psql -U postgres -d pantry_pirate_radio -c "SELECT COUNT(*) FROM organization;"
```

## Performance Optimization

### Resource Limits

The dev environment sets resource limits to prevent system overload:

```yaml
# worker service limits
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '2.0'
```

Adjust in `docker-compose.dev.yml` if needed.

### Volume Performance

On macOS, use the `cached` consistency mode for better performance:

```yaml
volumes:
  - .:/workspace:cached
```

## Fast SQL-based Initialization

The system now supports fast database initialization using SQL dumps:

### How It Works

1. **Automatic SQL Dumps**: HAARRRvest publisher creates daily compressed dumps
2. **Smart Detection**: db-init checks for SQL dumps before falling back to JSON
3. **Fast Restore**: <5 minutes vs 30+ minutes for JSON replay
4. **Compression**: Dumps are ~10% of original database size

### Manual SQL Dump Creation

```bash
# Create a SQL dump from current database
docker compose exec app bash /app/scripts/create-sql-dump.sh

# Dumps are saved to HAARRRvest/sql_dumps/
# Latest dump is symlinked as latest.sql.gz
```

### Performance Comparison

| Method | Time | Use Case |
|--------|------|----------|
| SQL Dump | <5 minutes | Default when dumps available |
| Empty Database | Instant | When no dumps available |

**Note**: JSON replay functionality has been removed from db-init for consistency. To populate from JSON files, use the replay tool directly.

## Next Steps

- See [Docker Quick Start](docker-quickstart.md) for production setup
- Read [Multi-Worker Support](multi-worker-support.md) for scaling
- Check [Troubleshooting](troubleshooting.md) for common issues