# Pantry Pirate Radio - Comprehensive Codebase Research Plan

## Purpose
Dispatch 60+ research agents to thoroughly document every component, pattern, integration point, and architectural decision in the current codebase. The output will feed into a feasibility analysis for rewriting the application (TypeScript or Python) to a higher standard, with full access to the original source.

---

## PHASE 1: Component-Specific Agents (50 agents)

### A. API Layer (7 agents)

**Agent A1: API Core Router & App Entry**
- Files: `app/main.py`, `app/__init__.py`, `app/api/v1/router.py` (493 lines), `app/api/v1/__init__.py`
- Document: FastAPI app creation, middleware registration, router mounting, CORS config, startup/shutdown events, route organization

**Agent A2: API Locations Endpoint**
- Files: `app/api/v1/locations.py` (805 lines), `app/api/v1/utils.py`
- Document: All location endpoints, query parameters, pagination, filtering, distance calculation, response models, error handling

**Agent A3: API Service-at-Location Endpoint**
- Files: `app/api/v1/service_at_location.py` (363 lines), `app/api/v1/services.py`
- Document: Service-at-location joins, HSDS compliance, search capabilities, query patterns

**Agent A4: API Organizations & Taxonomies**
- Files: `app/api/v1/organizations.py`, `app/api/v1/taxonomies.py`, `app/api/v1/taxonomy_terms.py`
- Document: Organization CRUD, taxonomy system, term management, filtering

**Agent A5: API Map Module**
- Files: `app/api/v1/map/router.py` (782 lines), `app/api/v1/map/services.py` (397 lines), `app/api/v1/map/search_service.py` (512 lines), `app/api/v1/map/models.py`, `app/api/v1/map/__init__.py`
- Document: Map-specific endpoints, geo search, spatial queries, map data models, GeoJSON support

**Agent A6: API Consumer Module**
- Files: `app/api/v1/consumer/router.py`, `app/api/v1/consumer/services.py` (555 lines), `app/api/v1/consumer/models.py`, `app/api/v1/consumer/__init__.py`
- Document: Consumer-facing API, simplified data access, service layer patterns

**Agent A7: API Middleware Stack**
- Files: `app/middleware/correlation.py`, `app/middleware/errors.py`, `app/middleware/metrics.py`, `app/middleware/security.py`
- Document: Request correlation IDs, error handling middleware, Prometheus metrics, security headers/CORS

---

### B. Database Layer (4 agents)

**Agent B1: Database Models & Schema**
- Files: `app/database/models.py` (366 lines), `app/database/__init__.py`
- Document: All SQLAlchemy models, relationships, column types, indexes, constraints, HSDS schema mapping

**Agent B2: Database Repositories**
- Files: `app/database/repositories.py` (799 lines), `app/database/base.py`
- Document: Repository pattern implementation, all query methods, pagination, filtering, base class patterns

**Agent B3: Database Geo Utilities & Migrations**
- Files: `app/database/geo_utils.py`, `app/database/migrations/add_map_search_indexes.py`, `app/database/init_scripts/04_map_search_indexes.sql`
- Document: PostGIS integration, spatial queries, distance calculations, migration patterns, index strategy

**Agent B4: Core Database Connection & Config**
- Files: `app/core/db.py`, `app/core/config.py`, `app/core/events.py` (360 lines), `app/core/logging.py`
- Document: Connection pool management, environment config, startup/shutdown lifecycle, logging setup

---

### C. LLM Module (6 agents)

**Agent C1: LLM Provider Base & Types**
- Files: `app/llm/base.py`, `app/llm/config.py`, `app/llm/__init__.py`, `app/llm/__main__.py`, `app/llm/providers/base.py`, `app/llm/providers/types.py`, `app/llm/providers/__init__.py`
- Document: Provider abstraction, interface contracts, config management, provider selection logic

**Agent C2: OpenAI Provider**
- Files: `app/llm/providers/openai.py` (591 lines)
- Document: OpenAI/OpenRouter integration, structured output, error handling, retry logic, token management

**Agent C3: Claude Provider**
- Files: `app/llm/providers/claude.py` (519 lines), `app/llm/providers/test_mock.py`
- Document: Anthropic API integration, authentication, response parsing, mock provider for testing

**Agent C4: HSDS Schema Aligner**
- Files: `app/llm/hsds_aligner/schema_converter.py` (1498 lines), `app/llm/hsds_aligner/type_defs.py`, `app/llm/hsds_aligner/__init__.py`, `app/llm/hsds_aligner/prompts/food_pantry_mapper.prompt`
- Document: Schema conversion logic, HSDS alignment prompts, type definitions, mapping rules

