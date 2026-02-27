
# 🎧 Pantry Pirate Radio
<img width="1024" height="1024" alt="PPR" src="https://github.com/user-attachments/assets/a68bc691-3f20-489a-b756-da1c0dcff082" />

⚠️ WARNING: Licensed under sandia-ftgg-nc-os-1.0 ⚠️

> **🚧 Please pardon our dust while we cleanup some aggressive refactoring and get the CI passing again**

*Breaking down barriers to food security through unified resource access*

[![Build Status](https://github.com/For-The-Greater-Good/pantry-pirate-radio/workflows/CI/badge.svg)](https://github.com/For-The-Greater-Good/pantry-pirate-radio/actions)
[![Test Coverage](https://github.com/For-The-Greater-Good/pantry-pirate-radio/workflows/CI/badge.svg?branch=main)](https://github.com/For-The-Greater-Good/pantry-pirate-radio/actions/workflows/ci.yml)
[![Latest Release](https://img.shields.io/github/v/release/For-The-Greater-Good/pantry-pirate-radio)](https://github.com/For-The-Greater-Good/pantry-pirate-radio/releases)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/get-started)
[![Bouy](https://img.shields.io/badge/bouy-v1.0.0-green.svg)](BOUY.md)
[![License](https://img.shields.io/badge/license-sandia--ftgg--nc--os--1.0-yellow.svg)](LICENSE)

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
- [Testing](#testing)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [Community and Support](#community-and-support)

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
- **Unified Geocoding Service**: Multi-provider with intelligent fallback (ArcGIS, Google Maps, Nominatim, Census)
- **0,0 Coordinate Detection**: Automatic detection and correction of invalid coordinates
- **State Boundary Verification**: Validates coordinates against US state boundaries
- **Exhaustive Provider Fallback**: Tries all available providers before accepting failure
- **Intelligent Caching**: TTL-based caching with rate limiting for geocoding requests
- Automatic request partitioning for extensive areas
- Coverage tracking and gap analysis

### AI Integration
- **LLM Providers**: Support for OpenAI and Claude providers
- **HSDS Schema Alignment**: AI-powered data mapping to HSDS v3.1.1 specification
- **Confidence Scoring**: Validation feedback loops with retry logic
- **Authentication Management**: Shared authentication across scaled workers
- **Failsafe System**: Automatic retry with quota management and exponential backoff
- **Structured Output**: Native structured output support for high-quality responses

### Data Validation & Quality Assurance
- **Confidence Scoring**: 0-100 scale for all location data quality assessment
- **Automated Data Enrichment**: Enhances incomplete data using geocoding and field validation
- **Validation Rules**: Rejects low-quality data (test addresses, placeholder names)
- **Redis-Based Validation**: Distributed validation service with caching for performance
- **Quality Thresholds**: Configurable rejection threshold (default: 30) for automatic data filtering
- **Field Coherence**: Validates relationships between fields (e.g., city/state/ZIP alignment)

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

Pantry Pirate Radio uses a **distributed microservices architecture** built with containerized services managed through Docker Compose orchestration. All services are defined in `.docker/compose/` with environment-specific configurations.

### Core Services

The system consists of the following containerized services:
- **app**: FastAPI server providing HSDS-compliant API endpoints
- **worker**: LLM processing workers (scalable)
- **reconciler**: Data reconciliation and deduplication service
- **recorder**: Job result archival service
- **haarrrvest-publisher**: GitHub repository synchronization
- **db**: PostgreSQL with PostGIS extensions
- **cache**: Redis for job queues and caching

```mermaid
flowchart TB
    %% Data Collection
    Scrapers[Scrapers<br/>70+ Food Banks<br/>Aggregator Platforms]
    ContentStore[(Content Store)]

    Scrapers --> ContentStore
    ContentStore -->|new| Queue[Redis Queue]
    ContentStore -.->|duplicate| Skip[Skip]
    
    %% Processing
    Queue --> Workers[LLM Workers]
    Workers <--> LLM[LLM Providers]
    Workers --> Validator[Validator]
    
    %% Job Distribution
    Validator --> Jobs{Job Router}
    Jobs --> ReconcilerQ[Reconciler Queue]
    Jobs --> RecorderQ[Recorder Queue]
    
    %% Services
    ReconcilerQ --> Reconciler[Reconciler<br/>Locations]
    RecorderQ --> Recorder[Recorder<br/>Archive]
    
    %% Storage
    Reconciler --> DB[(PostgreSQL)]
    Recorder --> Files[(JSON Files)]
    
    %% Output
    DB --> API[FastAPI]
    DB --> Publisher[Publisher]
    Files --> Publisher
    Publisher --> GitHub[GitHub]
    
    %% Minimal styling
    classDef service fill:#f8f9fa,stroke:#495057,stroke-width:1px
    classDef storage fill:#fff8dc,stroke:#795548,stroke-width:2px
    classDef external fill:#f0f0f0,stroke:#666,stroke-width:1px,stroke-dasharray: 5 5
    classDef queue fill:#e8f4f8,stroke:#0288d1,stroke-width:1px
    
    class Scrapers,Workers,Validator,Reconciler,Recorder,API,Publisher service
    class ContentStore,DB,Files storage
    class LLM,GitHub external
    class Queue,ReconcilerQ,RecorderQ,Jobs queue
    class Skip queue
```

### Service Components

#### **Scraper System** (`app/scraper/`)
- **90+ Individual Scrapers** (Private Submodule): Production scrapers in `app/scraper/scrapers/`
  - Requires access to private repository
  - **Data Aggregator Platforms**: Multiple nationwide food finder platforms and regional aggregators
  - **Food Bank Coverage by State**:
    - **Alabama**: Feeding the Gulf Coast, Heart of Alabama Food Bank
    - **Alaska & Hawaii**: Hawaii Food Bank, Maui Food Bank, The Food Basket Inc.
    - **California**: Central California Food Bank, Community Action of Napa Valley Food Bank, Community Action Partnership of Kern, Find Food Bank, Food Bank of Contra Costa and Solano, Second Harvest of Silicon Valley, SF-Marin Food Bank
    - **Connecticut**: Connecticut Foodshare
    - **Delaware**: Food Bank of Delaware
    - **District of Columbia**: Capital Area Food Bank
    - **Florida**: Second Harvest Food Bank of Central Florida, Feeding Tampa Bay, Treasure Coast Food Bank
    - **Idaho**: The Idaho Foodbank
    - **Kansas**: Kansas Food Bank
    - **Kentucky**: Dare to Care Food Bank, Feeding America Kentucky's Heartland, God's Pantry Food Bank, Purchase Area Development District Food Bank
    - **Louisiana**: Second Harvest Food Bank (multiple regions)
    - **Maine**: Good Shepherd Food Bank
    - **Maryland**: Maryland Food Bank
    - **Massachusetts**: Food Bank of Western Massachusetts
    - **Michigan**: Feeding America West Michigan
    - **Minnesota**: North Country Food Bank
    - **Mississippi**: Mississippi Food Network
    - **Missouri**: Food Bank for Central & Northeast Missouri, Food Bank for the Heartland, Harvesters - The Community Food Network, Ozarks Food Harvest, Second Harvest Community Food Bank, Southeast Missouri Food Bank
    - **Montana**: Montana Food Bank Network
    - **Nebraska**: Food Bank for the Heartland, Food Bank of Lincoln
    - **Nevada**: Food Bank of Northern Nevada, Three Square Food Bank
    - **New Jersey**: Community Foodbank of New Jersey
    - **New York**: Feed More Western New York, Food Bank for New York City, Food Bank of Central New York, Foodlink, Island Harvest, Long Island Cares
    - **North Carolina**: Second Harvest Food Bank of Metrolina, Second Harvest Food Bank of Northwest North Carolina
    - **North Dakota**: Great Plains Food Bank
    - **Ohio**: Akron-Canton Regional Foodbank, Freestore Foodbank, Greater Cleveland Food Bank, Toledo Northwestern Ohio Food Bank
    - **Oregon**: Oregon Food Bank
    - **Pennsylvania**: Chester County Food Bank, Greater Pittsburgh Community Food Bank, Philabundance, Second Harvest Food Bank of Lehigh Valley and Northeast Pennsylvania
    - **Puerto Rico**: Banco de Alimentos de Puerto Rico
    - **Rhode Island**: Rhode Island Community Food Bank
    - **South Carolina**: Harvest Hope Food Bank
    - **South Dakota**: Feeding South Dakota
    - **Tennessee**: Second Harvest Food Bank of East Tennessee, Second Harvest Food Bank of Middle Tennessee
    - **Texas**: El Pasoans Fighting Hunger, West Texas Food Bank
    - **Virginia**: Blue Ridge Area Food Bank, Feed More, Feeding Southwest Virginia, Foodbank of Southeastern Virginia and Eastern Shore, Healthy Harvest Food Bank
    - **Washington**: Food Lifeline, Second Harvest Inland Northwest
    - **West Virginia**: Mountaineer Food Bank
    - **Wisconsin**: Feed My People Food Bank, Feeding America Eastern Wisconsin, Second Harvest Foodbank of Southern Wisconsin
- **Public Framework**: `ScraperJob` base class with utilities for geocoding and grid generation
  - Available to all contributors
  - Includes sample scraper implementation
- **Testing Framework**: Comprehensive validation system for scraper outputs
- **Geographic Coverage**: Continental US with intelligent grid generation for large areas
- **Unified Geocoding**: Integrated with multi-provider geocoding service for accurate location data

#### **LLM Processing System** (`app/llm/`)
- **HSDS Aligner**: AI-powered schema alignment to HSDS v3.1.1 specification
- **Multiple Providers**:
  - **OpenAI/OpenRouter**: HTTP API-based provider with structured output support
  - **Claude**: CLI-based provider with shared authentication across workers
- **Queue Processing**: Redis-based job distribution with confidence scoring
- **Validation Pipeline**: Field coherence validation and hallucination detection
- **Retry Logic**: Intelligent failsafe system with quota management
- **Structured Output**: Native support for JSON schema validation

#### **Data Validation Pipeline** (`app/validator/`)
- **Confidence Scoring**: Evaluates data quality on a 0-100 scale based on field completeness and accuracy
- **Data Enrichment**: 
  - Enhances incomplete location data using multi-provider geocoding (ArcGIS → Nominatim → Census)
  - Corrects invalid coordinates (0,0 detection and US bounds validation)
  - Fills missing postal codes and normalizes addresses
- **Quality Control Rules**:
  - Rejects test/placeholder data (e.g., "123 Test St", "Example Organization")
  - Validates coordinates are within US boundaries (including Alaska and Hawaii)
  - Verifies state/coordinate consistency
  - Detects and flags suspicious patterns
- **Redis-Based Caching**: 
  - SHA256-hashed cache keys with configurable TTL (default: 24 hours)
  - Circuit breaker pattern for geocoding provider failures
  - Distributed caching for horizontal scalability
- **Configurable Thresholds**: 
  - Rejection threshold for low-confidence data (default: score < 10)
  - Per-rule enable/disable flags for customization
  - Provider-specific retry and timeout settings
- **Backward Compatibility**: Can be completely disabled via `VALIDATOR_ENABLED=false` for legacy behavior

#### **Reconciler Service** (`app/reconciler/`)
- **Version Tracker**: Maintains complete version history for all records
- **Location Creator**: Handles geographic data and coordinate-based deduplication
- **Organization Creator**: Creates and manages organization entities
- **Service Creator**: Processes service information and relationships
- **Merge Strategy**: Handles source-specific records with canonical merging
- **Geocoding Corrector**: Validates and corrects address coordinates with 0,0 detection and multi-provider fallback

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
- **PostgreSQL 15+**: Primary data store with HSDS-compliant schema
- **PostGIS 3.3+**: Spatial extensions for geographic queries and indexing
- **Version Control**: Complete version tracking for all records via `record_version` table
- **Backup System**: Automated backups with configurable retention policies (default: 30 days)
- **Spatial Indexing**: Optimized for geographic search and boundary queries
- **Source-Specific Records**: Maintains original data alongside canonical merged records

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

> **New to Pantry Pirate Radio?** Start with our [interactive setup wizard](#quick-start-in-3-commands)!

### Quick Start in 3 Commands

```bash
# 1. Clone the repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. (Optional) Initialize scrapers submodule - only needed if you have access to private scrapers
git submodule init
git submodule update --remote

# 3. Run interactive setup wizard (creates .env file)
./bouy setup

# 4. Start all services with HAARRRvest data (recommended)
./bouy up --with-init

# That's it! API will be available at http://localhost:8000/docs
```

> **Note:** The scrapers are in a private submodule. If you don't have access, you can still:
> - Use the scraper framework and sample scraper
> - Contribute to API, LLM processing, validator, and other components
> - Build your own scrapers using the public framework

The setup wizard will guide you through:
- Database password configuration
- LLM provider selection (OpenAI or Claude)
- API key configuration
- HAARRRvest repository access setup

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

### Alternative Setup Methods

#### Using DevContainer (Recommended for Linux/Windows/Codespaces)
```bash
# 1. Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. Open in VSCode
code .

# 3. When prompted, select "Reopen in Container"
# DevContainer will handle all setup automatically

# 4. In the DevContainer terminal:
./bouy setup                 # Run setup wizard
./bouy up --with-init       # Start with data
```

#### Manual Configuration (Advanced Users)
```bash
# 1. Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. Setup environment manually:
cp .env.example .env
# Edit .env with your configuration

# 3. Start services
./bouy up                    # Without data initialization
# OR
./bouy up --with-init       # With HAARRRvest data (recommended)
```

### Understanding the Startup Process

When you run `./bouy up --with-init`:

1. **Infrastructure Setup** (1-2 minutes)
   - PostgreSQL database with PostGIS extension starts
   - Redis cache for job queuing starts
   - Network connections are established

2. **Data Initialization** (5-15 minutes)
   - HAARRRvest repository is shallow cloned (depth=1)
   - ~90 days of historical food resource data is imported
   - Database indexes are created and optimized
   - Spatial indexes for geographic queries are built

3. **Service Startup** (30 seconds)
   - FastAPI server starts on port 8000
   - Worker processes for LLM processing start
   - Reconciler service for data deduplication starts
   - All health checks pass

**Note**: First-time initialization takes longer due to data import. Subsequent runs without `--with-init` start in under a minute.

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
| **FastAPI API** | http://localhost:8000/api/v1 | Main API endpoints |
| **API Documentation** | http://localhost:8000/docs | Interactive Swagger UI |
| **API ReDoc** | http://localhost:8000/redoc | Alternative API documentation |
| **OpenAPI JSON** | http://localhost:8000/openapi.json | Machine-readable API spec |
| **Health Check** | http://localhost:8000/api/v1/health | API health status |
| **Database Health** | http://localhost:8000/api/v1/health/db | PostgreSQL status |
| **Redis Health** | http://localhost:8000/api/v1/health/redis | Redis cache status |
| **LLM Health** | http://localhost:8000/api/v1/health/llm | LLM provider status |
| **RQ Dashboard** | http://localhost:9181 | Job queue monitoring |
| **Datasette** | http://localhost:8001 | Data exploration (prod mode only) |
| **Prometheus Metrics** | http://localhost:8000/api/v1/metrics | System metrics |

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
  - Poetry (for dependency management)
  - PostgreSQL 15+ with PostGIS 3.3+ extension
  - Redis 7.0+

**Note**: All dependencies are containerized. Local installations are only needed if running without Docker, which is not recommended.

### Testing and Verification

After starting services, verify everything is working:

```bash
# Run comprehensive test suite
./bouy test                  # Runs all tests and quality checks

# Check service health
./bouy ps                    # List running services
curl http://localhost:8000/health  # API health check

# View API documentation
open http://localhost:8000/docs    # Interactive API docs
```

### Service Management

All service management uses bouy commands as documented in the [Bouy section](#bouy---docker-fleet-management) above.

#### Using Docker Compose Directly (Not Recommended)
```bash
# Note: Use bouy commands instead for proper orchestration
# Start all services
docker compose -f .docker/compose/base.yml up -d

# Start specific service
docker compose up -d app                    # FastAPI server
docker compose up -d worker                 # LLM workers
docker compose up -d recorder               # Recorder service
docker compose up -d reconciler             # Reconciler service
docker compose up -d haarrrvest-publisher   # HAARRRvest publisher

# View logs (use bouy logs instead)
./bouy logs app                  # FastAPI logs
./bouy logs worker               # Worker logs
./bouy logs recorder             # Recorder logs
./bouy logs reconciler           # Reconciler logs
./bouy logs haarrrvest-publisher # Publisher logs

# Scale workers
docker compose -f .docker/compose/base.yml up -d --scale worker=3  # Run 3 worker instances
# Or use bouy:
./bouy up --scale worker=3
```

### Development Commands

All development commands use bouy as documented in the [Bouy section](#bouy---docker-fleet-management) above.

#### **Local Development Commands** (if running without Docker - not recommended)
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
- **Test Coverage**: Ratcheting mechanism maintains baseline (currently ~80%) with 2% tolerance
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
3. **Workers** → Process with LLM → **Validator** (quality checks & enrichment)
4. **Validator** → High-confidence data only → **Database** (source-specific records)
5. **Reconciler** → Create canonical records → **Database** (merged HSDS data)
6. **Recorder** → Archive results → **Compressed archives**
7. **API** → Serve HSDS-compliant data → **Client applications**
8. **HAARRRvest Publisher** → Sync content store → **Durable backup**

## 🔍 Explore the Data

### [**HAARRRvest - Interactive Data Explorer**](https://datasette.for-the-gg.org)

Explore our harvested food resource data directly in your browser! HAARRRvest provides:
- 🌐 Interactive SQL queries via Datasette-Lite
- 📊 Daily updated SQLite database
- 📁 Organized JSON archives
- 🏴‍☠️ No installation required

## 📚 Documentation

### [📖 Documentation Hub - Start Here](docs/INDEX.md)
Our comprehensive documentation is organized in the **[Documentation Index](docs/INDEX.md)**, which serves as the central hub for all project documentation. This index provides:
- 🚀 Quick navigation by user level (Beginner, Developer, Advanced)
- 📂 Complete documentation catalog organized by category
- 🔍 Documentation relationships and dependencies
- 📌 Quick links to essential resources

### Quick Links to Core Documentation
- **[Bouy Command Reference](BOUY.md)** - Complete Docker fleet management guide
- **[API Documentation](API_DOCUMENTATION.md)** - Complete REST API reference with examples
- **[Interactive API Docs](http://localhost:8000/docs)** - Live Swagger UI (when services are running)
- **[Quick Start Guide](docs/quickstart.md)** - Get up and running in minutes
- **[Architecture Overview](docs/architecture.md)** - System design and components
- **[HSDS Specification](docs/hsds_index.md)** - Human Services Data Specification overview
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
CLAUDE_HEALTH_SERVER=true            # Enable health monitoring

# Content Store Configuration (for deduplication)
CONTENT_STORE_PATH=/path/to/store    # Path to content store directory
CONTENT_STORE_ENABLED=true           # Enable/disable content store (default: enabled if path set)

# HAARRRvest Publisher Configuration
DATA_REPO_TOKEN=your_github_pat      # GitHub PAT with repo scope for HAARRRvest
DATA_REPO_OWNER=For-The-Greater-Good # Repository owner
DATA_REPO_NAME=HAARRRvest           # Repository name

# Validation Configuration
VALIDATOR_ENABLED=true                # Enable validation service (default: true)
VALIDATION_REJECTION_THRESHOLD=10    # Confidence score below this is rejected (0-100, default: 10)

# Validation Enrichment Settings
ENRICHMENT_CACHE_TTL=86400           # Cache TTL for enrichment in seconds (default: 24 hours)
ENRICHMENT_MAX_RETRIES=3             # Maximum retry attempts per provider (default: 3)
ENRICHMENT_CIRCUIT_BREAKER_THRESHOLD=5  # Failures before circuit opens (default: 5)
ENRICHMENT_CIRCUIT_BREAKER_COOLDOWN=300 # Circuit breaker cooldown in seconds (default: 5 minutes)

# Validation Rules Configuration
VALIDATION_ENABLE_US_BOUNDS_CHECK=true      # Check if coordinates are within US boundaries
VALIDATION_ENABLE_TEST_DATA_DETECTION=true  # Detect and flag test/placeholder data
VALIDATION_ENABLE_STATE_VERIFICATION=true   # Verify coordinates match claimed state
VALIDATION_ENABLE_PLACEHOLDER_DETECTION=true # Detect generic/placeholder addresses

# Geocoding Configuration
GEOCODING_PROVIDER=arcgis            # Primary provider (arcgis, google, nominatim, census)
GEOCODING_CACHE_TTL=2592000          # Cache TTL in seconds (30 days)
GEOCODING_RATE_LIMIT=0.5             # Requests per second
GEOCODING_ENABLE_FALLBACK=true       # Enable fallback to other providers
GEOCODING_EXHAUSTIVE_FALLBACK=true   # Try all providers before accepting failure
NOMINATIM_USER_AGENT=pantry-pirate-radio  # Required for Nominatim
GOOGLE_MAPS_API_KEY=your_key_here    # Optional: For Google Maps provider
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

## Testing

### Test-Driven Development

This project follows Test-Driven Development (TDD) principles:

1. **Write Tests First**: Define expected behavior before implementation
2. **Run Tests**: Use `./bouy test --pytest` to run tests
3. **Implement**: Write minimal code to pass tests
4. **Refactor**: Improve code while keeping tests green
5. **Full Suite**: Run `./bouy test` before committing

### Running Tests

```bash
# Run complete test suite (recommended before commits)
./bouy test

# Run specific test types
./bouy test --pytest         # Unit and integration tests
./bouy test --mypy          # Type checking
./bouy test --black         # Code formatting
./bouy test --ruff          # Linting
./bouy test --bandit        # Security scanning
./bouy test --coverage      # Coverage analysis

# Run specific test files
./bouy test --pytest tests/test_api.py
./bouy test --pytest -- -k "test_geocoding"

# Debug failing tests
./bouy test --pytest -- -vsx --pdb
```

### Code Quality Standards

- **Test Coverage**: Minimum 80% with ratcheting mechanism
- **Type Safety**: Strict mypy checking with no Any types
- **Code Style**: Black formatting (88 char lines)
- **Security**: Bandit scanning for vulnerabilities
- **Documentation**: Docstrings for all public functions
- **Data Quality**: Confidence scoring (0-100) for all locations
- **Validation**: Automatic rejection of test/placeholder data

## Contributing

We welcome contributions! Please read our [contribution guidelines](CONTRIBUTING.md) before submitting pull requests.

### Development Workflow

1. **Fork and Clone**: Fork the repository and clone locally
2. **Setup Environment**: Run `./bouy setup` to configure
3. **Create Branch**: Use descriptive names like `feat/new-scraper`
4. **Write Tests**: Follow TDD - write tests before code
5. **Implement**: Write code to pass tests
6. **Run Tests**: Ensure `./bouy test` passes
7. **Commit**: Use conventional commits (feat:, fix:, docs:, etc.)
8. **Push and PR**: Submit pull request with clear description

## Troubleshooting

### Common Issues and Solutions

#### Services Won't Start
```bash
# Check Docker is running
docker version

# Clean and restart
./bouy clean
./bouy up

# Check logs for errors
./bouy logs
```

#### Database Connection Errors
```bash
# Verify database is running
./bouy ps | grep db

# Check database logs
./bouy logs db

# Test connection
./bouy exec db pg_isready
```

#### LLM Authentication Issues
```bash
# For Claude provider
./bouy claude-auth status
./bouy claude-auth setup

# Check environment variables
./bouy exec worker env | grep -E "(ANTHROPIC|OPENROUTER|LLM)"
```

#### Test Failures
```bash
# Run with verbose output
./bouy test --pytest -- -v

# Debug specific test
./bouy test --pytest -- tests/test_file.py::test_function -vvs --pdb
```

For more solutions, see [Troubleshooting Guide](docs/troubleshooting.md).

## License

This software is released under the sandia-ftgg-nc-os-1.0 license. See [LICENSE](LICENSE) for full details.

**Key License Terms**:
- Free for non-commercial use
- Attribution required
- No warranty provided
- Commercial use requires permission

## About FTGG
For The Greater Good (FTGG) specializes in making public resources truly accessible through intelligent aggregation. Learn more at [forthegg.org](https://forthegg.org).

## Community and Support

### Get Help
- **Documentation Hub**: [Complete Documentation Index](docs/INDEX.md)
- **Issues**: [GitHub Issues](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
- **Discussions**: [GitHub Discussions](https://github.com/For-The-Greater-Good/pantry-pirate-radio/discussions)

### Project Status
- **Active Development**: Regular updates and improvements
- **Production Ready**: Used in production environments
- **Community Driven**: Open to contributions and feedback

---

**For The Greater Good (FTGG)** | *Making public resources truly accessible through intelligent aggregation*

*Breaking down information barriers in food security through AI-powered data unification and HSDS-compliant APIs.*

[Website](https://www.for-the-gg.org) | [HAARRRvest Data Explorer](https://datasette.for-the-gg.org) | [API Documentation](API_DOCUMENTATION.md) | [Interactive API Docs](https://api.for-the-gg.org/docs)
