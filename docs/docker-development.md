# Docker Development Environment

This guide covers setting up and using the Docker-based development environment for Pantry Pirate Radio.

## Overview

The development environment uses Docker Compose with multiple configuration files:
- `docker-compose.yml` - Base services configuration
- `docker-compose.dev.yml` - Development-specific overrides
- `docker-compose.with-init.yml` - Database initialization configuration

## Quick Start

### Basic Development Environment

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
# Start dev environment with database initialization
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
# Run tests in container
docker compose exec app poetry run pytest

# Run specific test file
docker compose exec app poetry run pytest tests/test_api.py

# Run with coverage
docker compose exec app poetry run pytest --cov
```

### 3. Code Quality

```bash
# Format code
docker compose exec app poetry run black .

# Run linter
docker compose exec app poetry run ruff .

# Type checking
docker compose exec app poetry run mypy .
```

### 4. Debugging

```bash
# View service logs
docker compose logs -f app
docker compose logs -f worker

# Shell access
docker compose exec app bash

# Python REPL with app context
docker compose exec app python
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
# Remove all data and start clean
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