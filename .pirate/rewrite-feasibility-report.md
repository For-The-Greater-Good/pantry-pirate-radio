# Pantry Pirate Radio: Rewrite Feasibility & Proposal Report

> Compiled from 65 research agents dispatched across the entire codebase
> Date: 2026-02-27
> Branch: claude/agent-codebase-documentation-IQGev

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current System Overview](#2-current-system-overview)
3. [Component Summary Matrix](#3-component-summary-matrix)
4. [Architecture & Data Flow](#4-architecture--data-flow)
5. [Technical Debt Catalog](#5-technical-debt-catalog)
6. [Cross-Cutting Analysis](#6-cross-cutting-analysis)
7. [Rewrite Feasibility Analysis](#7-rewrite-feasibility-analysis)
8. [Rewrite Proposals](#8-rewrite-proposals)
9. [Migration Strategy](#9-migration-strategy)
10. [Risk Assessment](#10-risk-assessment)
11. [Appendix: Agent Inventory](#11-appendix-agent-inventory)

---

## 1. Executive Summary

### The System

Pantry Pirate Radio (PPR) is a **food security data pipeline** that scrapes public food bank/pantry websites, normalizes the data to **HSDS v3.1.1** (Human Services Data Specification) using LLM processing, validates and enriches it with geocoding, reconciles it into canonical records in PostgreSQL, and publishes it as both a REST API and static data exports via the HAARRRvest repository.

### By the Numbers

| Metric | Value |
|--------|-------|
| **Total Python files** | 135 |
| **Total lines of code** | ~35,075 (app) + ~53,000 (tests/scripts/infra) |
| **Total classes** | 181 |
| **Total functions** | 703 |
| **Pydantic models** | 57 |
| **Database models** | 6 core (Organization, Location, Service, Schedule, Address, ServiceAtLocation) |
| **API endpoints** | 28 |
| **Test files** | 161 |
| **Tests** | 1,787 |
| **Production dependencies** | 33 |
| **Dev dependencies** | 23 |
| **Docker services** | 13 |
| **Scrapers** | 30+ (private submodule) |
| **Environment variables** | 121+ |

### Key Findings

1. **The architecture is sound.** The pipeline design (Scrape → Dedup → LLM → Validate → Reconcile → Publish) is well-conceived and the separation of concerns is reasonable.

2. **The debt is moderate-high.** Estimated at ~530 hours (13 weeks FTE) across all categories. The largest files (1,669, 1,568, 1,498 LOC) are the primary maintenance burden.

3. **Code quality is inconsistent but not broken.** Zero bare `except:` clauses, strong SQL injection prevention, but 147 print statements instead of structured logging, 26 `type: ignore` comments, and significant code duplication (~2,400-3,200 lines).

4. **Security posture is strong.** Public read-only API by design, no authentication needed, parameterized queries throughout, safe subprocess calls, comprehensive security headers.

5. **HSDS compliance is at 66%.** Core entities (Organization, Service, Location, ServiceAtLocation) are 100% compliant. Extended entities (Taxonomy, Program, Contact) are missing or stubbed.

6. **A rewrite is feasible** but should be incremental, not big-bang. The system is running in production and serving real food security data.

### Recommendation

**Incremental rewrite in TypeScript** using the strangler fig pattern, starting with the API layer and working inward. Python remains viable but TypeScript offers superior type safety, a unified frontend/backend language for the Flutter companion app's potential web version, and the team's expressed interest in exploring it.

---

## 2. Current System Overview

### System Architecture

```
                    ┌─────────────┐
                    │ Web Sources  │
                    │ (Food Banks) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Scrapers   │  30+ scrapers, ScraperJob base class
                    │  (app/scraper)│  Playwright, HTTP, PDF parsing
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │Content Store │  SHA-256 dedup, SQLite + filesystem
                    │(app/content_ │  Prevents reprocessing identical data
                    │    store)    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Redis Queue  │  RQ (Redis Queue) job management
                    │  (RQ/Redis)  │  4 named queues: llm, validator,
                    └──────┬──────┘    reconciler, recorder
                           │
                    ┌──────▼──────┐
                    │ LLM Workers  │  OpenAI (via OpenRouter) + Claude
                    │  (app/llm)   │  HSDS schema alignment
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Validator   │  Confidence scoring (0-100)
                    │(app/validator)│  Geocoding enrichment, test data
                    └──────┬──────┘    detection, quality control
                           │
                    ┌──────▼──────┐
                    │  Reconciler  │  Canonical record creation
                    │(app/reconciler│  Advisory locks, merge strategies
                    └──────┬──────┘    Version tracking
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐ ┌──▼───┐ ┌──────▼──────┐
       │  PostgreSQL  │ │ API  │ │  HAARRRvest  │
       │   + PostGIS  │ │(Fast │ │  Publisher   │
       │  (Database)  │ │ API) │ │(Git exports) │
       └─────────────┘ └──────┘ └─────────────┘
```

### Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Web Framework** | FastAPI + Uvicorn | >=0.116.0 |
| **ORM** | SQLAlchemy (async) | ^2.0.37 |
| **Database** | PostgreSQL + PostGIS | 15+ |
| **Cache/Queue** | Redis + RQ | ^5.0.0 / ^1.15.1 |
| **Validation** | Pydantic v2 | ^2.6.0 |
| **LLM** | OpenAI SDK + Claude CLI | ^1.10.0 |
| **Geocoding** | geopy (ArcGIS, Nominatim, Census) | ^2.4.1 |
| **Monitoring** | Prometheus + structlog | ^0.19.0 / ^24.1.0 |
| **Container** | Docker + docker compose | Multi-stage unified image |
| **CLI** | Bouy (custom bash, 2,810 LOC) | v1.0.0 |
| **CI/CD** | GitHub Actions + GitLab CI | Dual pipeline |
| **Python** | 3.11+ | ^3.11 |

---

## 3. Component Summary Matrix

### Core Pipeline Components

| Component | Files | LOC | Classes | Functions | Test Coverage | Debt Level | Complexity |
|-----------|-------|-----|---------|-----------|---------------|------------|------------|
| **API Layer** | 12 | ~2,500 | 0 | 35+ | Medium (36 tests) | Low-Medium | Medium |
| **Database** | 5 | ~1,800 | 8 | 30+ | Medium | Medium | Medium |
| **LLM Module** | 14 | ~3,200 | 12 | 50+ | Medium | Medium-High | High |
| **Reconciler** | 8 | ~5,500 | 8 | 60+ | Medium | High | Very High |
| **Validator** | 10 | ~4,200 | 10 | 70+ | Medium | Medium-High | High |
| **Content Store** | 5 | ~1,500 | 4 | 25+ | Medium | Low-Medium | Medium |
| **Publisher** | 7 | ~4,000 | 5 | 40+ | Low | Very High | Very High |
| **Geocoding** | 6 | ~1,800 | 5 | 30+ | Medium | Medium | Medium |
| **Scraper** | 5+ | ~2,000 | 5+ | 30+ | Low | Medium | Medium |

### Infrastructure Components

| Component | Files | LOC | Purpose | Debt Level |
|-----------|-------|-----|---------|------------|
| **Bouy CLI** | 3 | 2,810 | Docker fleet management, 35+ commands | Low |
| **Docker** | 10+2+3 | 1,350 | 13 services, unified multi-stage image | Low |
| **CI/CD** | 5 | 1,155 | GitHub Actions + GitLab CI dual pipeline | Low |
| **Project Config** | 4 | 1,408 | pyproject.toml, env, devcontainer | Medium |
| **DB Scripts** | 16 | 4,565 | Data migration history, state fixes | Medium |
| **FA Scripts** | 14 | 3,455 | Scraper generation factory, GitHub integration | Low |

### Supporting Modules

| Component | Files | LOC | Purpose | Debt Level |
|-----------|-------|-----|---------|------------|
| **Core Config** | 3 | ~800 | Settings, events, logging | Medium |
| **Middleware** | 4 | ~400 | Security headers, CORS, correlation IDs, errors | Low |
| **Models (HSDS)** | 8 | ~1,200 | 57 Pydantic models, HSDS compliance | Low |
| **Datasette** | 3 | ~1,400 | SQLite export for data viewing | Medium |

---

## 4. Architecture & Data Flow

### Pipeline Stages (from agents X1 & X2)

#### Stage 1: Scrape → Content Store
```
ScraperJob.submit_to_queue()
  → ScraperResult(name, address, phone, url, hours, services, latitude, longitude)
  → ContentStore.store(raw_html_or_json)
     → SHA-256 hash → check_duplicate()
     → If new: SQLite record + filesystem storage
  → Redis queue 'llm' → LLMJob(prompt, format, metadata)
```

#### Stage 2: LLM Processing
```
LLMJob received by worker
  → SchemaConverter builds HSDS-aligned prompt
  → Provider (OpenAI/Claude) processes
  → Structured JSON output: {organization, location, services[], schedules[]}
  → Validation of output against Pydantic models
  → Redis queue 'validator' → ValidatorJob
```

#### Stage 3: Validation & Enrichment
```
ValidatorJob received
  → Confidence scoring (0-100, deduction-based)
     → Test data detection (-100 deduction)
     → Placeholder address detection (-50 deduction)
     → Missing required fields (-15 each)
     → Invalid coordinates (-20 deduction)
  → Geocoding enrichment (if coordinates missing/invalid)
     → ArcGIS → Nominatim → Census (exhaustive fallback)
     → Redis cache (24hr TTL)
  → State/ZIP validation and correction
  → If score >= threshold (10): Redis queue 'reconciler'
  → If score < threshold: Rejected, logged, not stored
```

#### Stage 4: Reconciliation → Database
```
ReconcilerJob received
  → Organization matching (name similarity + source tracking)
  → Location matching (coordinate proximity + address fuzzy match)
  → Service matching (name + organization context)
  → Advisory lock (pg_advisory_xact_lock) per entity
  → INSERT...ON CONFLICT for upsert
  → Merge strategy with majority voting for conflicts
  → Version tracking for change history
  → PostgreSQL with PostGIS geometry column
```

#### Stage 5: API & Publishing
```
PostgreSQL → FastAPI (read-only HSDS v3.1.1 API)
  → 28 endpoints with pagination
  → Geographic queries (radius, bounding box)
  → Map optimization endpoints

PostgreSQL → HAARRRvest Publisher
  → Periodic sync to Git repository
  → JSON/GeoJSON/SQLite exports
  → GitHub Pages for public access
```

### Data Shape at Each Stage

| Stage | Format | Key Fields |
|-------|--------|------------|
| Scraper Output | ScraperResult dict | name, address, phone, hours, lat/lng |
| Content Store | SHA-256 keyed blob | raw content + metadata |
| LLM Input | Structured prompt | raw data + HSDS schema template |
| LLM Output | Parsed JSON | organization{}, location{}, services[], schedules[] |
| Validator Input | LLM output + metadata | + source_url, scraper_name |
| Validator Output | Enriched + scored | + confidence_score, validation_status, geocoded coords |
| Reconciler Output | DB records | Canonical UUIDs, merged fields, version history |
| API Output | HSDS JSON | Paginated, nested relationships, metadata |

---

## 5. Technical Debt Catalog

### Severity Distribution

| Severity | Count | Estimated Effort |
|----------|-------|-----------------|
| **Critical** | 4 items | 15 hours |
| **High** | 18 items | 120 hours |
| **Medium** | 35 items | 200 hours |
| **Low** | 30 items | 45 hours |
| **Informational** | varies | N/A |
| **TOTAL** | 87+ items | ~530 hours (13 weeks FTE) |

### Critical Issues

| # | Issue | Location | Impact | Effort |
|---|-------|----------|--------|--------|
| 1 | **Debug print statements in production** | `app/llm/queue/processor.py:87-88` | Prints metadata for every job processed | Trivial |
| 2 | **Schedule eager loading disabled** | `app/database/repositories.py:214-215, 231-232, 382-383` | Causes N+1 queries on all location queries | Medium |
| 3 | **State boundary checking returns True unconditionally** | `app/validator/scraper_context.py:344` | False data acceptance | Medium |
| 4 | **SQL injection risk via string concatenation** | `app/api/v1/map/search_service.py` | Potential injection in search queries | Medium |

### High Priority Debt

| # | Issue | Scope | Effort |
|---|-------|-------|--------|
| 5 | **10 files exceed 750 LOC** (largest: 1,669) | Publisher, Reconciler, LLM | Large (per file) |
| 6 | **147 print() instead of logger** | 48+ files across codebase | Medium (scriptable) |
| 7 | **26 type: ignore comments** | Database, API, Validator | Medium |
| 8 | **~2,400-3,200 lines of duplicated code** | Reconciler creators, exporters, geocoding | Large |
| 9 | **3 unsafe singletons without thread locks** | Module-level globals | Small |
| 10 | **Redis connection blocks at import time** | `app/llm/queue/queues.py` | Medium |
| 11 | **8 unused production dependencies** | pyproject.toml | Small |
| 12 | **Dual PostgreSQL drivers** | psycopg + psycopg2-binary | Small |
| 13 | **Double schema wrapper architecture** | `schema_converter.py:1002` | Medium |
| 14 | **0 bare except, but 24 broad Exception catches** | Various | Medium |
| 15 | **Taxonomy endpoints stubbed (not implemented)** | API v1 | High |

### Code Duplication Hotspots (from agent X10)

| Duplication Area | Files Affected | Duplicated Lines | Priority |
|------------------|---------------|-----------------|----------|
| Reconciler creators (retry, logging, INSERT) | 3 files | 350-400 | Critical |
| HAARRRvest export classes | 4 files | 280-350 | High |
| API pagination pattern | 5+ endpoints | 200-250 | Medium |
| Geocoding coordinate validation | 4 files | 180-220 | High |
| Database connection string | 4 files | 140-180 | High |
| State/ZIP mapping calls | 3+ files | 120-160 | Medium |
| Error handling boilerplate | 48+ files | 150-200 | Medium |
| Validation metadata handling | 3+ files | 80-120 | Medium |

### Monolithic Files Needing Decomposition

| File | LOC | Responsibility Overload |
|------|-----|------------------------|
| `haarrrvest_publisher/service.py` | 1,669 | Git ops + data processing + scheduling + state management |
| `reconciler/job_processor.py` | 1,568 | Org + Location + Service processing in single class |
| `llm/hsds_aligner/schema_converter.py` | 1,498 | Schema building + output formatting + validation |
| `datasette/exporter.py` | 1,181 | SQL generation + export logic + file management |
| `reconciler/service_creator.py` | 990 | Service + schedule + SAL creation |
| `validator/enrichment.py` | 931 | Geocoding + state validation + data augmentation |

---

## 6. Cross-Cutting Analysis

### Error Handling (X3)
- **250 try/except blocks** across 135 files
- **0 bare `except:`** clauses (excellent)
- **24 broad `except Exception:`** catches (could be more specific)
- **5 custom exception classes** (could use more domain-specific exceptions)
- **Consistency score: 7/10** - generally good but could be more uniform

### Configuration (X4)
- **52+ unique environment variables** via Pydantic Settings
- **Duplication between Settings and ValidatorConfig** classes
- **DB config scattered** across 4+ files
- **Well-typed** via Pydantic BaseSettings with validation

### Testing (X5)
- **1,787 tests in 161 files**
- **Only 9% async** despite async-first codebase
- **Critical gaps**: middleware (0 tests), integration (0.7%), API (36 tests only)
- **Coverage ratcheting** in CI prevents regression

### Database Queries (X6)
- **72 query patterns** across 31 files
- **68% ORM / 32% raw SQL** mix
- **3 critical N+1 patterns** in map search and services
- **SQL injection risk** in search_service.py via string concatenation

### Authentication & Security (X7)
- **Public read-only API** by design - no auth needed
- **Claude auth**: CLI-based with Redis state management
- **SQL injection: VERY LOW risk** - parameterized throughout
- **Command injection: VERY LOW** - safe subprocess calls
- **Security headers**: Good foundation, missing CSP
- **Rate limiting**: LLM quota managed, HTTP not limited (intentional)

### Redis Usage (X8)
- **4 named queues**: llm, validator, reconciler, recorder
- **Geocoding cache**: 24hr TTL
- **Claude auth state**: Cross-worker quota tracking
- **Circuit breaker pattern** in geocoding providers
- **Max 50 pool connections** with graceful degradation

### Pydantic Models (X9)
- **57 Pydantic models** across 21 files
- **95%+ Pydantic v2** compliant (only 2 v1 patterns in geographic.py)
- **CRUD triple-model pattern**: Read/Create/Update per entity
- **Generic `Page[T]`** pagination wrapper
- **7 custom validators** for coordinates, bounding boxes, status enums
- **Model duplication** between Consumer API and Map API models

### Code Duplication (X10)
- **~2,400-3,200 duplicated lines** estimated
- **Top offenders**: Reconciler creators, HAARRRvest exporters, geocoding validation
- **~1,150 lines recoverable** through 5 refactoring phases

### Dependencies (X11)
- **33 production + 23 dev** dependencies
- **8 unused production deps** (pdfplumber, marshmallow, xlrd, pyjwt, etc.)
- **Dual PostgreSQL drivers** (psycopg + psycopg2-binary)
- **3 missing explicit deps** (click, flask, requests - currently transitive)
- **Heavy deps**: geopandas (~50MB), playwright (~250MB)

### Metrics & Observability (X12)
- **16 Prometheus metrics** across validator/reconciler/core
- **Request duration measured but NOT recorded** to histogram
- **No distributed tracing**
- **Health checks** separate per service
- **structlog** for structured logging (but 147 print() bypass it)

### State Management (X13)
- **3 module-level singletons** without thread safety
- **ZERO `threading.Lock`** usage anywhere
- **Redis connection blocks at import time** in `llm/queue/queues.py`
- **Duplicate Settings instances** possible

### API Contract & HSDS (X14)
- **28 endpoints** under `/api/v1`
- **Core HSDS entities: 100%** (Organization, Service, Location, ServiceAtLocation)
- **Extended entities: 35%** (Address, Schedule partial; Taxonomy, Program, Contact missing)
- **Overall HSDS coverage: 66%**
- **Custom extensions**: validation scoring, geocoding tracking, map endpoints
- **Pagination consistent** with `Page[T]` wrapper

### Technical Debt (X15)
- **87+ identified items** across all severity levels
- **5 TODOs in core paths**
- **2 debug statements in production**
- **21 empty pass statements** (mostly acceptable)
- **18+ hardcoded magic numbers**
- **3 deprecated methods** without `@deprecated` decorator
- **14 security suppressions** (mostly justified)

---

## 7. Rewrite Feasibility Analysis

### Should You Rewrite?

| Factor | Assessment | Weight |
|--------|-----------|--------|
| **System age & iteration** | High iteration debt but functional | Moderate |
| **Architecture quality** | Pipeline design is sound; individual components need work | In favor of incremental |
| **Test coverage** | 1,787 tests provide safety net for migration | In favor of rewrite |
| **Team knowledge** | Original author available; full source access | In favor of rewrite |
| **Production criticality** | Serving real food security data | Against big-bang |
| **Dependency health** | Mostly modern, well-maintained deps | Neutral |
| **Code quality** | Moderate-high debt but no showstoppers | In favor of rewrite |

**Verdict: YES, rewrite is feasible and justified.** The system works but maintenance cost is increasing. A measured, incremental approach preserves functionality while improving quality.

### Effort Estimation

| Phase | Scope | Effort (Python) | Effort (TypeScript) |
|-------|-------|-----------------|---------------------|
| **API Layer** | 28 endpoints, Pydantic models, middleware | 2-3 weeks | 3-4 weeks |
| **Database Layer** | Models, repositories, migrations | 2-3 weeks | 3-4 weeks |
| **Validator Service** | Scoring, enrichment, geocoding | 3-4 weeks | 4-5 weeks |
| **Reconciler** | Matching, merging, version tracking | 3-4 weeks | 4-5 weeks |
| **LLM Integration** | Providers, schema conversion, queue | 2-3 weeks | 3-4 weeks |
| **Content Store** | Dedup, storage, metadata | 1-2 weeks | 2-3 weeks |
| **Scraper Framework** | Base class, utilities, plugin system | 2-3 weeks | 3-4 weeks |
| **Publisher** | Git ops, data export, scheduling | 2-3 weeks | 3-4 weeks |
| **Infrastructure** | Docker, CI/CD, CLI | 1-2 weeks | 1-2 weeks |
| **Testing** | Rewrite 1,787 tests | 4-6 weeks | 5-7 weeks |
| **Integration** | End-to-end, migration, cutover | 2-3 weeks | 2-3 weeks |
| **TOTAL** | | **24-36 weeks** | **33-45 weeks** |

### Language Choice Analysis

#### Option A: Python Rewrite (Clean)

**Pros:**
- Existing team expertise
- All current libraries available
- Faster time to completion (~24-36 weeks)
- Tests can be partially reused
- Pydantic v2 already working well

**Cons:**
- Still dynamic typing (mitigated by mypy)
- May accumulate same debt patterns
- No frontend/backend language unification

**Recommended Stack:**
- FastAPI (keep) + SQLAlchemy 2.0 (keep) + Pydantic v2 (keep)
- Replace RQ with Celery or Dramatiq for better async support
- Add proper dependency injection (dependency-injector)
- Enforce strict mypy from day one

#### Option B: TypeScript Rewrite

**Pros:**
- Superior type safety at compile time
- Unified language with potential web frontend
- Richer ecosystem for API development
- Better async/await patterns (native)
- npm ecosystem mature for all needs

**Cons:**
- Longer timeline (~33-45 weeks)
- No direct Pydantic equivalent (Zod is close but different)
- PostGIS integration less mature
- LLM SDK parity (OpenAI SDK available, Claude SDK good)

**Recommended Stack:**

| Python Current | TypeScript Replacement |
|---------------|----------------------|
| FastAPI | Fastify or NestJS |
| SQLAlchemy | Prisma (type-safe ORM) |
| Pydantic | Zod (runtime validation) |
| Redis + RQ | Redis + BullMQ |
| PostgreSQL/PostGIS | PostgreSQL/PostGIS (same) |
| Prometheus | prom-client |
| structlog | Pino |
| OpenAI SDK | @openai/sdk |
| geopy | OpenCage or custom |
| Playwright | Playwright (same API) |

#### Option C: Hybrid (Recommended)

**Strategy:** Rewrite the API layer and new features in TypeScript while maintaining the Python pipeline (scraper → LLM → validator → reconciler) as a separate service communicating via Redis queues.

**Pros:**
- Incremental migration with zero downtime
- Play to each language's strengths
- TypeScript for API/web-facing code
- Python for data processing/LLM/ML work
- Shared Redis queue interface

**Cons:**
- Two languages to maintain
- More complex deployment
- Cross-language type sharing challenges

---

## 8. Rewrite Proposals

### Proposal A: Clean Python Rewrite (Recommended if staying Python)

**Timeline: 24-36 weeks**

#### Architecture Principles
1. **Strict dependency injection** - No module-level singletons
2. **Domain-driven design** - Bounded contexts for each pipeline stage
3. **CQRS pattern** - Separate read/write models cleanly
4. **Event-driven** - Replace direct queue calls with event bus
5. **100% async** - No sync code in the pipeline
6. **Strict mypy** - `--strict` mode from day one

#### Module Structure
```
src/
├── api/                    # FastAPI application
│   ├── v1/
│   │   ├── endpoints/      # One file per entity (max 200 LOC)
│   │   ├── middleware/      # Security, correlation, metrics
│   │   └── dependencies/   # FastAPI dependency injection
│   ├── consumer/           # Mobile app endpoints
│   └── map/                # Map-specific endpoints
├── domain/                 # Pure business logic (no framework deps)
│   ├── models/             # Domain entities (dataclasses/attrs)
│   ├── services/           # Business operations
│   ├── events/             # Domain events
│   └── exceptions/         # Domain-specific exceptions
├── infrastructure/         # External adapters
│   ├── database/           # SQLAlchemy repos, migrations
│   ├── cache/              # Redis abstraction
│   ├── queue/              # Job queue abstraction
│   ├── llm/                # LLM provider adapters
│   ├── geocoding/          # Geocoding provider adapters
│   └── git/                # HAARRRvest Git operations
├── pipeline/               # Data processing pipeline
│   ├── scraper/            # Scraper framework
│   ├── content_store/      # Deduplication
│   ├── validator/          # Scoring & enrichment
│   └── reconciler/         # Canonical record creation
└── shared/                 # Cross-cutting concerns
    ├── config/             # Unified configuration
    ├── logging/            # Structured logging
    ├── metrics/            # Prometheus metrics
    └── testing/            # Test utilities & fixtures
```

#### Key Improvements
- **Max file size: 300 LOC** (enforced by linting)
- **Dependency injection** via FastAPI's Depends() and a DI container
- **Abstract interfaces** for all external services (database, Redis, LLM, geocoding)
- **Proper error hierarchy** with domain-specific exceptions
- **Event bus** replacing direct Redis queue coupling
- **Repository pattern** with proper unit-of-work
- **No print statements** - structured logging only

### Proposal B: TypeScript Rewrite (Recommended for new direction)

**Timeline: 33-45 weeks**

#### Architecture
```
src/
├── api/                    # Fastify or NestJS
│   ├── controllers/        # Route handlers
│   ├── middleware/          # Auth, CORS, metrics
│   ├── schemas/            # Zod validation schemas
│   └── dto/                # Data transfer objects
├── domain/                 # Pure TypeScript, no framework deps
│   ├── entities/           # Domain types (interfaces + classes)
│   ├── services/           # Business logic
│   ├── events/             # Domain events
│   └── errors/             # Custom error classes
├── infrastructure/
│   ├── database/           # Prisma client, repos
│   ├── cache/              # Redis via ioredis
│   ├── queue/              # BullMQ workers
│   ├── llm/                # OpenAI + Anthropic SDKs
│   ├── geocoding/          # Multi-provider geocoding
│   └── git/                # simple-git for HAARRRvest
├── pipeline/
│   ├── scraper/            # Playwright + Cheerio
│   ├── dedup/              # Content-addressable store
│   ├── validator/          # Confidence scoring
│   └── reconciler/         # Record matching/merging
├── shared/
│   ├── config/             # Type-safe env config
│   ├── logger/             # Pino structured logging
│   └── metrics/            # prom-client
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

#### TypeScript-Specific Advantages
- **Prisma** generates types from schema - no model/DB drift
- **Zod** provides runtime validation with type inference
- **BullMQ** is superior to RQ for job management (priorities, rate limiting, retries)
- **Native async/await** with proper error boundaries
- **ESLint + TypeScript strict mode** catches more bugs at compile time

### Proposal C: Hybrid Strangler Fig (Recommended overall)

**Timeline: Phase 1 (API) 6-8 weeks, then incremental**

#### Phase 1: TypeScript API Gateway
- New Fastify/NestJS API in front of existing PostgreSQL
- Read directly from existing database (Prisma ORM)
- Existing Python pipeline continues writing to same DB
- **Zero downtime migration**

#### Phase 2: TypeScript Validator Service
- Rewrite validator as TypeScript microservice
- Communicate via Redis queues (same interface)
- Decommission Python validator

#### Phase 3: TypeScript Reconciler
- Most complex migration - proceed carefully
- Maintain both versions during transition
- Comprehensive integration tests before cutover

#### Phase 4: TypeScript LLM Workers
- Straightforward - OpenAI SDK has excellent TS support
- Claude SDK (Anthropic) also has TS SDK

#### Phase 5: TypeScript Scrapers
- Playwright is identical API in TS
- Cheerio replaces BeautifulSoup
- Migrate scrapers one at a time

#### Phase 6: Decommission Python
- Remove Python codebase
- Consolidate to single TypeScript monorepo

---

## 9. Migration Strategy

### Pre-Migration Checklist

1. **Document all API contracts** - OpenAPI spec already exists (ppr-openapi.json)
2. **Capture all integration points** - Redis queue message formats, DB schema
3. **Create comprehensive integration tests** - Currently only 0.7% integration tests
4. **Freeze schema changes** during migration
5. **Set up feature flags** for gradual traffic shifting

### Database Migration

The PostgreSQL database with PostGIS is **the shared state** between old and new systems:

1. **Keep existing schema** - Both systems read/write the same DB
2. **Add Prisma schema** (for TS) that maps to existing tables
3. **No schema migration needed** initially
4. **Eventually**: Prisma migrations become the source of truth

### Queue Migration

Redis queues are the **integration seam**:

```
Current:  Python (RQ) → Redis queues → Python (RQ workers)
Phase 1:  Python (RQ) → Redis queues → TypeScript (BullMQ workers)
Phase 2:  TypeScript (BullMQ) → Redis queues → TypeScript (BullMQ workers)
```

BullMQ can consume RQ-formatted messages with a thin adapter.

### Test Migration Strategy

1. **Keep Python tests running** during migration (regression safety)
2. **Write new TS tests** for each migrated component
3. **Shared integration tests** against actual DB/Redis
4. **End-to-end tests** that verify pipeline output regardless of implementation

### Rollback Plan

- **Feature flags** control traffic routing
- **Both systems** can run simultaneously
- **Database** is shared - no data migration needed
- **Redis queues** are implementation-agnostic
- **Rollback**: Flip feature flag, old system takes over

---

## 10. Risk Assessment

### High Risk Items

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| **Reconciler logic regression** | Medium | Critical | Extensive integration tests, parallel run |
| **LLM prompt changes** | Low | High | Preserve exact prompts, compare outputs |
| **Geocoding provider differences** | Low | Medium | Same providers via geocoding APIs |
| **Performance regression** | Medium | Medium | Benchmark current system, set SLAs |
| **Data loss during migration** | Low | Critical | Shared DB, no data movement needed |

### Medium Risk Items

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| **HSDS compliance drift** | Medium | Medium | Automated compliance testing |
| **Queue message format changes** | Medium | Medium | Version queue messages, adapter layer |
| **PostGIS query differences** | Low | Medium | Test spatial queries thoroughly |
| **Team learning curve (TS)** | Medium | Medium | Training period, pair programming |

### Low Risk Items

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| **Docker infrastructure changes** | Low | Low | Containerization is language-agnostic |
| **CI/CD pipeline changes** | Low | Low | GitHub Actions supports TS natively |
| **Monitoring gaps** | Low | Low | Prometheus works identically in TS |

---

## 11. Appendix: Agent Inventory

### Phase 1: Component Agents (50 agents)

#### A. API Layer (7 agents)
- **A1**: Main application entry (`main.py`) - FastAPI app setup, middleware stack, lifecycle
- **A2**: Core router (`router.py`) - Route mounting, complex raw SQL queries
- **A3**: Organization endpoints - CRUD operations, pagination
- **A4**: Location endpoints - Geographic queries, export-simple, 805 LOC
- **A5**: Service endpoints - Status filtering, active services
- **A6**: ServiceAtLocation endpoints - Junction entity, bidirectional queries
- **A7**: Map/Consumer API - Map pins, clustering, search, mobile optimization

#### B. Database Layer (4 agents)
- **B1**: Models (`models.py`) - 6 SQLAlchemy models, PostGIS geometry
- **B2**: Repositories (`repositories.py`) - 25+ methods, geographic queries, N+1 issues
- **B3**: Database core (`db.py`) - Async engine, session management
- **B4**: Init scripts - Schema creation, PostGIS, triggers

#### C. LLM Module (6 agents)
- **C1**: Provider base & types - Abstract interface, LLMResponse model
- **C2**: OpenAI provider - Structured output, OpenRouter integration
- **C3**: Claude provider - CLI subprocess, quota management
- **C4**: Schema converter - HSDS alignment prompts, 1,498 LOC
- **C5**: Queue system - RQ integration, job lifecycle
- **C6**: Worker & processor - Job execution, error handling

#### D. Reconciler (6 agents)
- **D1**: Core reconciler - Pipeline orchestration
- **D2**: Job processor - Main processing, 1,568 LOC
- **D3**: Organization creator - Org record management
- **D4**: Location creator - Coordinate matching, address handling
- **D5**: Service creator - Service + schedule + SAL creation, 990 LOC
- **D6**: Merge strategy - Majority voting, field precedence, 740 LOC

#### E. Validator (7 agents)
- **E1**: Service (`validator_service.py`) - Main orchestration
- **E2**: Job processor - Queue consumption, result routing
- **E3**: Confidence scoring - 0-100 deduction system
- **E4**: Enrichment - Geocoding, state correction, 931 LOC
- **E5**: Rules engine - Validation rules, test data detection
- **E6**: Config & queues - ValidatorConfig, Redis queue setup
- **E7**: Scraper context - Source-aware validation rules

#### F. Content Store (3 agents)
- **F1**: Store core - SHA-256 dedup, SQLite + filesystem
- **F2**: Manager - High-level operations, cleanup
- **F3**: Dashboard/CLI - Status display, reporting

#### G. HAARRRvest Publisher (2 agents)
- **G1**: Service - Main publishing logic, 1,669 LOC
- **G2**: Exporters - Map data, aggregated, enhanced formats

#### H. Geocoding (2 agents)
- **H1**: Service & providers - Multi-provider with fallback
- **H2**: Validator & corrector - Coordinate validation, correction

#### I. Scraper (2 agents)
- **I1**: Framework - ScraperJob base, utilities, plugin system
- **I2**: Queue integration - Redis enqueueing, result handling

#### J. Supporting Modules (4 agents)
- **J1**: Core config & events - Settings, app lifecycle
- **J2**: Middleware - Security headers, CORS, correlation, errors
- **J3**: Datasette exporter - SQLite export, 1,181 LOC
- **J4**: Models & types - Geographic, HSDS response

#### K. Infrastructure (4 agents)
- **K1**: Bouy CLI - 2,810 LOC bash, 35+ commands
- **K2**: Docker - 13 services, multi-stage unified image
- **K3**: CI/CD - GitHub Actions + GitLab CI dual pipeline
- **K4**: Project config - pyproject.toml, dependencies, env

#### L. Utility Scripts (2 agents)
- **L1**: DB scripts - 16 migration/fix scripts, 4,565 LOC
- **L2**: Feeding America - Scraper factory, 14 scripts, 3,455 LOC

### Phase 2: Cross-Cutting Pattern Agents (15 agents)

| Agent | Focus | Key Finding |
|-------|-------|-------------|
| **X1** | Data flow: Scrape → Store | Complete pipeline trace documented |
| **X2** | Data flow: LLM → DB | Transformation chain mapped |
| **X3** | Error handling | 250 try/except, 0 bare except, 24 broad Exception |
| **X4** | Configuration | 52+ env vars, Settings/ValidatorConfig duplication |
| **X5** | Testing patterns | 1,787 tests, 9% async, critical middleware gap |
| **X6** | DB queries | 72 patterns, 3 N+1, 1 SQL injection risk |
| **X7** | Auth & security | Strong posture, public API by design |
| **X8** | Redis usage | 4 queues, geocoding cache, circuit breaker |
| **X9** | Pydantic models | 57 models, 95%+ v2, CRUD triple pattern |
| **X10** | Code duplication | 2,400-3,200 duplicated lines, 10 refactoring targets |
| **X11** | Dependencies | 33 prod, 8 unused, dual PG drivers |
| **X12** | Metrics & observability | 16 Prometheus metrics, no distributed tracing |
| **X13** | State management | 3 unsafe singletons, 0 thread locks |
| **X14** | API contract & HSDS | 66% HSDS coverage, core 100%, extended 35% |
| **X15** | Technical debt | 87+ items, ~530 hours total, 4 severity levels |

---

## Conclusion

Pantry Pirate Radio is a **well-conceived system with moderate-high technical debt** accumulated through rapid iteration. The pipeline architecture is sound and should be preserved in any rewrite. The primary issues are:

1. **Monolithic files** that need decomposition (6 files > 900 LOC)
2. **Code duplication** that needs extraction (~2,400-3,200 lines)
3. **Missing test coverage** in critical areas (middleware, integration)
4. **Configuration sprawl** with duplicated settings

A **hybrid strangler fig approach** (Proposal C) is recommended: start with a TypeScript API layer reading from the shared PostgreSQL database, then incrementally migrate pipeline components while the Python system continues running. This approach minimizes risk while providing a clear path to a fully modernized system.

The estimated total effort is **33-45 weeks for a full TypeScript rewrite** or **24-36 weeks for a clean Python rewrite**, with the hybrid approach allowing useful delivery from week 6-8 onward.

---

*Report generated from 65 research agents analyzing ~88,000 lines of code across 135 Python files, 161 test files, and supporting infrastructure.*