**Agent C5: LLM Job Queue System**
- Files: `app/llm/queue/models.py`, `app/llm/queue/queues.py`, `app/llm/queue/job.py`, `app/llm/queue/types.py`, `app/llm/queue/__init__.py`, `app/llm/queue/__main__.py`
- Document: Queue models, job definitions, queue configuration, RQ integration

**Agent C6: LLM Workers & Processor**
- Files: `app/llm/queue/worker.py`, `app/llm/queue/claude_worker.py`, `app/llm/queue/processor.py` (326 lines), `app/llm/queue/auth_state.py`, `app/llm/jobs.py`, `app/llm/utils/geocoding_validator.py`
- Document: Worker lifecycle, job processing pipeline, auth state management, geocoding validation in LLM context

---

### D. Reconciler (6 agents)

**Agent D1: Reconciler Core & Base**
- Files: `app/reconciler/reconciler.py`, `app/reconciler/base.py`, `app/reconciler/__init__.py`, `app/reconciler/__main__.py`
- Document: Reconciliation orchestration, base class hierarchy, entry points, overall flow

**Agent D2: Reconciler Job Processor**
- Files: `app/reconciler/job_processor.py` (1568 lines)
- Document: Job processing pipeline, state machine, error handling, retry logic, data transformation steps

**Agent D3: Reconciler Location Creator**
- Files: `app/reconciler/location_creator.py` (778 lines)
- Document: Location record creation, deduplication logic, address normalization, geocoding integration

**Agent D4: Reconciler Organization Creator**
- Files: `app/reconciler/organization_creator.py` (604 lines)
- Document: Organization creation, name matching, proximity-based dedup, source tracking

**Agent D5: Reconciler Service Creator & Merge Strategy**
- Files: `app/reconciler/service_creator.py` (990 lines), `app/reconciler/merge_strategy.py` (740 lines)
- Document: Service record creation, merge conflict resolution, field-level merge rules, priority system

**Agent D6: Reconciler Version Tracking & Metrics**
- Files: `app/reconciler/version_tracker.py`, `app/reconciler/metrics.py`, `app/reconciler/utils.py`
- Document: Version history, change tracking, Prometheus metrics, utility functions

---

### E. Validator Service (7 agents)

**Agent E1: Validator Core & Config**
- Files: `app/validator/base.py`, `app/validator/config.py` (382 lines), `app/validator/__init__.py`, `app/validator/__main__.py`
- Document: Validator service architecture, configuration system, feature flags, thresholds

**Agent E2: Validator Scoring System**
- Files: `app/validator/scoring.py`
- Document: Confidence scoring algorithm, 0-100 scale, scoring factors, weight system

**Agent E3: Validator Rules Engine**
- Files: `app/validator/rules.py` (520 lines)
- Document: All validation rules, rule composition, test data detection, placeholder filtering

**Agent E4: Validator Enrichment**
- Files: `app/validator/enrichment.py` (931 lines)
- Document: Data enrichment pipeline, geocoding integration, field completion, caching strategy

**Agent E5: Validator Job Processing & Routing**
- Files: `app/validator/job_processor.py` (722 lines), `app/validator/routing.py`
- Document: Job processing flow, routing decisions, pass/fail/enrich branching

**Agent E6: Validator Infrastructure**
- Files: `app/validator/queues.py`, `app/validator/worker.py`, `app/validator/health.py`, `app/validator/metrics.py`, `app/validator/database.py`
- Document: Queue setup, worker configuration, health checks, metrics, database interaction

**Agent E7: Validator Scraper Context & Reprocessor**
- Files: `app/validator/scraper_context.py` (345 lines), `app/validator/reprocessor.py` (528 lines)
- Document: Scraper metadata tracking, reprocessing pipeline, batch operations

---

### F. Content Store (3 agents)

**Agent F1: Content Store Core**
- Files: `app/content_store/store.py` (457 lines), `app/content_store/models.py`, `app/content_store/config.py`, `app/content_store/__init__.py`, `app/content_store/__main__.py`
- Document: SHA-256 dedup, storage engine, content models, configuration

**Agent F2: Content Store Monitoring & Dashboard**
- Files: `app/content_store/monitor.py` (371 lines), `app/content_store/dashboard.py` (478 lines), `app/content_store/cli.py`
- Document: Monitoring system, dashboard generation, CLI interface, health reporting

**Agent F3: Content Store Retry & Integration**
- Files: `app/content_store/retry.py`
- Document: Retry mechanisms, failure recovery, integration with scraper and LLM pipelines

---

### G. HAARRRvest Publisher (3 agents)

**Agent G1: Publisher Service Core**
- Files: `app/haarrrvest_publisher/service.py` (1669 lines - LARGEST FILE), `app/haarrrvest_publisher/__init__.py`
- Document: Publishing pipeline, Git operations, data export orchestration, scheduling

