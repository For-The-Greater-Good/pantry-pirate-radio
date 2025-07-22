<img width="1024" height="1024" alt="ChatGPT Image Jul 11, 2025 at 09_59_43 AM" src="https://github.com/user-attachments/assets/1f6a1f2a-adf1-4bfe-8969-d13c4c315de7" />

# 🎧 Pantry Pirate Radio

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
<img width="1024" height="1024" alt="ChatGPT Image Jul 12, 2025 at 07_16_15 PM" src="https://github.com/user-attachments/assets/4e3945ff-2606-40ab-b64f-08c612f09566" />

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

```plaintext
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Scrapers  │───▶│    Redis    │◀───│   Workers   │
│   [12+]     │    │    Queue    │    │ [Scalable]  │
└─────────────┘    └──────┬──────┘    └──────┬──────┘
                          │                  │
                          ▼                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Recorder   │    │ Reconciler  │    │     LLM     │
│  Service    │    │  Service    │    │ Providers   │
└──────┬──────┘    └──────┬──────┘    └─────────────┘
       │                  │
       ▼                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Archives   │    │PostgreSQL + │    │   FastAPI   │
│ (Compressed)│    │   PostGIS   │◀───│   Server    │
└─────────────┘    └─────────────┘    └─────────────┘
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
- **Job Archival**: Archives all job results to JSON files in `outputs/`
- **Data Compression**: Maintains compressed raw data archives
- **Audit Trail**: Complete audit trail for all processing activities
- **File Management**: Utilities for archive organization and cleanup

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

## Quick Start

### Using DevContainer (Recommended)
```bash
# 1. Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. Open in VSCode
code .

# 3. When prompted, select "Reopen in Container"
# DevContainer will handle all setup automatically
```

### Manual Setup
```bash
# 1. Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# 2. Copy environment variables
cp .env.example .env
# Edit .env with your configuration (API keys, passwords, etc.)

# 3. Enable git hooks for security
git config core.hooksPath .githooks

# 4. Install dependencies
poetry install

# 5. Start all services
docker-compose up -d

# FastAPI server will be available at http://localhost:8000
# Workers will start automatically
# Search orchestrator will run scrapers on schedule
```

Visit http://localhost:8000/docs for API documentation

## LLM Provider Configuration

The system supports two LLM providers for HSDS data alignment:

### Claude Provider (Recommended)
```bash
# Set environment variables
export LLM_PROVIDER=claude
export ANTHROPIC_API_KEY=your_api_key_here  # Optional

# Start services
docker-compose up -d

# Setup authentication (interactive)
docker-compose exec worker python -m app.claude_auth_manager setup

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
docker-compose up -d
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

### Prerequisites
- Python 3.11+
- Poetry
- Docker and Docker Compose
- PostgreSQL with PostGIS
- Redis 7.0+

### Service Management
```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d app         # FastAPI server
docker-compose up -d worker      # LLM workers
docker-compose up -d orchestrator # Search orchestrator (runs scrapers)
docker-compose up -d recorder    # Recorder service
docker-compose up -d reconciler  # Reconciler service
docker-compose up -d db-backup   # Database backup service

# View logs
docker-compose logs -f app          # FastAPI logs
docker-compose logs -f worker       # Worker logs
docker-compose logs -f orchestrator # Search orchestrator logs
docker-compose logs -f recorder     # Recorder logs
docker-compose logs -f reconciler   # Reconciler logs
docker-compose logs -f db-backup    # Database backup logs

# Scale workers
docker-compose up -d --scale worker=3  # Run 3 worker instances
```

### Development Commands

#### **Testing & Quality**
```bash
# Run all tests with coverage
poetry run pytest

# Run specific test types
poetry run pytest -m integration        # Integration tests
poetry run pytest -m asyncio           # Async tests
poetry run pytest tests/test_scraper/  # Scraper tests

# Coverage analysis
bash scripts/coverage-report.sh        # Comprehensive coverage
poetry run coverage report --show-missing --sort=Cover

# Code quality checks
poetry run mypy .                       # Type checking
poetry run black .                      # Code formatting
poetry run ruff .                       # Linting
poetry run bandit -r app/               # Security scan
poetry run vulture app/                 # Unused code detection

# Run all CI checks
./scripts/run-ci-checks.sh
```

#### **Scraper Management**
```bash
# List available scrapers
python -m app.scraper --list

# Run specific scraper
python -m app.scraper nyc_efap_programs

# Run all scrapers
python -m app.scraper --all

# Run scrapers in parallel
python -m app.scraper --all --parallel --max-workers 4

# Test scrapers without processing
python -m app.scraper.test_scrapers --all
```

#### **Docker Development**
```bash
# Build specific service targets
docker build --target app -t pantry-pirate-radio:app .
docker build --target worker -t pantry-pirate-radio:worker .
docker build --target recorder -t pantry-pirate-radio:recorder .

# Run tests using Docker
docker build --target test -t pantry-pirate-radio:test .
docker run --rm pantry-pirate-radio:test

# Debug service containers
docker-compose exec app bash
docker-compose exec worker bash
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
1. **Scrapers** → Collect raw data → **Redis Queue**
2. **Workers** → Process with LLM → **Database** (source-specific records)
3. **Reconciler** → Create canonical records → **Database** (merged HSDS data)
4. **Recorder** → Archive results → **Compressed archives**
5. **API** → Serve HSDS-compliant data → **Client applications**

## Documentation
- [Architecture Details](docs/architecture.md)
- [API Reference](docs/api.md)
- [HSDS Implementation](docs/HSDS/)
- [LLM System](docs/llm.md)
- [Reconciler Service](docs/reconciler.md)
- [Recorder Service](docs/recorder.md)
- [Worker System](docs/worker.md)
- [Database Backup](docs/database-backup.md)
- [Deployment Guide](docs/deployment.md)
- [GitHub Workflows Guide](docs/GITHUB_WORKFLOWS.md)
- [Troubleshooting](docs/troubleshooting.md)

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
