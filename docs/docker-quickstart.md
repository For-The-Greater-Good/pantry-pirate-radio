# Docker Quick Start Guide

Get Pantry Pirate Radio running quickly with Docker and the bouy command-line tool.

## Prerequisites

### Required Software
- **Docker Desktop** (Mac/Windows) or **Docker Engine** (Linux)
  - Mac: Docker Desktop 4.20+ with at least 4GB RAM allocated
  - Windows: Docker Desktop 4.20+ with WSL2 backend recommended
  - Linux: Docker Engine 20.10+ and Docker Compose 2.10+
- **Git** 2.25 or later
- **System Resources**:
  - 4GB+ available RAM (8GB recommended for development)
  - 10GB+ available disk space (20GB recommended for full data)
  - 2+ CPU cores available

## Quick Start Options

### Option 1: Interactive Setup Wizard (Recommended for New Users)

Use the bouy setup wizard for guided configuration:

```bash
# Clone and enter directory
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# Run interactive setup wizard
./bouy setup

# Start with database initialization
./bouy up --with-init

# Monitor progress (5-15 minutes with SQL dumps)
./bouy logs -f db-init

# Access API
open http://localhost:8000/docs
```

The setup wizard will:
- Check Docker installation and version
- Create `.env` file with secure defaults
- Configure LLM provider (Claude or OpenAI)
- Set up HAARRRvest repository access
- Create backups of existing configurations

### Option 2: Production Mode with Data

Start all services with ~90 days of food resource data:

```bash
# Start production services with data
./bouy up --prod --with-init

# Monitor progress
./bouy logs -f db-init

# Access API
open http://localhost:8000/docs
```

**Fast Initialization**: Database initialization uses SQL dumps from HAARRRvest (<5 minutes). If no SQL dumps exist, the database starts empty.

### Option 3: Development Mode

For active development with hot reload and debugging:

```bash
# Start development environment (default mode)
./bouy up

# Or explicitly specify dev mode
./bouy up --dev

# With pre-populated data
./bouy up --dev --with-init
```

Development mode features:
- Hot reload on code changes
- Debug logging enabled
- Volume mounts for live code editing
- Development dependencies included

See [Docker Development Guide](docker-development.md) for detailed dev setup.

### Option 4: Basic Mode (Empty Database)

Fastest startup, but no initial data:

```bash
# Start core services only (development mode is default)
./bouy up

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

### Using bouy (All Docker operations go through bouy)

```bash
# Initial Setup
./bouy setup                 # Interactive setup wizard
./bouy --help               # Show all available commands
./bouy --version            # Show bouy version

# Service management
./bouy up                    # Start in dev mode (default)
./bouy up --prod            # Start in production mode
./bouy up --with-init       # Start with data initialization
./bouy down                 # Stop all services
./bouy ps                   # View service status
./bouy logs app             # View service logs
./bouy logs -f worker       # Follow worker logs in real-time
./bouy shell app            # Open shell in container
./bouy exec app CMD         # Execute command in container
./bouy clean                # Stop and remove volumes
./bouy build                # Build all services
./bouy build app            # Build specific service
./bouy pull                 # Pull latest images
./bouy pull v1.2.3          # Pull specific version

# Running scrapers
./bouy scraper --list       # List available scrapers
./bouy scraper nyc_efap_programs  # Run specific scraper
./bouy scraper --all        # Run all scrapers
./bouy scraper scouting-party  # Run all scrapers in parallel
./bouy scraper-test NAME    # Test scraper (dry run)

# Testing
./bouy test                 # Run all CI checks
./bouy test --pytest        # Run tests only
./bouy test --black         # Format code
./bouy test --mypy          # Type checking
./bouy test --ruff          # Linting
./bouy test --bandit        # Security scan
./bouy test --coverage      # Tests with coverage check
./bouy test --vulture       # Dead code detection
./bouy test --safety        # Dependency vulnerability scan
./bouy test --pip-audit     # Pip audit for vulnerabilities
./bouy test --xenon         # Code complexity analysis

# Claude authentication
./bouy claude-auth          # Authenticate Claude provider
```

### Global Flags (Work with All Commands)

```bash
# Output control flags
./bouy --programmatic CMD   # Structured output for CI/CD
./bouy --json CMD          # JSON output (implies --programmatic)
./bouy --quiet CMD         # Minimal output
./bouy --verbose CMD       # Debug output
./bouy --no-color CMD      # No color codes

