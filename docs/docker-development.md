# Docker Development Environment

This guide covers setting up and using the Docker-based development environment for Pantry Pirate Radio.

## Overview

The development environment uses Docker Compose with multiple configuration files:
- `docker-compose.yml` - Base services configuration
- `docker-compose.dev.yml` - Development-specific overrides
- `docker-compose.with-init.yml` - Database initialization configuration

## Quick Start

### Using bouy Helper (Recommended)

```bash
# Start development services (empty database)
./bouy up --dev

# Start with pre-populated data from HAARRRvest
./bouy up --dev --with-init

# View logs
./bouy logs app

# Stop services
./bouy down
```

### Alternative: Understanding the Underlying Commands

While bouy is the recommended approach, it's helpful to understand what it does behind the scenes:

- `./bouy up` runs the appropriate docker compose configuration
- `./bouy logs` follows service logs
- `./bouy down` stops all services

Always use bouy for consistency and additional safety checks.

### Development with Pre-populated Data

To start with ~90 days of historical data from HAARRRvest:

```bash
# Using bouy (recommended)
./bouy up --dev --with-init

# Monitor initialization progress
./bouy logs db-init

# The bouy command handles all the complexity for you
# It automatically uses the correct compose files and profiles

# Monitor initialization progress (takes 5-15 minutes)
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
./bouy exec db psql -U postgres -d pantry_pirate_radio

# Run migrations
./bouy exec app alembic upgrade head

# Create backup
./bouy exec db-backup /backup.sh
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

# Run specific test files directly
./bouy test --pytest tests/test_api.py
./bouy test --pytest tests/test_api.py::TestAPI::test_get_organizations
./bouy test --pytest -- --cov
```

### 3. Code Quality

```bash
# Using bouy (updates local files)
./bouy test --black           # Format code
./bouy test --ruff            # Run linter
./bouy test --mypy            # Type checking

# These commands automatically update your local files
# The test container has your code mounted, so changes are reflected locally
```

### 4. Debugging

```bash
# Using bouy
./bouy logs app               # View service logs
./bouy logs worker           # View worker logs
./bouy shell app             # Shell access
./bouy exec app python       # Python REPL

# Follow logs for multiple services
./bouy logs app worker

# Get Python REPL in app container
./bouy exec app python
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
# Authenticate Claude (interactive)
./bouy claude-auth

# Check status and manage auth
./bouy exec worker python -m app.claude_auth_manager status
./bouy exec worker python -m app.claude_auth_manager setup
./bouy exec worker python -m app.claude_auth_manager test

# Health check endpoint
curl http://localhost:8080/health
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
# Update dependencies in container
./bouy exec app poetry update
./bouy exec app poetry lock

# Rebuild containers after changes
./bouy build                  # Rebuild all services
./bouy build app             # Rebuild specific service
./bouy build --no-cache app  # Force rebuild
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

### Container won't start

```bash
# Check logs
./bouy logs app

# Check all service status
./bouy ps

# Verbose mode for debugging
./bouy --verbose up
```

### Database connection issues

```bash
# Verify database is running
./bouy ps | grep db

# Check database logs
./bouy logs db

# Test connection
./bouy exec db pg_isready
```

### Slow initialization

The db-init process can take 5-30 minutes depending on:
- Amount of historical data
- System performance
- Network speed for cloning HAARRRvest

Monitor progress:
```bash
# Watch initialization logs
./bouy logs -f db-init

# Check database record count
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT COUNT(*) FROM organization;"
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
./bouy exec app bash /app/scripts/create-sql-dump.sh

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