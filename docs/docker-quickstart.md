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
./docker.sh up --with-init

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
./docker.sh up --dev

# Or with pre-populated data
./docker.sh up --dev --with-init
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

### Using docker.sh Helper (Recommended)

```bash
# Service management
./docker.sh up                    # Start in dev mode
./docker.sh up --prod            # Start in production mode
./docker.sh up --with-init       # Start with data initialization
./docker.sh down                 # Stop all services
./docker.sh ps                   # View service status
./docker.sh logs app             # View service logs
./docker.sh shell app            # Open shell in container
./docker.sh clean                # Stop and remove volumes

# Running scrapers
./docker.sh scraper --list       # List available scrapers
./docker.sh scraper nyc_efap_programs  # Run specific scraper
./docker.sh scraper --all        # Run all scrapers

# Testing
./docker.sh test                 # Run all CI checks
./docker.sh test --pytest        # Run tests only
./docker.sh test --black         # Format code
./docker.sh test --mypy          # Type checking

# Claude authentication
./docker.sh claude-auth          # Authenticate Claude provider
```

### Using Docker Compose Directly

```bash
# View all services
docker compose ps

# View logs
docker compose logs -f [service-name]

# Stop all services
docker compose down

# Stop and remove data
docker compose down -v

# Running scrapers
docker compose exec scraper python -m app.scraper --list
docker compose exec scraper python -m app.scraper nyc_efap_programs
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

## Programmatic Usage

The docker.sh script supports programmatic mode for automation:

### Flags for Automation
```bash
# Structured output mode
./docker.sh --programmatic COMMAND    # Timestamped logs to stderr
./docker.sh --json COMMAND           # JSON output where supported
./docker.sh --quiet COMMAND          # Suppress non-error output
./docker.sh --no-color COMMAND       # Disable colored output

# Combine flags
./docker.sh --programmatic --quiet up
./docker.sh --json --verbose ps
```

### Non-Interactive Execution
```bash
# Commands run without TTY allocation in programmatic mode
./docker.sh --programmatic exec app python --version
./docker.sh --programmatic scraper --list

# Logs are limited to last 100 lines (no follow)
./docker.sh --programmatic logs app
```

### Exit Codes
- `0` - Success
- `1` - General error or command failure
- Non-zero - Command-specific errors

### Example: Python Automation
```python
import subprocess
import json

# Get service status as JSON
result = subprocess.run(
    ["./docker.sh", "--json", "ps"],
    capture_output=True,
    text=True
)

# Parse each line as JSON (one service per line)
for line in result.stdout.strip().split('\n'):
    service = json.loads(line)
    print(f"{service['Service']}: {service['Status']}")
```

See `examples/docker-automation.py` for a complete automation example.

## Next Steps

- [API Examples](api-examples.md) - Learn to use the API
- [Docker Development](docker-development.md) - Set up development environment
- [Architecture Overview](architecture.md) - Understand the system
- [Troubleshooting Guide](troubleshooting.md) - Solve common issues