# Examples
./bouy --json ps           # Get service status as JSON
./bouy --quiet up          # Start with minimal output
./bouy --verbose test      # Run tests with debug output
./bouy --programmatic --quiet test  # CI-friendly test run

# Follow logs for multiple services
./bouy logs -f app worker

# Execute commands in containers
./bouy exec app python --version
./bouy exec db pg_isready

# Programmatic mode for CI/CD
./bouy --programmatic --quiet test
./bouy --programmatic scraper --all
```

### Database Access

```bash
# Connect to database
./bouy exec db psql -U postgres -d pantry_pirate_radio

# Check record count
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT COUNT(*) FROM organization;"

# Create a SQL dump for fast init
./bouy exec app bash /app/scripts/create-sql-dump.sh
```

## Environment Variables

### Using the Setup Wizard (Recommended)

```bash
# Run interactive setup to configure all variables
./bouy setup
```

### Manual Configuration

Create `.env` file with these variables:

```bash
# Database (secure defaults provided by setup wizard)
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=pantry_pirate_radio
DATABASE_URL=postgresql://postgres:your_secure_password@db:5432/pantry_pirate_radio
DATABASE_URL_SYNC=postgresql+psycopg2://postgres:your_secure_password@db:5432/pantry_pirate_radio

# Redis Cache
REDIS_URL=redis://cache:6379/0

# LLM Provider (choose one)
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your_key  # Optional - can use CLI auth

# Or OpenAI
LLM_PROVIDER=openai
OPENROUTER_API_KEY=your_key  # Required for OpenAI
LLM_MODEL_NAME=gpt-4

# HAARRRvest Repository (optional)
DATA_REPO_TOKEN=your_github_pat
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git

# Geocoding (optional)
GEOCODING_PROVIDER=arcgis
ARCGIS_API_KEY=your_key  # Optional for higher limits
```

## Initialization Performance

The system uses SQL dumps for fast initialization when available:

| Method | Time | Description |
|--------|------|-------------|
| SQL Dump | <5 minutes | Restores from compressed PostgreSQL dump |
| Empty Database | Instant | No data to restore |

SQL dumps are automatically created daily by the HAARRRvest publisher service. Without SQL dumps, the database starts empty.

## Docker Configuration

### Docker Desktop Settings

#### macOS
1. Open Docker Desktop → Settings → Resources
2. Set Memory: 4GB minimum (8GB recommended)
3. Set CPUs: 2 minimum (4 recommended)
4. Set Disk: 10GB minimum (20GB recommended)
5. Apply & Restart

#### Windows (WSL2)
1. Open Docker Desktop → Settings → Resources → WSL Integration
2. Enable integration with your WSL2 distro
3. Set Memory: 4GB minimum (8GB recommended)
4. Set CPUs: 2 minimum (4 recommended)
5. Apply & Restart

#### Linux
No Docker Desktop required. Ensure Docker daemon has sufficient resources:
```bash
# Check Docker system info
docker system info

# Check available resources
free -h  # Memory
nproc    # CPU cores
df -h    # Disk space
```

### Docker Compose Files

The system uses Docker Compose files located in `.docker/compose/`:
- `base.yml` - Core service definitions
- `docker-compose.dev.yml` - Development overrides
- `docker-compose.prod.yml` - Production configuration
- `docker-compose.with-init.yml` - Database initialization
- `docker-compose.test.yml` - Test environment

The bouy script automatically selects the appropriate files based on your commands.

## Troubleshooting

### Services won't start
```bash
# Check Docker is running
docker version

# If Docker not running:
# macOS/Windows: Start Docker Desktop
# Linux: sudo systemctl start docker

# Check port conflicts
lsof -i :8000  # API port
lsof -i :5432  # Database port
lsof -i :6379  # Redis port
lsof -i :9181  # RQ Dashboard port

# View detailed error logs
./bouy --verbose up
```

### Database initialization slow or failing
```bash
# Check if SQL dumps exist
ls HAARRRvest/sql_dumps/

# Monitor initialization progress
./bouy logs -f db-init

# Check disk space
df -h

# If initialization fails, try without data
./bouy down
./bouy clean
./bouy up  # Start without --with-init
```

### Out of memory errors
```bash
# Check current Docker memory allocation
docker system info | grep -i memory

# Increase Docker memory in Docker Desktop settings
# Or scale down workers
./bouy up --scale worker=1