**Agent G2: Publisher Map Data Exports**
- Files: `app/haarrrvest_publisher/export_map_data.py` (531 lines), `app/haarrrvest_publisher/export_map_data_aggregated.py` (494 lines), `app/haarrrvest_publisher/export_map_data_enhanced.py` (306 lines)
- Document: Three export strategies, data formatting, GeoJSON generation, aggregation logic

---

### H. Geocoding System (2 agents)

**Agent H1: Geocoding Service & Providers**
- Files: `app/core/geocoding/service.py` (674 lines), `app/core/geocoding/__init__.py`
- Document: Multi-provider geocoding, fallback chains, ArcGIS/Google/Nominatim/Census, rate limiting

**Agent H2: Geocoding Validation & Correction**
- Files: `app/core/geocoding/validator.py` (332 lines), `app/core/geocoding/corrector.py` (404 lines), `app/core/geocoding/constants.py` (323 lines)
- Document: Coordinate validation, 0,0 detection, address correction, state/zip constants

---

### I. Scraper Framework (2 agents)

**Agent I1: Scraper Base Framework**
- Files: `app/scraper/__init__.py`, `app/scraper/__main__.py`, `app/scraper/utils.py` (446 lines)
- Document: ScraperJob base class, utility functions, HTTP helpers, parsing utilities, scraper registration

**Agent I2: Sample Scraper & Scraper Pattern**
- Files: `app/scraper/sample_scraper.py`
- Document: Reference implementation, expected patterns, output format, testing approach

---

### J. Supporting Modules (4 agents)

**Agent J1: Replay System**
- Files: `app/replay/replay.py` (428 lines), `app/replay/__init__.py`, `app/replay/__main__.py`
- Document: Data replay pipeline, JSON file processing, validation routing, dry-run mode

**Agent J2: Recorder System**
- Files: `app/recorder/__init__.py`, `app/recorder/__main__.py`, `app/recorder/utils.py`
- Document: Job result recording, output formatting, directory management

**Agent J3: Datasette Integration**
- Files: `app/datasette/exporter.py` (1181 lines), `app/datasette/cli.py`, `app/datasette/__init__.py`
- Document: SQLite export, Datasette configuration, data viewer setup, export pipeline

**Agent J4: HSDS Data Models**
- Files: `app/models/hsds/organization.py`, `app/models/hsds/location.py`, `app/models/hsds/service.py`, `app/models/hsds/service_at_location.py`, `app/models/hsds/query.py`, `app/models/hsds/response.py`, `app/models/hsds/base.py`, `app/models/hsds/__init__.py`, `app/models/__init__.py`, `app/models/geographic.py`
- Document: HSDS v3.1.1 Pydantic models, query models, response wrappers, geographic models

---

### K. Infrastructure & DevOps (4 agents)

**Agent K1: Bouy CLI Tool**
- Files: `bouy`, `bouy-api`, `bouy-functions.sh`
- Document: CLI architecture, command routing, Docker compose orchestration, all subcommands

**Agent K2: Docker Configuration**
- Files: `.docker/compose/base.yml`, `.docker/compose/docker-compose.dev.yml`, `.docker/compose/docker-compose.prod.yml`, `.docker/compose/docker-compose.test.yml`, `.docker/compose/docker-compose.with-init.yml`, `.docker/compose/docker-compose.dev-with-init.yml`, `.docker/compose/docker-compose.codespaces.yml`, `.docker/compose/docker-compose.github-actions.yml`, `.docker/images/app/Dockerfile`, `.docker/images/datasette/Dockerfile`
- Document: Service definitions, networking, volumes, multi-stage builds, environment modes

**Agent K3: CI/CD & GitHub Configuration**
- Files: `.github/workflows/ci.yml`, `.github/workflows/cd.yml`, `.github/workflows/claude.yml`, `.github/workflows/claude-code-review.yml`, `.gitlab-ci.yml`
- Document: CI pipeline stages, test matrix, deployment process, Claude Code integration, GitLab fallback

**Agent K4: Project Configuration & Dependencies**
- Files: `pyproject.toml`, `pytest.ini`, `.env.example`, `.env.test`, `.env.github-actions`, `configure-poetry.sh`, `.pre-commit-config.yaml`, `.pre-commit-config.docker.yaml`, `.devcontainer/devcontainer.json`, `.devcontainer/Dockerfile`
- Document: All dependencies and versions, Python version, tool configs, dev container setup

---

### L. Utility Scripts (2 agents)

