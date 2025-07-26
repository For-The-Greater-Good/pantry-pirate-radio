# Getting Started Locally

### Prerequisites and Requirements
• Install Python 3.11 or higher.
• Install [Poetry](https://python-poetry.org/docs/#installation).
• (Optional) Install Docker and Docker Compose.
• (Optional) Ensure PostgreSQL/PostGIS are installed if you don’t use Docker for the database.

### Cloning the Project
```bash
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio
```

### Local Environment Setup
```bash
# Install dependencies
poetry install
poetry shell

# Copy environment template
cp .env.example .env
# Edit .env with your configuration
```

• Configure environment variables in `.env`:
  - Database credentials
  - LLM API keys (OpenRouter or Anthropic)
  - HAARRRvest repository settings (if using publisher)

### Database Configuration

#### Option 1: Docker Compose (Recommended)
```bash
# Start all services including database
docker-compose up -d

# This starts:
# - PostgreSQL with PostGIS
# - Redis
# - All microservices
```

#### Option 2: Local PostgreSQL
```bash
# Install PostgreSQL with PostGIS extension
# Create database and enable PostGIS:
createb pantry_pirate_radio
psql -d pantry_pirate_radio -c "CREATE EXTENSION postgis;"
```

### Running the Application

#### Full Stack with Docker Compose
```bash
# Start all services
docker-compose up -d

# View service status
docker-compose ps

# View logs
docker-compose logs -f app
docker-compose logs -f worker
docker-compose logs -f haarrrvest-publisher
```

#### Individual Services
```bash
# API Server only
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Worker
poetry run rq worker llm

# Recorder
poetry run python -m app.recorder

# Reconciler
poetry run rq worker reconciler

# HAARRRvest Publisher
poetry run python -m app.haarrrvest_publisher.service
```

• Visit http://localhost:8000/docs for the API docs.
• Check worker health at http://localhost:8080/health (Claude provider)
• Monitor job queue at http://localhost:9181 (RQ Dashboard)

### Testing and Linting
```bash
# Run all tests with coverage
poetry run pytest

# Run specific test suites
poetry run pytest tests/test_scraper/
poetry run pytest -m integration

# Code quality checks
poetry run mypy .
poetry run ruff .
poetry run black .
poetry run bandit -r app/

# Run all CI checks
./scripts/run-ci-checks.sh
```

### Working with Scrapers
```bash
# List available scrapers
python -m app.scraper --list

# Run a specific scraper
python -m app.scraper nyc_efap_programs

# Run all scrapers
python -m app.scraper --all
```

### HAARRRvest Publisher Setup
```bash
# Configure in .env:
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_token

# Start the publisher
docker-compose up -d haarrrvest-publisher

# View publisher logs
docker-compose logs -f haarrrvest-publisher

# Manually trigger publishing (restart service)
docker-compose restart haarrrvest-publisher
```

### Troubleshooting / FAQ
• **Port collisions**: Check if something else uses ports 8000, 6379, 5432
• **Database connection errors**: Confirm DB credentials in .env match docker-compose
• **Worker not processing jobs**: Check Redis connection and worker logs
• **HAARRRvest push failures**: Verify GitHub token has repository write access
• **Test failures locally**: Ensure DATABASE_URL is set for test environment

### Devcontainer vs Local Setup
• **Devcontainer**: Everything preconfigured, consistent environment
• **Local setup**: More flexibility but requires manual configuration
• **Recommendation**: Use devcontainer for development, local for debugging