# Or use production mode (more optimized)
./bouy up --prod
```

### Container build failures
```bash
# Clean Docker build cache
docker system prune -a

# Rebuild without cache
./bouy build --no-cache

# Check Docker disk space
docker system df
```

### Permission issues (Linux)
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, then verify
groups | grep docker
```

## Development vs Production Modes

### Development Mode (Default)
```bash
./bouy up         # Starts in dev mode by default
./bouy up --dev   # Explicitly specify dev mode
```

Features:
- Hot reload enabled
- Debug logging
- Volume mounts for code editing
- Development tools included
- Resource limits relaxed

### Production Mode
```bash
./bouy up --prod
```

Features:
- Optimized for performance
- Production logging levels
- No volume mounts
- Security hardening
- Resource limits enforced

## Resource Optimization

### Memory Management
```bash
# Check current memory usage
docker stats --no-stream

# Limit worker memory
./bouy up --scale worker=1

# Use production mode (more efficient)
./bouy up --prod
```

### Disk Space Management
```bash
# Check Docker disk usage
docker system df

# Clean unused resources
docker system prune -a --volumes

# Remove old bouy data
./bouy clean
```

### CPU Optimization
```bash
# Limit worker CPU usage
# Edit .docker/compose/docker-compose.dev.yml
# Adjust deploy.resources.limits.cpus
```

## Programmatic Usage

The bouy script supports programmatic mode for automation:

### Flags for Automation
```bash
# Structured output mode
./bouy --programmatic COMMAND    # Timestamped logs to stderr
./bouy --json COMMAND           # JSON output where supported
./bouy --quiet COMMAND          # Suppress non-error output
./bouy --no-color COMMAND       # Disable colored output
./bouy --verbose COMMAND        # Debug output

# Combine flags
./bouy --programmatic --quiet up
./bouy --json --verbose ps
```

### Non-Interactive Execution
```bash
# Commands run without TTY allocation in programmatic mode
./bouy --programmatic exec app python --version
./bouy --programmatic scraper --list

# Logs are limited to last 100 lines (no follow)
./bouy --programmatic logs app
```

### Exit Codes
- `0` - Success
- `1` - General error or command failure
- `2` - Docker not installed or not running
- `3` - Configuration error
- Non-zero - Command-specific errors

### CI/CD Integration Examples

#### GitHub Actions
```yaml
- name: Setup and Test
  run: |
    ./bouy setup --non-interactive
    ./bouy --programmatic --quiet test
```

#### Jenkins Pipeline
```groovy
stage('Test') {
    steps {
        sh './bouy --programmatic --quiet test'
    }
}
```

#### GitLab CI
```yaml
test:
  script:
    - ./bouy --programmatic --quiet test
```

### Python Automation Example
```python
import subprocess
import json

# Get service status as JSON
result = subprocess.run(
    ["./bouy", "--json", "ps"],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    # Parse each line as JSON (one service per line)
    for line in result.stdout.strip().split('\n'):
        if line:
            service = json.loads(line)
            print(f"{service['Service']}: {service['Status']}")
else:
    print(f"Error: {result.stderr}")
```

See `examples/docker-automation.py` for a complete automation example.

## Platform-Specific Notes

### macOS
- Use Docker Desktop with at least 4GB RAM allocated
- Enable "Use Rosetta for x86/amd64 emulation" on Apple Silicon
- File sharing performance is best with :cached volume mounts

### Windows
- WSL2 backend strongly recommended over Hyper-V
- Store code in WSL2 filesystem for better performance
- Use Windows Terminal for better command-line experience

### Linux
- No Docker Desktop needed - use native Docker Engine
- Ensure user is in docker group to avoid sudo
- Use overlay2 storage driver for best performance

## Verification Steps

After setup, verify everything works:

```bash
# 1. Check all services are running
./bouy ps

# 2. Test API health endpoint
curl http://localhost:8000/health

# 3. Run basic tests
./bouy test --pytest tests/test_api.py::test_health_check

# 4. Try a scraper
./bouy scraper-test sample_scraper

# 5. Check logs for errors
./bouy logs app | grep -i error
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Main getting started guide
- [API Examples](api-examples.md) - Learn to use the API
- [Docker Development](docker-development.md) - Set up development environment
- [Architecture Overview](architecture.md) - Understand the system
- [Troubleshooting Guide](troubleshooting.md) - Solve common issues
- [CLAUDE.md](../CLAUDE.md) - Development guidelines and bouy commands