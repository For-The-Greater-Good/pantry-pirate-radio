
# 🎧 Pantry Pirate Radio
<img width="1024" height="1024" alt="PPR" src="https://github.com/user-attachments/assets/a68bc691-3f20-489a-b756-da1c0dcff082" />

⚠️ WARNING: Licensed under sandia-ftgg-nc-os-1.0 ⚠️

*Breaking down barriers to food security through unified resource access*

[![Build Status](https://github.com/For-The-Greater-Good/pantry-pirate-radio/workflows/CI/badge.svg)](https://github.com/For-The-Greater-Good/pantry-pirate-radio/actions)
[![Test Coverage](https://github.com/For-The-Greater-Good/pantry-pirate-radio/workflows/CI/badge.svg?branch=main)](https://github.com/For-The-Greater-Good/pantry-pirate-radio/actions/workflows/ci.yml)
[![Latest Release](https://img.shields.io/github/v/release/For-The-Greater-Good/pantry-pirate-radio)](https://github.com/For-The-Greater-Good/pantry-pirate-radio/releases)

### Quality Metrics
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Table of Contents

- [Overview](#overview)
- [Core Features](#core-features)
- [System Architecture](#system-architecture)
- [Quick Start](#quick-start)
- [Bouy - Docker Fleet Management](#bouy---docker-fleet-management)
- [LLM Provider Configuration](#llm-provider-configuration)
- [Service URLs](#service-urls-development)
- [Development](#development)
- [HSDS Implementation & Database](#hsds-implementation--database)
- [🔍 Explore the Data](#-explore-the-data)
- [📚 Documentation](#-documentation)
- [Environment Configuration](#environment-configuration)
- [Contributing](#contributing)
- [License](#license)

## Overview

Pantry Pirate Radio is a distributed food security data aggregation system implementing the **OpenReferral Human Services Data Specification (HSDS) v3.1.1**. The system unifies scattered food resource data through AI-powered normalization, intelligent deduplication, and geographic optimization to provide comprehensive, HSDS-compliant food security information.

### Mission
Our mission is to break down information barriers in food security by making public resources truly accessible through intelligent aggregation and standardization.

### Key Benefits
- **HSDS Compliance**: Full compliance with OpenReferral HSDS v3.1.1 specification
- **AI-Powered Processing**: LLM-based data alignment with confidence scoring and validation
- **Geographic Intelligence**: Continental US coverage with PostGIS spatial optimization
- **Distributed Architecture**: Scalable microservices with Redis-based job processing
- **High Quality Standards**: 90% test coverage, strict type checking, comprehensive validation

## Core Features

### Data Aggregation
- Full HSDS v3.1.1 compliance with comprehensive validation
- Real-time and scheduled aggregation of food security resources
- AI-powered data normalization with confidence scoring
- Intelligent deduplication across multiple sources
- Geographic coverage optimization
- Rich metadata and provenance tracking

### Geographic Intelligence
- Continental US coverage (25°N to 49°N, -125°W to -67°W)
- Smart grid generation for large area searches
- PostGIS-optimized spatial queries

- Automatic request partitioning for extensive areas
- Coverage tracking and gap analysis

### AI Integration
- **LLM Providers**: Support for OpenAI and Claude providers
- **HSDS Schema Alignment**: AI-powered data mapping to HSDS v3.1.1 specification
- **Confidence Scoring**: Validation feedback loops with retry logic
- **Authentication Management**: Shared authentication across scaled workers
- **Failsafe System**: Automatic retry with quota management and exponential backoff
- **Structured Output**: Native structured output support for high-quality responses

### Data Processing Pipeline
- Redis-based distributed job processing
- Priority queue with dependency tracking
- Dead letter queue for failed jobs
- Comprehensive job monitoring
- Automatic error recovery
- Resource-aware scaling

### Data Management
- Version-controlled HSDS records
- Automated data reconciliation
- Intelligent entity matching
- Compressed data archiving

### API Features
- **Read-Only Access**: Safe data exploration without modification capabilities
- Complete OpenAPI/Swagger documentation
- Geographic search with radius and bounds support
- Multi-criteria filtering capabilities
- Cursor-based pagination
- Fair use rate limiting
- Response caching with invalidation
- Comprehensive error handling
- HSDS-compliant read endpoints for all entity types

### Monitoring & Metrics
- Prometheus metrics integration
- Worker health monitoring
- Queue performance tracking
- Resource utilization metrics
- Coverage analysis tools
- Error rate monitoring
- Data quality metrics
- Service health dashboards

## System Architecture

Pantry Pirate Radio uses a **distributed microservices architecture** built with containerized services and a consolidated multi-stage Dockerfile for efficient builds and consistent deployment.

### Core Services

```mermaid
flowchart TB
    %% Data Collection
    Scrapers[Scrapers<br/>12+ sources]
    ContentStore{Content Store<br/>Deduplication}

    Scrapers --> ContentStore
    ContentStore -->|New content| Queue[Redis Queue]
    ContentStore -->|Duplicate| Skip[Return existing]

    %% Processing
    Queue --> Workers[LLM Workers]
    Workers <--> LLM[LLM Providers]

    %% Job Distribution
    Workers --> Jobs{Create Jobs}
    Jobs --> ReconcilerQ[Reconciler Queue]
    Jobs --> RecorderQ[Recorder Queue]

    %% Services
    ReconcilerQ --> Reconciler[Reconciler<br/>Location matching]
    RecorderQ --> Recorder[Recorder<br/>Archive JSON]

    %% Storage
    Reconciler --> DB[(PostgreSQL<br/>PostGIS)]
    Recorder --> Files[JSON Files]

    %% Output
    DB --> API[FastAPI]
    DB --> Publisher[HAARRRvest<br/>Publisher]
    Files --> Publisher
    Publisher --> GitHub[HAARRRvest<br/>Repository]

    %% Style
    classDef service fill:#bbdefb,stroke:#1565c0,stroke-width:2px,color:#000
    classDef storage fill:#ffe0b2,stroke:#ef6c00,stroke-width:2px,color:#000
    classDef external fill:#e1bee7,stroke:#6a1b9a,stroke-width:2px,color:#000
    classDef queue fill:#c8e6c9,stroke:#388e3c,stroke-width:2px,color:#000

    class Scrapers,Workers,Reconciler,Recorder,API,Publisher service
    class ContentStore,DB,Files storage
    class LLM,GitHub external
    class Queue,ReconcilerQ,RecorderQ,Skip,Jobs queue
```

### Service Components

#### **Scraper System** (`app/scraper/`)
- **12+ Individual Scrapers**: Each targeting specific food security data sources
- **Base Framework**: `ScraperJob` base class with utilities for geocoding and grid generation
- **Data Sources**: NYC EFAP, FoodHelpline.org, Plentiful, Care & Share, Freshtrak, and more
- **Testing Framework**: Comprehensive validation system for scraper outputs
- **Geographic Coverage**: Continental US with intelligent grid generation for large areas

#### **LLM Processing System** (`app/llm/`)
- **HSDS Aligner**: AI-powered schema alignment to HSDS v3.1.1 specification
- **Multiple Providers**:
  - **OpenAI/OpenRouter**: HTTP API-based provider
  - **Claude**: CLI-based provider with shared authentication across workers
- **Queue Processing**: Redis-based job distribution with confidence scoring
- **Validation Pipeline**: Field coherence validation and hallucination detection
- **Retry Logic**: Intelligent failsafe system with quota management

#### **Reconciler Service** (`app/reconciler/`)
- **Version Tracker**: Maintains complete version history for all records
- **Location Creator**: Handles geographic data and coordinate-based deduplication
- **Organization Creator**: Creates and manages organization entities
- **Service Creator**: Processes service information and relationships
- **Merge Strategy**: Handles source-specific records with canonical merging

#### **Worker Pool** (`app/llm/queue/`)
- **Scalable Processing**: Horizontally scalable worker instances
- **Job Coordination**: Processes jobs in dependency order (organizations → locations → services)
- **Health Monitoring**: Built-in health checks and status reporting
- **Shared Authentication**: Single authentication state across all scaled workers

#### **Recorder Service** (`app/recorder/`)
- **Job Storage**: Saves all job results as JSON files in `outputs/`
- **File Organization**: Structured output in `daily/YYYY-MM-DD/` directories
- **Latest Symlinks**: Maintains `latest/` symlink to most recent daily directory
- **Summary Files**: Creates daily summary files tracking all processed jobs

#### **Database Layer**
- **PostgreSQL**: Primary data store with HSDS-compliant schema
- **PostGIS**: Spatial extensions for geographic queries and indexing
- **Version Control**: Complete version tracking for all records
- **Backup System**: Automated backups with retention policies
- **Spatial Indexing**: Optimized for geographic search and boundary queries

#### **API Layer** (`app/api/`)
- **FastAPI Framework**: High-performance async API server
- **Read-Only HSDS Endpoints**: Safe data access following OpenReferral HSDS v3.1.1 specification
- **Geographic Search**: Radius-based and bounding box search capabilities
- **Pagination**: Cursor-based pagination for large result sets
- **Response Caching**: Geographic tile-based caching for performance

#### **HAARRRvest Publisher** (`app/haarrrvest_publisher/`)
- **Automated Publishing**: Monitors recorder JSON outputs and publishes to HAARRRvest repository
- **File Processing**: Reads from `outputs/daily/` and `outputs/latest/` directories
- **Branch-Based Workflow**: Creates date-based branches with merge commits
- **SQLite Export**: Generates SQLite database for Datasette visualization
- **Git Safety**: Handles repository updates, conflict resolution, and authentication
- **State Tracking**: Remembers processed files to avoid duplicates

## Quick Start

### Platform Considerations

#### macOS Users (Apple Silicon/ARM)
⚠️ **Important**: The PostGIS database image is AMD64-only and requires emulation on Apple Silicon Macs.

**Recommended approach for Mac users:**
- Use `bouy` tool directly for local development (Docker handles PostGIS emulation automatically)
- Use GitHub Codespaces for the full DevContainer experience (with prebuild support for instant startup)
- VSCode DevContainers on Mac may experience slower performance due to emulation

#### Linux/Windows/Intel Mac Users
- Full DevContainer support available
- No platform limitations

#### GitHub Codespaces
- **Recommended for all users** - provides consistent environment with prebuilt images
- Automatic port forwarding for web services
- Use Codespaces Secrets for API keys: Settings → Codespaces → Secrets
- Set secrets: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `DATA_REPO_TOKEN`

### Using DevContainer (Recommended for Linux/Windows/Codespaces)
```bash
# 1. Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. Open in VSCode
code .

# 3. When prompted, select "Reopen in Container"
# DevContainer will handle all setup automatically
```

#### DevContainer with Database Initialization
To start the dev environment with pre-populated data from HAARRRvest:
```bash
# Start dev environment with initialization
./bouy up --dev --with-init

# Monitor initialization progress
docker compose logs -f db-init

# This will populate ~90 days of historical data from HAARRRvest
```

### Using Docker Compose (Fastest)
```bash
# 1. Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. Quick setup with interactive wizard (NEW USERS START HERE!)
./bouy setup                 # Interactive setup wizard - creates .env file
# OR use legacy script:
./scripts/setup-secrets.sh   # Alternative interactive setup
# OR manually:
cp .env.example .env
# Edit .env with your API keys and settings

# 3. Start all services WITH latest HAARRRvest data (recommended)
# This will populate the database with ~90 days of food resource data
./bouy up --with-init

# 4. Monitor initialization (takes 5-15 minutes)
docker compose logs -f db-init
docker compose logs -f haarrrvest-publisher

# 5. Access the API at http://localhost:8000/docs
```

**Startup Process**:
1. PostgreSQL and Redis start first
2. HAARRRvest publisher shallow clones the data repository (depth=1 for efficiency)
3. Database initializer populates ~90 days of historical data
4. All services start once the database is ready

**Note**: The initialization command uses both compose files to ensure proper dependency handling. For subsequent runs, use `docker compose up -d` for faster startup. See [Docker Startup Documentation](docs/docker-startup-sequence.md) for details.

### Manual Setup
```bash
# 1. Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. Setup environment (choose one):
./bouy setup                 # Interactive setup wizard (recommended)
./scripts/setup-secrets.sh   # Alternative interactive setup
# OR manually copy and edit:
cp .env.example .env
# Edit .env with your configuration (API keys, passwords, etc.)

# 3. Enable git hooks for security
git config core.hooksPath .githooks

# 4. Install dependencies
# Dependencies are installed automatically in containers via bouy

# 5. Start all services
docker compose up -d

# FastAPI server will be available at http://localhost:8000
# Workers will start automatically
# Search orchestrator will run scrapers on schedule
```

Visit http://localhost:8000/docs for API documentation

## Bouy - Docker Fleet Management

**Bouy is the primary way to control all Docker stacks and run tests in this project.** All development operations use bouy for consistent, reliable container management.

> **Note**: VSCode DevContainer environments are available for Linux/Windows users and GitHub Codespaces. Mac users should use bouy directly due to PostGIS platform limitations. See [Platform Considerations](#platform-considerations) for details.

### Why Bouy?
- **Single command interface** for all Docker operations
- **Interactive setup wizard** with guided configuration
- **Automatic health checks** and dependency verification
- **Integrated testing** with coverage reporting
- **Built-in authentication management** for LLM providers  
- **Programmatic mode** with JSON output for automation
- **No local dependencies** required except Docker

### Quick Start for New Users
```bash
# NEW USERS: Complete setup in 3 commands
./bouy setup                # Interactive setup wizard (creates .env)
./bouy up                   # Start all services
./bouy test                 # Verify everything works
```

### Essential Commands
```bash
# Initial Setup
./bouy setup                # Interactive setup wizard for .env configuration
./bouy --help               # Show help with all commands
./bouy --version            # Show bouy version

# Service Management
./bouy up                    # Start all services (development mode)
./bouy up --with-init       # Start with database initialization from HAARRRvest
./bouy up --prod            # Start in production mode
./bouy down                 # Stop all services
./bouy ps                   # List running services
./bouy clean                # Stop services and remove volumes

# Logs and Debugging
./bouy logs app             # View service logs
./bouy shell app            # Open shell in container
./bouy exec app python --version  # Execute command in container

# Testing (Primary Development Workflow)
./bouy test                 # Run ALL CI checks (pytest, mypy, black, ruff, bandit)
./bouy test --pytest        # Run tests with coverage
./bouy test --mypy          # Type checking only
./bouy test --black         # Code formatting check
./bouy test --ruff          # Linting only
./bouy test --bandit        # Security scan only
./bouy test --coverage      # Tests with coverage threshold check
./bouy test --vulture       # Dead code detection
./bouy test --safety        # Dependency vulnerability scan
./bouy test --pip-audit     # Pip audit for vulnerabilities
./bouy test --xenon         # Code complexity analysis

# Scraper Operations  
./bouy scraper --list       # List available scrapers
./bouy scraper --all        # Run all scrapers
./bouy scraper nyc_efap_programs  # Run specific scraper
./bouy scraper-test --all   # Test scrapers (dry run)

# Data Management
./bouy reconciler           # Process LLM job results
./bouy recorder            # Save job results to JSON files
./bouy content-store status # Check deduplication system
./bouy content-store report # Generate detailed deduplication report
./bouy datasette            # Export database to SQLite for Datasette
./bouy datasette schedule   # Start periodic SQLite export scheduler
./bouy replay --use-default-output-dir  # Replay recorded JSON files
./bouy haarrrvest          # Publish to HAARRRvest repository

# Authentication (Claude Provider)
./bouy claude-auth         # Interactive Claude authentication
./bouy claude-auth status  # Check authentication status
```

### Advanced Usage

#### Global Flags (All Commands)
```bash
# Output Control
./bouy --help               # Show help
./bouy --version            # Show version
./bouy --programmatic CMD   # Structured output for automation
./bouy --json CMD           # JSON output (implies --programmatic)
./bouy --quiet CMD          # Suppress non-error output
./bouy --verbose CMD        # Enable debug output
./bouy --no-color CMD       # Disable colored output

# Examples
./bouy --json ps            # Get service status as JSON
./bouy --quiet up           # Start services with minimal output
./bouy --no-color logs app  # Plain text logs for files
```

#### Running Specific Tests
```bash
# Test specific files or patterns
./bouy test --pytest tests/test_api.py
./bouy test --pytest -- -k "test_organization"
./bouy test --pytest -- -v    # Verbose output

# Type check specific paths
./bouy test --mypy app/api/
```

#### Service-Specific Operations
```bash
# Start only specific services
./bouy up app worker
./bouy build app            # Build specific service
./bouy logs -f worker       # Follow worker logs
```

### Development Environments

#### Primary: Bouy + Docker
**Recommended for most development tasks**
- No local Python dependencies required
- Consistent environment across all developers
- All commands use bouy for Docker fleet management

#### Alternative: VSCode DevContainer
**Great for integrated IDE experience**
- Full VSCode integration with extensions
- Automatic setup and configuration
- Still uses bouy for all Docker operations
- See [DevContainer Setup](#using-devcontainer-recommended) section

For complete documentation, see **[Bouy Command Reference](BOUY.md)**.

## LLM Provider Configuration

The system supports two LLM providers for HSDS data alignment:

### Claude Provider (Recommended)
```bash
# Set environment variables
export LLM_PROVIDER=claude
export ANTHROPIC_API_KEY=your_api_key_here  # Optional

# Start services
./bouy up

# Setup authentication (interactive)
./bouy claude-auth                   # Recommended: Interactive Claude CLI auth

# Check authentication status
curl http://localhost:8080/health
```

**Features:**
- Native structured output support
- Shared authentication across scaled workers
- Automatic quota management with exponential backoff
- Built-in health monitoring at `http://localhost:8080/health`

### OpenAI/OpenRouter Provider
```bash
# Set environment variables
export LLM_PROVIDER=openai
export OPENROUTER_API_KEY=your_api_key_here
export LLM_MODEL_NAME=gpt-4

# Start services
./bouy up
```

## Service URLs (Development)

| Service | URL | Description |
|---------|-----|-------------|
| **FastAPI API** | http://localhost:8000 | Main API endpoints |
| **API Documentation** | http://localhost:8000/docs | Interactive API docs |
| **Health Check** | http://localhost:8080/health | Worker health status (Claude) |
| **RQ Dashboard** | http://localhost:9181 | Job queue monitoring |
| **Datasette** | http://localhost:8001 | Data exploration |
| **Prometheus Metrics** | http://localhost:8000/metrics | System metrics |

## Development

### Security Configuration

#### API Keys and Secrets
- **Never commit real API keys** to the repository
- Use placeholders in `.env.example`
- For **GitHub Codespaces**: Configure secrets in Settings → Codespaces → Secrets
- For **local development**: Store keys in `.env` file (gitignored)

#### Database Security
- PostgreSQL uses password authentication (not trust mode)
- Default dev password: `devcontainer` (change for production)
- Healthchecks include proper authentication

#### Recommended Secrets Setup
```bash
# For Codespaces, set these as repository secrets:
ANTHROPIC_API_KEY       # For Claude LLM provider
OPENROUTER_API_KEY      # For OpenAI provider
DATA_REPO_TOKEN        # GitHub PAT with repo scope
```

### Prerequisites
- Docker and Docker Compose (v2.0+)
- For local development without Docker:
  - Python 3.11+
  - Poetry
  - PostgreSQL 15+ with PostGIS extension
  - Redis 7.0+

**Note**: All dependencies are containerized. Local installations are only needed if running without Docker.

### Service Management

All service management uses bouy commands as documented in the [Bouy section](#bouy---docker-fleet-management) above.

#### Using Docker Compose Directly
```bash
# Start all services
docker compose up -d

# Start specific service
docker compose up -d app                    # FastAPI server
docker compose up -d worker                 # LLM workers
docker compose up -d recorder               # Recorder service
docker compose up -d reconciler             # Reconciler service
docker compose up -d haarrrvest-publisher   # HAARRRvest publisher
docker compose up -d db-backup              # Database backup service

# View logs
docker compose logs -f app                  # FastAPI logs
docker compose logs -f worker               # Worker logs
docker compose logs -f recorder             # Recorder logs
docker compose logs -f reconciler           # Reconciler logs
docker compose logs -f haarrrvest-publisher # Publisher logs
docker compose logs -f db-backup            # Database backup logs

# Scale workers
docker compose up -d --scale worker=3  # Run 3 worker instances
```

### Development Commands

All development commands use bouy as documented in the [Bouy section](#bouy---docker-fleet-management) above.

#### **Legacy Poetry Commands** (if running locally without Docker)
```bash
# Local testing with poetry (not recommended - use './bouy test' instead)
poetry run pytest                       # Run all tests with coverage
poetry run pytest -m integration        # Integration tests
poetry run pytest -m asyncio           # Async tests
poetry run pytest tests/test_scraper/  # Scraper tests

# Coverage analysis
bash scripts/coverage-report.sh        # Comprehensive coverage
poetry run coverage report --show-missing --sort=Cover

# Code quality checks (local)
poetry run mypy .                       # Type checking
poetry run black .                      # Code formatting
poetry run ruff .                       # Linting
poetry run bandit -r app/               # Security scan
poetry run vulture app/                 # Unused code detection
```

### Quality Standards
- **Test Coverage**: 90% minimum requirement
- **Type Safety**: Strict mypy configuration with comprehensive annotations
- **Code Style**: Black formatting (88 character line length)
- **Linting**: Ruff with security checks (bandit integration)
- **Documentation**: Required for all public functions
- **Security**: Regular security scanning and validation

## HSDS Implementation & Database

### OpenReferral HSDS Compliance
Pantry Pirate Radio implements the complete **OpenReferral Human Services Data Specification (HSDS) v3.1.1**:

- **Complete Schema**: All HSDS entities (Organizations, Services, Locations, Contacts, etc.)
- **Pydantic Models**: Type-safe validation using comprehensive Pydantic models (`app/models/hsds/`)
- **Geographic Extensions**: PostGIS integration for spatial data and queries
- **Relationship Integrity**: Proper foreign key constraints and entity relationships
- **Taxonomy Support**: Service categories, accessibility, and language taxonomies

### Database Architecture
```bash
# PostgreSQL with PostGIS extensions
# Continental US geographic constraints (25°N-49°N, -125°W to -67°W)
# Spatial indexing for optimized geographic queries
# Version tracking for all records
# Source-specific records with canonical merging
```

**Key Features:**
- **Version Control**: Complete audit trail with `version_tracker.py`
- **Spatial Optimization**: PostGIS indexes for radius and bounding box queries
- **Deduplication**: Coordinate-based location matching and intelligent merging
- **Source Records**: Maintains original source data alongside canonical records
- **Automated Backups**: Scheduled backups with configurable retention policies

### Data Pipeline Flow
1. **Scrapers** → Collect raw data → **Content Store** (deduplication check)
2. **Content Store** → New content only → **Redis Queue**
3. **Workers** → Process with LLM → **Database** (source-specific records)
4. **Reconciler** → Create canonical records → **Database** (merged HSDS data)
5. **Recorder** → Archive results → **Compressed archives**
6. **API** → Serve HSDS-compliant data → **Client applications**
7. **HAARRRvest Publisher** → Sync content store → **Durable backup**

## 🔍 Explore the Data

### [**HAARRRvest - Interactive Data Explorer**](https://for-the-greater-good.github.io/HAARRRvest/)

Explore our harvested food resource data directly in your browser! HAARRRvest provides:
- 🌐 Interactive SQL queries via Datasette-Lite
- 📊 Daily updated SQLite database
- 📁 Organized JSON archives
- 🏴‍☠️ No installation required

## 📚 Documentation

See **[Documentation Index](docs/README.md)** for complete navigation through all available documentation.

### Quick Links
- **[Bouy Command Reference](BOUY.md)** - Complete Docker fleet management guide
- **[Quick Start Guide](docs/quickstart.md)** - Get up and running in minutes
- **[Docker Quick Start](docs/docker-quickstart.md)** - Fast setup with Docker
- **[API Examples](docs/api-examples.md)** - Practical API usage examples
- **[Architecture Overview](docs/architecture.md)** - System design and components
- **[Test Environment Setup](docs/test-environment-setup.md)** - ⚠️ Critical: Configure test isolation
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

## Environment Configuration

### Required Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/pantry_pirate_radio
REDIS_URL=redis://localhost:6379/0

# LLM Provider (choose one)
LLM_PROVIDER=claude  # or "openai"

# Claude Provider
ANTHROPIC_API_KEY=your_api_key_here  # Optional - can use interactive auth

# OpenAI Provider
OPENROUTER_API_KEY=your_api_key_here
LLM_MODEL_NAME=gpt-4

# Optional Configuration
OUTPUT_DIR=outputs/                   # Job output directory
BACKUP_KEEP_DAYS=30                  # Database backup retention
CLAUDE_HEALTH_SERVER=true            # Enable health monitoring

# Content Store Configuration (for deduplication)
CONTENT_STORE_PATH=/path/to/store    # Path to content store directory
CONTENT_STORE_ENABLED=true           # Enable/disable content store (default: enabled if path set)
```

### Key Dependencies
- **Python 3.11+**: Core runtime requirement
- **Poetry**: Dependency management and virtual environments
- **Docker & Docker Compose**: Container orchestration
- **PostgreSQL 15+**: Primary database with PostGIS extension
- **Redis 7.0+**: Job queue and caching
- **Node.js**: Required for Claude CLI provider
- **FastAPI**: High-performance async web framework
- **Pydantic**: Data validation and serialization
- **SQLAlchemy**: Database ORM with async support
- **Prometheus**: Metrics collection and monitoring

## Contributing
We welcome contributions! Please read our [contribution guidelines](CONTRIBUTING.md) before submitting pull requests.

## License
This software is released into the public domain. See [LICENSE](LICENSE) for details.

## About FTGG
For The Greater Good (FTGG) specializes in making public resources truly accessible through intelligent aggregation. Learn more at [forthegg.org](https://forthegg.org).

---

**For The Greater Good (FTGG)** | *Making public resources truly accessible through intelligent aggregation*

*Breaking down information barriers in food security through AI-powered data unification and HSDS-compliant APIs.*
