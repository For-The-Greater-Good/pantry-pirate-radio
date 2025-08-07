# Getting Started Locally (Advanced Users Only)

> **IMPORTANT**: Docker with the `bouy` command is the **strongly recommended** approach for development. This local setup guide is for advanced users who specifically need to run the application without Docker. For most users, please see [Docker Quickstart](docker-quickstart.md) instead.

## Why Docker/Bouy is Recommended

- **Zero dependency issues**: All dependencies are containerized
- **Consistent environment**: Same setup across all developers
- **Simplified commands**: Single `./bouy` interface for everything
- **No version conflicts**: Python, PostgreSQL, Redis versions are managed
- **Easier troubleshooting**: Known, reproducible environment

**To use Docker (recommended):**
```bash
./bouy setup    # Interactive setup wizard
./bouy up       # Start all services
./bouy test     # Run all tests
```

## Prerequisites for Local Development

If you must run locally without Docker, you'll need:

### Required Software Versions
- **Python 3.11 or 3.12** (verify with `python --version`)
- **Poetry 1.7.0+** for dependency management
- **PostgreSQL 15+** with PostGIS 3.3+ extension
- **Redis 7+** for caching and job queues
- **Git** for version control
- **Make** (optional, for some scripts)

### System Dependencies (OS-specific)

#### Ubuntu/Debian
```bash
# Update package list
sudo apt update

# Python and build tools
sudo apt install python3.11 python3.11-dev python3-pip build-essential

# PostgreSQL with PostGIS
sudo apt install postgresql-15 postgresql-15-postgis-3 postgresql-client-15

# Redis
sudo apt install redis-server

# Additional dependencies
sudo apt install libpq-dev gdal-bin libgdal-dev
```

#### macOS (with Homebrew)
```bash
# Python
brew install python@3.11

# PostgreSQL with PostGIS
brew install postgresql@15 postgis

# Redis
brew install redis

# Additional dependencies
brew install gdal
```

#### Windows (WSL2 recommended)
Use WSL2 with Ubuntu and follow the Ubuntu instructions above. Native Windows development is not officially supported.

## Installation Steps

### 1. Clone the Repository
```bash
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio
```

### 2. Install Poetry
```bash
# Official installer (recommended)
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH (adjust for your shell)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify installation
poetry --version
```

### 3. Install Python Dependencies
```bash
# Install all dependencies including dev tools
poetry install

# Activate the virtual environment
poetry shell
```

### 4. PostgreSQL Setup

#### Start PostgreSQL Service
```bash
# Ubuntu/Debian
sudo systemctl start postgresql
sudo systemctl enable postgresql

# macOS
brew services start postgresql@15
```

#### Create Database and User
```bash
# Switch to postgres user
sudo -u postgres psql

# In psql prompt:
CREATE USER pantry_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE pantry_pirate_radio OWNER pantry_user;
\c pantry_pirate_radio
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
\q

# For test database
sudo -u postgres psql
CREATE DATABASE test_pantry_pirate_radio OWNER pantry_user;
\c test_pantry_pirate_radio
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
\q
```

#### Initialize Database Schema
```bash
# Run initialization scripts
for script in init-scripts/*.sql; do
    psql -U pantry_user -d pantry_pirate_radio -f "$script"
done
```

### 5. Redis Setup

#### Start Redis Service
```bash
# Ubuntu/Debian
sudo systemctl start redis-server
sudo systemctl enable redis-server

# macOS
brew services start redis

# Verify Redis is running
redis-cli ping  # Should return PONG
```

### 6. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your local settings
# CRITICAL: Update these for local development
```

**Key environment variables for local setup:**

```bash
# Database - Use localhost instead of container names
DATABASE_URL=postgresql+psycopg2://pantry_user:your_secure_password@localhost:5432/pantry_pirate_radio
TEST_DATABASE_URL=postgresql+psycopg2://pantry_user:your_secure_password@localhost:5432/test_pantry_pirate_radio

# Redis - Use localhost
REDIS_URL=redis://localhost:6379/0
TEST_REDIS_URL=redis://localhost:6379/1

# PostgreSQL settings (for some tools)
POSTGRES_USER=pantry_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=pantry_pirate_radio
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Python path (important for imports)
PYTHONPATH=.

# LLM Configuration (choose one provider)
LLM_PROVIDER=openai  # or 'claude'

# For OpenAI/OpenRouter
OPENROUTER_API_KEY=your_api_key_here
API_BASE_URL=https://openrouter.ai/api/v1

# For Claude
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Geocoding Service Configuration
GEOCODING_PROVIDER=arcgis  # or 'nominatim'
GEOCODING_CACHE_TTL=2592000  # 30 days
GEOCODING_RATE_LIMIT=0.5  # seconds between requests

# Optional: ArcGIS API key for higher limits
# ARCGIS_API_KEY=your_arcgis_api_key

# HAARRRvest Configuration
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_PATH=./data-repo
DATA_REPO_TOKEN=your_github_token  # Required for HTTPS

# Output paths
OUTPUT_DIR=./outputs
CONTENT_STORE_PATH=./content_store
```

### 7. Geocoding Service Setup

The application uses a unified geocoding service that supports multiple providers:

#### ArcGIS (Default - Free Tier)
- No API key required for 20K geocodes/month
- With API key: 1M geocodes/month
- Get API key from [ArcGIS Developers](https://developers.arcgis.com/api-keys/)

#### Nominatim (Alternative)
- Free, no API key required
- Must respect 1 request/second rate limit
- Configure user agent in `.env`:
```bash
NOMINATIM_USER_AGENT=pantry-pirate-radio-dev
NOMINATIM_RATE_LIMIT=1.1
```

## Running the Application

### Start Individual Services

```bash
# API Server
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# LLM Worker (in new terminal)
poetry run python -m app.llm.queue.worker