**Agent L1: Database & Data Fix Scripts**
- Files: `scripts/backfill_missing_states.py`, `scripts/backfill_service_at_location.py`, `scripts/fix_bad_zip_codes.py`, `scripts/fix_city_as_location_name.py`, `scripts/fix_state_mismatches.py`, `scripts/fix_state_codes.sql`, `scripts/normalize_state_codes.sql`, `scripts/drop_food_helpline_data.sql`, `scripts/migrate_to_source_records.py`, `scripts/rebuild_content_store_db.py`, `scripts/cleanup-content-store.py`, `scripts/cleanup_content_store_since_date.py`
- Document: Data migration history, fix patterns, what each addresses, manual intervention needs

**Agent L2: Feeding America Scripts & Tooling**
- Files: All `scripts/feeding-america/*.py`, templates, `scripts/list_scrapers.py`, `scripts/generate_state_grids.py`
- Document: Scraper generation workflow, issue integration, priority system, template system

---

## PHASE 2: Cross-Cutting Pattern Agents (15 agents)

**Agent X1: Data Flow - Scrape to Store**
- Trace: Scraper output → Content Store dedup → Redis queue → LLM worker
- Document: Complete data flow, serialization formats, queue payloads, error propagation

**Agent X2: Data Flow - LLM to Database**
- Trace: LLM output → Validator → Reconciler → PostgreSQL → API
- Document: Transformation chain, data shape at each stage, loss/enrichment points

**Agent X3: Error Handling Patterns**
- Search across entire codebase for: try/except patterns, error types, retry logic, fallback chains, error propagation
- Document: Consistency (or lack thereof), custom exceptions, logging patterns, silent failures

**Agent X4: Configuration & Environment Management**
- Analyze: All env vars, config classes, settings objects, feature flags, secrets handling
- Document: Config sprawl, duplication, type safety, validation, defaults

**Agent X5: Testing Patterns & Coverage Gaps**
- Analyze: All test files, conftest.py patterns, fixtures, mocking strategies, test organization
- Document: Coverage distribution, testing anti-patterns, fixture duplication, slow tests

**Agent X6: Database Query Patterns**
- Analyze: All SQLAlchemy usage, raw SQL, query construction, N+1 patterns, join strategies
- Document: Performance concerns, query complexity, pagination approaches, transaction management

**Agent X7: Authentication & Security Patterns**
- Analyze: Claude auth, API key handling, middleware security, CORS, input validation
- Document: Auth mechanisms, security gaps, input sanitization, rate limiting

**Agent X8: Redis Usage Patterns**
- Analyze: All Redis interactions across RQ queues, caching, validator, content store
- Document: Redis as queue vs cache vs state store, key patterns, TTL management, connection handling

**Agent X9: Pydantic Model Patterns**
- Analyze: All Pydantic models across API, HSDS, validator, content store
- Document: Model inheritance, validation rules, serialization patterns, model duplication

**Agent X10: Code Duplication & DRY Violations**
- Analyze: Similar code blocks across modules, repeated patterns, copy-paste evidence
- Document: Specific duplications with file references, refactoring opportunities

**Agent X11: Dependency Analysis**
- Analyze: `pyproject.toml`, all imports, transitive dependencies, version constraints
- Document: Dependency graph, heavy deps, outdated packages, security advisories

**Agent X12: Metrics & Observability**
- Analyze: All Prometheus metrics, logging calls, health checks, monitoring endpoints
- Document: Observable behaviors, metric gaps, logging inconsistencies, alerting capabilities

**Agent X13: State Management & Side Effects**
- Analyze: Global state, singletons, module-level variables, import-time side effects
- Document: Hidden state, initialization order dependencies, testability implications

**Agent X14: API Contract & HSDS Compliance**
- Analyze: OpenAPI spec (`ppr-openapi.json`), HSDS v3.1.1 spec, API examples, response models
- Document: Compliance gaps, custom extensions, breaking changes, versioning strategy

**Agent X15: Technical Debt Inventory**
- Analyze: TODOs, FIXMEs, hacky workarounds, commented-out code, dead code (vulture output), overly complex functions
- Document: Categorized debt inventory with severity, effort estimates, and dependency chains

---

## PHASE 3: Compilation & Feasibility Report

After all agents complete, compile findings into:

1. **Component Summary Matrix** - Each component's purpose, complexity, lines of code, test coverage, debt level
2. **Architecture Diagram** - Data flow, service boundaries, integration points
3. **Technical Debt Catalog** - Prioritized list of issues with severity ratings
4. **Rewrite Feasibility Analysis** - Effort estimation, risk assessment, phasing strategy
5. **Rewrite Proposals** - Concrete proposals for TypeScript and/or Python rewrite approaches
6. **Migration Strategy** - How to incrementally transition with access to original source

---

## Execution Notes

- Total agents: **65** (50 component + 15 cross-cutting)
- All agents are READ-ONLY (Explore type) - no code modifications
- Agents will be dispatched in parallel batches of ~10
- Each agent produces a structured findings document
- Cross-cutting agents run after component agents to reference their findings
