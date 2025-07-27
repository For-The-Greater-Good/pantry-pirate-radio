# Docker Quick Start Guide

Get Pantry Pirate Radio running quickly with Docker Compose.

## Prerequisites

- Docker Desktop (Mac/Windows) or Docker Engine (Linux)
- Git
- 4GB+ available RAM
- 10GB+ available disk space

## Quick Start Options

### Option 1: Production Mode with Data (Recommended)

Start all services with ~90 days of food resource data:

```bash
# Clone and enter directory
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# Setup environment
cp .env.example .env
# Edit .env with your API keys

# Start with database initialization
docker compose -f docker-compose.yml -f docker-compose.with-init.yml --profile with-init up -d

# Monitor progress (5-15 minutes with SQL dumps, 30+ minutes without)
docker compose logs -f db-init

# Access API
open http://localhost:8000/docs
```

**Fast Initialization**: Database initialization uses SQL dumps from HAARRRvest (<5 minutes). If no SQL dumps exist, the database starts empty.

### Option 2: Development Mode

For active development with hot reload and debugging:

```bash
# Start development environment
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Or with pre-populated data
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.with-init.yml --profile with-init up -d
```

See [Docker Development Guide](docker-development.md) for detailed dev setup.

### Option 3: Basic Mode (Empty Database)

Fastest startup, but no initial data:

```bash
# Start core services only
docker compose up -d

# Access API (will be empty)
open http://localhost:8000/docs
```

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| API Docs | http://localhost:8000/docs | Interactive API documentation |
| API | http://localhost:8000 | REST API endpoints |
| RQ Dashboard | http://localhost:9181 | Job queue monitoring |
| Datasette | http://localhost:8001 | Data exploration (after export) |

## Essential Commands

### Service Management

```bash
# View all services
docker compose ps

# View logs
docker compose logs -f [service-name]

# Stop all services
docker compose down

# Stop and remove data
docker compose down -v
```

### Running Scrapers

```bash
# List available scrapers
docker compose exec scraper python -m app.scraper --list

# Run a specific scraper
docker compose exec scraper python -m app.scraper nyc_efap_programs

# Run all scrapers
docker compose exec scraper python -m app.scraper --all
```

### Database Access

```bash
# Connect to database
docker compose exec db psql -U postgres -d pantry_pirate_radio

# Check record count
docker compose exec db psql -U postgres -d pantry_pirate_radio -c "SELECT COUNT(*) FROM organization;"

# Create a SQL dump for fast init
docker compose exec app bash /app/scripts/create-sql-dump.sh
```

## Environment Variables

Required in `.env`:

```bash
# Database (defaults provided)
POSTGRES_PASSWORD=your_secure_password
DATABASE_URL=postgresql://postgres:your_secure_password@db:5432/pantry_pirate_radio

# LLM Provider (choose one)
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your_key  # For Claude

# Or
LLM_PROVIDER=openai
OPENROUTER_API_KEY=your_key  # For OpenAI
```

## Initialization Performance

The system uses SQL dumps for fast initialization when available:

| Method | Time | Description |
|--------|------|-------------|
| SQL Dump | <5 minutes | Restores from compressed PostgreSQL dump |
| Empty Database | Instant | No data to restore |

SQL dumps are automatically created daily by the HAARRRvest publisher service. Without SQL dumps, the database starts empty.

## Troubleshooting

### Services won't start
```bash
# Check Docker is running
docker version

# Check port conflicts
lsof -i :8000  # API port
lsof -i :5432  # Database port
```

### Database initialization slow
- Check if SQL dumps exist: `ls HAARRRvest/sql_dumps/`
- First run downloads HAARRRvest data and may take time
- Subsequent runs use cached data

### Out of memory
```bash
# Increase Docker memory in Docker Desktop settings
# Or scale down workers
docker compose up -d --scale worker=1
```

## Next Steps

- [API Examples](api-examples.md) - Learn to use the API
- [Docker Development](docker-development.md) - Set up development environment
- [Architecture Overview](architecture.md) - Understand the system
- [Troubleshooting Guide](troubleshooting.md) - Solve common issues