# Reconciler Worker (in new terminal)
poetry run python -m app.reconciler

# Recorder Service (in new terminal)
poetry run python -m app.recorder

# HAARRRvest Publisher (in new terminal)
poetry run python -m app.haarrrvest_publisher.service

# RQ Dashboard (optional, for monitoring)
poetry run rq-dashboard --redis-url redis://localhost:6379/0
```

### Verify Services
- API Documentation: http://localhost:8000/docs
- API Health: http://localhost:8000/health
- RQ Dashboard: http://localhost:9181

## Running Tests Locally

### All Tests with Coverage
```bash
# Run all tests
poetry run pytest

# With coverage report
poetry run pytest --cov=app --cov-report=html --cov-report=term

# View coverage report
open htmlcov/index.html
```

### Specific Test Categories
```bash
# Unit tests only
poetry run pytest tests/ -m "not integration"

# Integration tests
poetry run pytest tests/ -m integration

# Specific test file
poetry run pytest tests/test_api_endpoints_unit.py

# With verbose output
poetry run pytest -v

# Stop on first failure
poetry run pytest -x
```

### Code Quality Checks
```bash
# Type checking
poetry run mypy app tests

# Code formatting (auto-fix)
poetry run black app tests

# Linting
poetry run ruff check app tests

# Security scanning
poetry run bandit -r app/

# All checks (similar to CI)
./scripts/run-ci-checks.sh
```

## Working with Scrapers Locally

```bash
# List available scrapers
poetry run python -m app.scraper --list

# Run specific scraper
poetry run python -m app.scraper nyc_efap_programs

# Test scraper (dry run)
poetry run python -m app.scraper --test nyc_efap_programs

# Run all scrapers
poetry run python -m app.scraper --all
```

## Common Local Setup Issues

### PostgreSQL Connection Errors
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql  # Linux
brew services list | grep postgresql  # macOS

# Verify connection
psql -U pantry_user -d pantry_pirate_radio -c "SELECT version();"

# Common fixes:
# 1. Check pg_hba.conf allows local connections
# 2. Ensure PostgreSQL is listening on localhost
# 3. Verify credentials in .env match database
```

### PostGIS Extension Missing
```bash
# Install PostGIS if missing
sudo apt install postgresql-15-postgis-3  # Ubuntu
brew install postgis  # macOS

# Enable in database
psql -U pantry_user -d pantry_pirate_radio -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

### Redis Connection Issues
```bash
# Check Redis is running
redis-cli ping

# If not running, start it:
sudo systemctl start redis-server  # Linux
brew services start redis  # macOS

# Test connection with Python
poetry run python -c "import redis; r = redis.from_url('redis://localhost:6379/0'); print(r.ping())"
```

### Python Import Errors
```bash
# Ensure you're in Poetry shell
poetry shell

# Set PYTHONPATH
export PYTHONPATH=.

# Verify imports work
poetry run python -c "from app.main import app; print('Imports OK')"
```

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill the process or use different port
poetry run uvicorn app.main:app --port 8001
```

### Geocoding Service Errors
```bash
# Test geocoding locally
poetry run python -c "
from app.core.geocoding import GeocodingService
service = GeocodingService()
result = service.geocode('New York, NY')
print(f'Geocoded: {result}')
"

# Common issues:
# 1. Rate limiting - increase GEOCODING_RATE_LIMIT
# 2. No Redis - geocoding will work but without caching
# 3. Invalid API key - remove ARCGIS_API_KEY to use free tier
```

### Database Migration Issues
```bash
# Reset database (CAUTION: destroys all data)
psql -U pantry_user -c "DROP DATABASE IF EXISTS pantry_pirate_radio;"
psql -U pantry_user -c "CREATE DATABASE pantry_pirate_radio;"

# Re-run initialization
for script in init-scripts/*.sql; do
    psql -U pantry_user -d pantry_pirate_radio -f "$script"
done
```

## Performance Optimization for Local Development

### PostgreSQL Tuning
Edit `postgresql.conf`:
```conf
# For development (not production!)
shared_buffers = 256MB
work_mem = 4MB
maintenance_work_mem = 64MB
effective_cache_size = 1GB
```

### Redis Configuration
Edit `redis.conf`:
```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

### Python Optimization
```bash
# Use multiple workers for better performance
poetry run gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker

# Enable Python optimizations
export PYTHONOPTIMIZE=1
```

## Switching Between Local and Docker

If you need to switch between local and Docker development:

### From Local to Docker
```bash
# Stop all local services
pkill -f uvicorn
pkill -f "python -m app"
sudo systemctl stop postgresql redis-server

# Clean local data (optional)
rm -rf outputs/ data-repo/ content_store/

# Start with Docker
./bouy up
```

### From Docker to Local
```bash
# Stop Docker services
./bouy down

# Start local services
sudo systemctl start postgresql redis-server
poetry shell
# Follow "Running the Application" section above
```

## When to Use Local Development

Local development without Docker should only be used when:

1. **Debugging system-level issues** that require direct access to processes
2. **Developing with IDE integrations** that don't work well with containers
3. **Performance profiling** requiring native execution
4. **Contributing to geocoding providers** or other external integrations
5. **Working on platform-specific features** (though this is discouraged)

## Getting Help

If you encounter issues with local setup:

1. **First, try Docker**: `./bouy setup && ./bouy up`
2. Check [Troubleshooting Guide](troubleshooting.md)
3. Search existing [GitHub Issues](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
4. Ask in discussions with full error messages and environment details

Remember: The development team primarily supports Docker-based development. Local setup issues may have limited support.