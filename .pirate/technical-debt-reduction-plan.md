# Technical Debt Reduction Plan: Pantry Pirate Radio

## Context

The Pantry Pirate Radio codebase (~88K LOC) has accumulated moderate-high technical debt through rapid iteration. 65 research agents documented the entire system, identifying 87+ debt items totaling ~530 hours. This plan provides a component-by-component, phased execution strategy to systematically reduce that debt while keeping the system running in production. Every item below includes exact file paths, line numbers, and specific code changes derived from 8 deep-exploration agents.

**Guiding principles:**
- Never break production. Run `./bouy test` after every change.
- One component at a time. Complete and verify before moving on.
- Tests first where possible - add missing tests before refactoring.
- Smallest possible PRs - each numbered task below is one commit.

---

## Phase 0: Critical Fixes (Day 1 - immediate safety)

These 4 items are bugs or security risks that should be fixed before any refactoring begins.

### 0.1 Remove debug print statement in production
- **File:** `app/llm/queue/processor.py:87-88`
- **Current:** `print(f"DEBUG: Job {job.id} metadata: {job.metadata}")` + redundant `logger.warning()`
- **Fix:** Delete line 87 (the print). Change line 88 from `logger.warning` to `logger.debug`.

### 0.2 Fix SQL injection risk in search service
- **File:** `app/api/v1/map/search_service.py:316-332`
- **Current:** `where_clause` built via string concatenation of conditions list, with `# nosec B608` suppression comments.
- **Fix:** While individual conditions already use parameterized `:param` placeholders (so actual injection risk is low), refactor to use SQLAlchemy `text()` with explicit `bindparams()` to eliminate the concatenation pattern entirely. Remove `nosec B608` comments.

### 0.3 Fix scraper_context always-true state boundary check
- **File:** `app/validator/scraper_context.py:344-345`
- **Current:** `return True` unconditionally with `# TODO: Implement proper state boundary checking`
- **Fix:** Implement actual state bounds checking by calling `GeocodingValidator.is_within_state_bounds()` for each state in the scraper's region list. If no states defined, keep returning True.

### 0.4 Fix N+1 queries - re-enable schedule eager loading
- **File:** `app/database/repositories.py:214-215, 231-232, 382-383`
- **Current:** `# selectinload(self.model.schedules)` commented out with "async loading issues"
- **Fix:** Re-enable `selectinload(self.model.schedules)` in all three locations. If async greenlet issues persist, implement a separate batch query method `_batch_load_schedules(location_ids)` using `select(ScheduleModel).where(ScheduleModel.location_id.in_(ids))`.

---

## Phase 1: Reconciler Module (highest debt - ~24-28 hours)

The reconciler has the most concentrated debt: a 1,568-line monolithic file, 80+ lines of triplicated retry logic, and weak typing throughout.

### 1.1 Extract shared retry logic from creators
- **Files:** `app/reconciler/location_creator.py:20-57`, `app/reconciler/organization_creator.py:280-323`, `app/reconciler/service_creator.py:192-230`
- **Action:** Create `app/reconciler/retry_utils.py` with a single `retry_with_backoff()` function. Extract `_log_constraint_violation()` alongside it. Update all 3 creators to import from this shared module. Remove the duplicated methods.
- **Eliminates:** ~80 lines of exact duplication across 3 files.

### 1.2 Create domain exception hierarchy
- **Action:** Create `app/reconciler/exceptions.py` with: `ReconcilerError` (base), `JSONParseError`, `HSDataValidationError`, `ConstraintViolationError`, `RowConversionError`.
- **Then update:** Replace 4 broad `except Exception` catches in `job_processor.py:53,330` and `merge_strategy.py:101,186` with specific exception types.

### 1.3 Extract constants from inline code
- **Action:** Create `app/reconciler/constants.py` containing:
  - `STATE_DEFAULT_POSTAL_CODES` dict (currently hardcoded at `location_creator.py:559-611`, 53 entries inline)
  - Retry configuration constants (`BASE_DELAY=0.1`, `BACKOFF_MULTIPLIER=2.0`, `MAX_ATTEMPTS=3`)
  - Validation status strings (`REJECTED`, `ACCEPTED`)
  - Phone placeholder values set
- **Then update:** All files to import from constants.

### 1.4 Decompose job_processor.py (1,568 LOC → 5 files)
This is the largest single refactoring. Execute in sub-steps:

#### 1.4a Extract JSON parser
- **From:** `job_processor.py:255-385`
- **To:** `app/reconciler/parsers/hsds_parser.py` - class `HSDataParser` with methods `parse_job_result_text()`, `_extract_json_from_markdown()`, `_validate_hsds_structure()`.

#### 1.4b Extract organization processor
- **From:** `job_processor.py:406-658`
- **To:** `app/reconciler/processors/organization_processor.py` - class `OrganizationProcessor` with `process_organizations()`, `_extract_validation_data_for_org()`, `_extract_coordinates_for_proximity()`.

#### 1.4c Extract location processor
- **From:** `job_processor.py:659-1050`
- **To:** `app/reconciler/processors/location_processor.py` - class `LocationProcessor` with `process_locations()`, `_extract_validation_data_for_location()`, `_should_reject_location()`.

#### 1.4d Extract service processor
- **From:** `job_processor.py:1051-1450`
- **To:** `app/reconciler/processors/service_processor.py` - class `ServiceProcessor` with `process_services()`, phone and schedule processing.

#### 1.4e Refactor job_processor as coordinator
- **Result:** `process_job_result()` becomes ~40 LOC orchestrating the 4 extracted classes.

### 1.5 Standardize return types (UUID vs str)
- **Files:** `organization_creator.py:144` (returns UUID), `service_creator.py:190` (returns str), `location_creator.py:358` (returns str)
- **Fix:** Standardize all creator methods to return `UUID`. Wrap `str` returns with `uuid.UUID()`.

### 1.6 Fix logging inconsistencies
- **File:** `job_processor.py:29,172` has both module-level AND instance-level loggers.
- **Fix:** Remove module-level `logger = logging.getLogger(__name__)` at line 29. Keep only instance-level loggers inherited from base class pattern.
- **Also:** In `merge_strategy.py:94,102,131`, change `logger.error(f"...")` to `logger.exception("...")` for stack trace capture.

### 1.7 Add missing test coverage
- **Location:** `tests/test_reconciler/`
- **Add tests for:**
  - `_transform_schedule()` - 6 test cases (times array, start/end time, ONCE→WEEKLY conversion, invalid frequency, missing freq, missing wkst)
  - `merge_strategy._row_to_dict` edge cases - UUID string detection, single non-iterable, fallback zip
  - `location_creator.create_address` state validation - invalid state too long, non-alpha, uppercase normalization, default postal codes

### 1.8 Remove deprecated method
- **File:** `job_processor.py:174-180` - `process_completed_jobs()` with docstring "This method is no longer needed"
- **Fix:** Delete the method entirely.

---

## Phase 2: HAARRRvest Publisher Module (~80-100 hours)

The publisher has the largest single file (1,669 LOC) and 85% code duplication across 3 exporter classes.

### 2.1 Extract base exporter class to eliminate duplication
- **Files:** `app/haarrrvest_publisher/export_map_data.py` (531 LOC), `export_map_data_aggregated.py` (494 LOC), `export_map_data_enhanced.py` (306 LOC)
- **Action:** Create `app/haarrrvest_publisher/exporters/base_exporter.py` containing:
  - `_get_connection_string()` (currently duplicated 3x at lines 29-45 in each file)
  - `__init__(data_repo_path, pg_conn_string)` (duplicated 3x)
  - `_generate_state_files()` (duplicated between map_data and aggregated)
  - `_print_summary()` using logger (not print())
  - `export()` template method pattern
- **Then:** Refactor each exporter to inherit from `BaseMapDataExporter`, keeping only their unique query/format logic.
- **Eliminates:** ~350 lines of duplication.

### 2.2 Replace print() statements with logger
- **File:** `export_map_data_enhanced.py:271-277` - 6 `print()` calls
- **File:** `export_map_data.py:445-510` - mixed print/logger in `_print_summary()`
- **File:** `export_map_data_aggregated.py:449-472` - similar mixed approach
- **Fix:** Replace all with `logger.info()` calls.

### 2.3 Centralize database configuration
- **Current:** `POSTGRES_*` env vars read independently in `service.py:745,961` AND in each exporter file (lines 31-35, 45-61).
- **Action:** Create `app/haarrrvest_publisher/database_config.py` with single `DatabaseConfig.get_connection_string()`. Update all 4 files to use it.

### 2.4 Add error checking to git operations
- **File:** `service.py` - 8+ locations where `_run_command()` return code is ignored:
  - Lines 364-371: git config commands (2x)
  - Lines 376-383: git config commands in update path (2x)
  - Line 830: git add -A
  - Lines 848-850: git commit
  - Line 853: git checkout main
  - Lines 854-857: git merge
- **Fix:** For each, capture return code and raise `GitOperationError` on non-zero. Create custom `GitOperationError` exception class.

### 2.5 Decompose service.py (1,669 LOC → 5 focused modules)

#### 2.5a Extract GitClient class
- **From:** `service.py:130-898` (~520 LOC, 15 methods)
- **To:** `app/haarrrvest_publisher/git_client.py`
- **Contains:** `_run_command()`, `_get_authenticated_url()`, `_setup_git_repo()`, `_create_and_merge_branch()`, `_safe_git_stash_with_content_store_protection()`, `_maintain_shallow_clone()`, `_check_and_cleanup_repository()`, `_perform_deep_cleanup()`.

#### 2.5b Extract StateManager class
- **From:** `service.py:90-128` (~40 LOC)
- **To:** `app/haarrrvest_publisher/state_manager.py`
- **Contains:** `_load_processed_files()`, `_save_processed_files()`, plus schema versioning for future-proofing.

#### 2.5c Extract DatabaseExporter class
- **From:** `service.py:899-1318` (~420 LOC)
- **To:** `app/haarrrvest_publisher/database_exporter.py`
- **Contains:** `_export_to_sqlite()`, `_export_to_sql_dump()`, `_cleanup_old_dumps()`, `_sync_database_from_haarrrvest()`, plus ratchet logic.

#### 2.5d Extract ContentStoreManager class
- **From:** `service.py:148-224` (~90 LOC)
- **To:** `app/haarrrvest_publisher/content_store_manager.py`
- **Contains:** `_get_content_store_stats()`, `_verify_content_store_integrity()`, `_safe_git_stash_with_content_store_protection()`.

#### 2.5e Refactor service.py as orchestrator
- **Result:** `HAARRRvestPublisher` delegates to GitClient, StateManager, DatabaseExporter, ContentStoreManager. Remains ~300 LOC with `run()`, `process_once()`, scheduling.

### 2.6 Fix silent SQL dump failure
- **File:** `service.py:1165-1168`
- **Current:** `except Exception as e:` with "Don't fail the entire pipeline if SQL dump fails"
- **Fix:** Differentiate transient vs permanent failures. Log at `ERROR` level (not warning). Track failure count in metrics.

### 2.7 Add publisher test coverage
- **Current:** Only `test_confidence_export.py` (317 lines, 4 tests) - covers only `MapDataExporter.export()`
- **Missing:** HAARRRvestPublisher class, GitClient operations, DatabaseExporter, ratchet logic, AggregatedMapDataExporter, EnhancedMapDataExporter.
- **Add:** `test_git_client.py`, `test_database_exporter.py`, `test_state_manager.py`, `test_aggregated_exporter.py`, `test_enhanced_exporter.py`.

---

## Phase 3: LLM Module (~30 hours)

### 3.1 Fix Redis connection blocking at import time
- **File:** `app/llm/queue/queues.py:15-34`
- **Current:** `redis_client.ping()` at module level blocks import for 5 seconds if Redis unavailable, then raises (killing the process).
- **Fix:** Replace with lazy initialization pattern. Create `LazyRedisConnection` class with `get()` classmethod that initializes on first use. Move `redis_pool` creation inside `get()`.

### 3.2 Decompose schema_converter.py (1,498 LOC → 4 files)

#### 3.2a Extract schema builder
- **From:** `schema_converter.py:1-500` (constants, SchemaField, validation)
- **To:** `app/llm/hsds_aligner/schema_builder.py`

#### 3.2b Extract schema loader
- **From:** `schema_converter.py:1034-1303` (JSON/CSV file loading)
- **To:** `app/llm/hsds_aligner/schema_loader.py`

#### 3.2c Extract schema formatters
- **From:** `schema_converter.py:950-1033, 1305-1498` (output wrapping)
- **To:** `app/llm/hsds_aligner/schema_formatters.py`

#### 3.2d Fix double schema wrapper (Debt #13)
- **File:** `schema_converter.py:1002-1032`
- **Current:** Returns `{"type": "json_schema", "json_schema": {"schema": actual_schema}}` - double nesting.
- **Fix:** Return provider-agnostic `SchemaConversionResult(schema, name, description)` dataclass. Move OpenAI-specific wrapping to `providers/openai.py`.

### 3.3 Add subprocess timeout to Claude provider
- **File:** `app/llm/providers/claude.py:456-487`
- **Current:** `await process.communicate()` with no timeout - can hang indefinitely.
- **Fix:** Wrap with `asyncio.wait_for(process.communicate(), timeout=60)`. On timeout, `process.kill()` and raise `TimeoutError`.

### 3.4 Consolidate Claude error imports
- **File:** `app/llm/queue/processor.py:147-151, 281-326`
- **Current:** `from app.llm.providers.claude import ClaudeQuotaExceededException` imported inside try blocks twice.
- **Fix:** Move imports to module top level. Restructure retry loop to separate Claude-specific and generic error handling.

### 3.5 Extract shared provider utilities
- **Action:** Create `app/llm/providers/common.py` with `StructuredOutputFormatter.extract_json_from_markdown()` and `ErrorExtractor.extract_message()`.
- **Reduces:** ~25% duplication between OpenAI and Claude providers.

### 3.6 Add LLM test coverage
- **Missing tests for:** Redis connection at import time, Claude subprocess timeout, error recovery and retry logic, double-wrapped schema unwrapping, provider error handling.

---

## Phase 4: Validator Module (~35 hours)

### 4.1 Remove print statements from reprocessor
- **File:** `app/validator/reprocessor.py:520-524` - 5 `print()` statements
- **Fix:** Replace with `logger.info()`.

### 4.2 Extract scoring constants
- **File:** `app/validator/scoring.py`
- **Action:** Create `ScoringConstants` class at top of file with all magic numbers:
  - `STARTING_SCORE = 100`
  - `DEDUCTION_NO_COORDINATES = 100`, `DEDUCTION_ZERO_COORDINATES = 100`
  - `DEDUCTION_OUTSIDE_US = 95`, `DEDUCTION_TEST_DATA = 95`
  - `DEDUCTION_PLACEHOLDER = 75`, `DEDUCTION_WRONG_STATE = 20`
  - `DEDUCTION_CENSUS_GEOCODER = 10`, `DEDUCTION_FALLBACK_GEOCODING = 15`
  - `DEDUCTION_MISSING_POSTAL = 5`, `DEDUCTION_MISSING_CITY = 10`
  - `VERIFIED_THRESHOLD = 80`

### 4.3 Consolidate ValidatorConfig with Settings
- **Files:** `app/validator/config.py:1-106` (ValidatorConfig dataclass) and `app/core/config.py:70-152` (Settings)
- **Duplicated fields:** `enabled`, `queue_name`, `redis_ttl`, `log_data_flow`, `only_hsds`, `confidence_threshold`
- **Fix:** Remove ValidatorConfig dataclass entirely. Create `ValidatorConfigAccessor` class that reads directly from Settings. Update `get_validator_config()` to return Settings values directly.

### 4.4 Decompose enrichment.py (931 LOC → 5 classes)
- **From:** `app/validator/enrichment.py` - `GeocodingEnricher` class with 17 methods
- **To:**
  - `enrichment/cache_manager.py` - Redis operations (`_get_cache_key`, `_get_cached_coordinates`, `_cache_coordinates`)
  - `enrichment/circuit_breaker.py` - Provider failure tracking (`_is_circuit_open`, `_record_circuit_failure`, `_reset_circuit_breaker`)
  - `enrichment/geocoding_provider.py` - Geocoding logic (`_geocode_with_retry`, `_geocode_missing_coordinates`, `_reverse_geocode_missing_address`)
  - `enrichment/state_validator.py` - State/ZIP correction (`_correct_state_mismatches`)
  - `enrichment/enricher.py` - Orchestrator (now ~150 LOC)

### 4.5 Remove emoji logging prefixes
- **File:** `app/validator/enrichment.py:101-290`
- **Current:** Uses emoji prefixes like `"🌟 ENRICHER"`, `"✅ ENRICHER"`, `"❌ ENRICHER"` in log messages.
- **Fix:** Replace with standard logging levels: `logger.debug()`, `logger.info()`, `logger.error()`.

### 4.6 Add missing validator tests
- **Missing:** `is_address_in_scraper_region()` tests, circuit breaker state transitions, Redis failure scenarios, geocoding timeout handling, large batch enrichment behavior.

---

## Phase 5: Database & API Layer (~30 hours)

### 5.1 Centralize database connection configuration
- **Current:** DATABASE_URL parsed/converted in 4+ files: `app/core/db.py:26-35`, `app/api/v1/router.py:467`, `app/database/migrations/add_map_search_indexes.py`, `app/datasette/exporter.py`
- **Action:** Create `app/core/database_config.py` with `DatabaseConfig` class offering `async_url`, `sync_url`, `_to_async_url()`. Update all 4 files to use it.

### 5.2 Extract pagination helper
- **Current:** Pagination pattern duplicated 13+ times across `organizations.py`, `locations.py`, `services.py`, `service_at_location.py`.
- **Action:** Create `app/api/v1/pagination.py` with `async def get_paginated_response(request, repository, page, per_page, filters, extra_params)`. Refactor all endpoints to use it.
- **Eliminates:** ~200-250 lines of duplication.

### 5.3 Fix type: ignore comments in database models
- **File:** `app/database/models.py` - 6 `type: ignore[assignment]` comments (lines 56, 106, 115, 196, 211, 350)
- **Root cause:** SQLAlchemy Enum column type doesn't match `Column[str]` annotation.
- **Fix:** Use `Mapped[str]` with SQLAlchemy 2.0 mapped column pattern instead of legacy `Column[str]`.

### 5.4 Add missing database indexes
- **File:** `app/database/models.py`
- **Add:**
  - `Index('idx_location_organization_id', LocationModel.organization_id)`
  - `Index('idx_location_coordinates', LocationModel.latitude, LocationModel.longitude)`
  - `Index('idx_service_organization_id', ServiceModel.organization_id)`
  - `Index('idx_schedule_service_id', ScheduleModel.service_id)`
  - `UniqueConstraint('service_id', 'location_id', name='uq_service_at_location')` on ServiceAtLocationModel

### 5.5 Fix async session lifecycle
- **File:** `app/core/db.py:54-70`
- **Current:** Session closed in `finally` but no rollback on exception.
- **Fix:** Add `except Exception: await session.rollback(); raise` before the `finally` block.
- **Also:** Add `pool_pre_ping=True` to engine creation at line 37 for stale connection detection.

### 5.6 Standardize API error responses
- **Action:** Create `app/api/v1/errors.py` with `ErrorResponse(BaseModel)` containing `status_code`, `error_code` (string enum), `message`, `details`, `correlation_id`. Update error middleware to use this format. Update all HTTPException(404) raises to include structured error codes.

### 5.7 Consolidate Consumer/Map API response models
- **Files:** `app/api/v1/consumer/models.py` and `app/api/v1/map/models.py`
- **Both define:** location detail with id, lat, lng, name, org, address, city, state, sources, confidence_score.
- **Fix:** Create shared `LocationDetail` model in `app/models/hsds/response.py`. Both APIs import from there.

### 5.8 Add middleware tests
- **Current:** 0 dedicated middleware tests.
- **Add:** `tests/middleware/test_correlation.py`, `test_error_handling.py`, `test_metrics.py`, `test_security_headers.py` covering: correlation ID generation/propagation, error format, security headers presence, CORS preflight.

### 5.9 Convert simple raw SQL to ORM
- **Targets:** `map/router.py:613-625` (statistics query), `locations.py:102-125` (source info), `map/router.py:488-517` (location detail).
- **Keep as raw SQL:** Complex CTEs in `router.py:67-163`, `map/search_service.py:58-124`, `map/router.py:344-359`.

---

## Phase 6: Geocoding Module (~20 hours)

### 6.1 Consolidate coordinate validation into single module
- **Current duplication (4 locations):**
  - `app/core/geocoding/validator.py:124-131` - `is_valid_coordinates()`
  - `app/database/geo_utils.py:140-146` - `validate_coordinates()`
  - `app/core/geocoding/corrector.py:78-79,90-91` - inline zero/range checks
  - `app/validator/rules.py:80-126` - `check_coordinates_present()`, `check_zero_coordinates()`
- **Action:** Create `app/core/geocoding/coordinate_utils.py` with single `CoordinateValidator` class offering `is_valid()`, `is_zero()`, `is_within_us()`, `is_within_state()`. Update all 4+ files to import from this single source.

### 6.2 Unify geocoding cache implementations
- **Two caches with conflicting behavior:**
  - `service.py:155-225`: Key `geocode:{provider}:{full_hash}`, TTL 30 days
  - `enrichment.py:801-859`: Key `geocoding:{provider}:{hash[:16]}`, TTL 24 hours
- **Action:** Create `app/core/geocoding/cache.py` with single `GeocodeCache` class. Standardize on: namespace `geocode:`, full SHA-256 hash, configurable TTL (default 24h).

### 6.3 Extract shared circuit breaker
- **Currently:** Full circuit breaker only in `enrichment.py:695-733`. Service.py has none.
- **Action:** Create `app/core/circuit_breaker.py` with reusable `CircuitBreaker` class. Use in both geocoding service and enrichment module.

### 6.4 Fix conflicting rate limit configurations
- **Conflict:** `service.py:68,121` says 0.5s delay (2 req/sec), `config.py:128-151` says 100 req/sec for ArcGIS.
- **Fix:** Remove hardcoded defaults from `service.py`. Read all rate limits from `Settings` (app/core/config.py) as single source of truth.

### 6.5 Add Census provider to main fallback chain
- **File:** `service.py:299-325` - Only ArcGIS → Nominatim in fallback.
- **But:** `enrichment.py:407-450` uses all 3 providers (ArcGIS → Nominatim → Census).
- **Fix:** Add Census as third provider in `service.py` fallback chain for consistency.

---

## Phase 7: Content Store (~10 hours)

### 7.1 Fix broad exception handling
- **File:** `app/content_store/store.py:95-97, 379-381`
- **Current:** `except Exception:` catches everything including `SystemExit`, `KeyboardInterrupt`.
- **Fix:** Replace with `except (sqlite3.OperationalError, FileNotFoundError, json.JSONDecodeError) as e:`.

### 7.2 Fix non-unique job IDs in scraper queue integration
- **File:** `app/scraper/utils.py:237`
- **Current:** `id=str(datetime.now().timestamp())` - collisions possible within same second.
- **Fix:** `id=str(uuid.uuid4())`.

### 7.3 Add Pydantic config validation
- **File:** `app/content_store/config.py:43-44`
- **Current:** Manual env var parsing with inconsistent boolean detection.
- **Fix:** Replace with Pydantic `BaseSettings` class with proper type validation.

### 7.4 Fix content store error recovery on enqueue failure
- **File:** `app/scraper/utils.py:278-295`
- **Current:** If RQ enqueue fails after content store marks entry as "pending", no rollback occurs.
- **Fix:** Add try/except around enqueue. On failure, call `content_store.clear_job_id(entry.hash)` to reset status.

---

## Phase 8: Scraper Framework (~8 hours)

### 8.1 Add scraper ID validation
- **File:** `app/scraper/utils.py:388-399` (ScraperJob.__init__)
- **Fix:** Add regex validation for `scraper_id` format (lowercase alphanumeric + hyphens/underscores).

### 8.2 Add lifecycle hooks to ScraperJob
- **File:** `app/scraper/utils.py:385-447`
- **Add:** `async before_scrape()`, `async after_scrape(content, job_id)`, `async on_error(exception)` hook methods (no-op by default, subclasses can override).

### 8.3 Add scraper class validation in loader
- **File:** `app/scraper/__main__.py:21-74` (load_scraper_class)
- **Current:** No check that loaded class inherits from ScraperJob.
- **Fix:** After loading, verify `issubclass(cls, ScraperJob)` before returning.

### 8.4 Remove unused GeocoderUtils parameters
- **File:** `app/scraper/utils.py:306-321`
- **Current:** `__init__` accepts `timeout` and `max_retries` but ignores them.
- **Fix:** Remove the parameters. Add deprecation comment if backward compatibility needed.

---

## Phase 9: Core Config, Middleware & Shared Patterns (~25 hours)

### 9.1 Consolidate print statements codebase-wide
- **Verified count:** 110 `print()` calls across 13 files in `app/`:
  - `app/content_store/cli.py` (21), `app/content_store/__main__.py` (18), `app/haarrrvest_publisher/export_map_data.py` (16), `app/haarrrvest_publisher/export_map_data_aggregated.py` (11), `app/claude_auth_manager.py` (8), `app/scraper/__main__.py` (8), `app/content_store/monitor.py` (6), `app/haarrrvest_publisher/export_map_data_enhanced.py` (4), `app/validator/reprocessor.py` (4), `app/claude_health_server.py` (3), `app/content_store/dashboard.py` (2), `app/core/grid.py` (2), `app/llm/queue/processor.py` (1)
- **Action:** Replace each with appropriate `logger.info()`, `logger.debug()`, or `logger.warning()` call. CLI-facing files (`cli.py`, `__main__.py`) may use `click.echo()` instead where interactive output is intended.

### 9.2 Create shared queue abstraction
- **Current:** Queue setup duplicated between `app/llm/queue/queues.py` and `app/validator/queues.py` with identical patterns: lazy initialization, configuration builders, health checking, Redis connection handling.
- **Action:** Create `app/core/queue/base.py` with `QueueManager` class offering `get_queue(name)`, `create_queue(name, config)`, `check_health()`. Both LLM and Validator queue modules become thin wrappers.

### 9.3 Fix module-level singletons (3 verified locations)
- **Singleton 1:** `app/core/db.py:11-12` - `engine = None; async_session_factory = None` - database initialization without asyncio.Lock. **Fix:** Add `_db_init_lock = asyncio.Lock()` and wrap `_initialize_database()` with `async with _db_init_lock:`.
- **Singleton 2:** `app/core/geocoding/service.py:661-674` - `_geocoding_service = None` with classic non-thread-safe `get_geocoding_service()`. **Fix:** Replace with `@functools.lru_cache(maxsize=1)` decorator.
- **Singleton 3:** `app/llm/queue/auth_state.py:23-184` - `AuthStateManager` holds Redis state without coordination. **Fix:** Add Redis-based distributed locking for `set_auth_failed()` operations.

### 9.4 Remove unused dependencies (8 verified unused)
- **File:** `pyproject.toml`
- **Confirmed unused (0 imports found):** pdfplumber, pdf2image, pytesseract, marshmallow, xlrd, pyjwt, demjson3, db-to-sqlite. Remove all 8.
- **Dual PostgreSQL drivers:** psycopg (v3, used by `app/core/db.py`) and psycopg2-binary (v2, used by 5 HAARRRvest exporter files + `datasette/exporter.py`). Migrate exporters to psycopg v3, then remove psycopg2-binary.

### 9.5 Decompose Datasette exporter (1,181 LOC)
- **File:** `app/datasette/exporter.py`
- **Decompose into 5 files:**
  - `postgres_views.py` (~200 LOC) - `create_postgres_materialized_views()` (lines 25-200)
  - `sqlite_schema.py` (~200 LOC) - `get_table_schema()`, `create_sqlite_table()`, `postgres_to_sqlite_type()` (lines 367-573)
  - `sqlite_data.py` (~150 LOC) - `export_table_data()`, `insert_batch()`, `convert_value()` (lines 256-365, 617-650)
  - `datasette_metadata.py` (~150 LOC) - `add_datasette_metadata()`, `create_datasette_views()` (lines 793-1040)
  - `exporter.py` (~120 LOC) - orchestrator only
- **Also delete:** `create_datasette_views_old()` (lines 887-1040) - dead legacy code confirmed by "DEPRECATED" comment at line 889.

### 9.6 Add missing explicit dependencies (3 verified)
- **click** - imported by `app/content_store/cli.py:4` and `app/datasette/cli.py:6`
- **flask** - imported by `app/content_store/dashboard.py:11`
- **requests** - imported by `app/core/geocoding/service.py:19`
- **Action:** Add `click = "^8.0"`, `flask = "^3.0"`, `requests = "^2.31"` to `pyproject.toml`.

### 9.7 Add Content-Security-Policy header
- **File:** `app/middleware/security.py:21-26`
- **Current headers:** X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Strict-Transport-Security
- **Missing:** Content-Security-Policy, Referrer-Policy, Permissions-Policy
- **Fix:** Add `"Content-Security-Policy": "default-src 'self'"`, `"Referrer-Policy": "strict-origin-when-cross-origin"`, `"Permissions-Policy": "geolocation=(), camera=(), microphone=()"`.

### 9.8 Fix middleware error handler dead code
- **File:** `app/middleware/errors.py`
- **Lines 50-80:** `handle_404()` and `handle_405()` are registered but never called (middleware dispatch catches exceptions in try/except before they reach these handlers).
- **Lines 95-99:** Duplicate `error_type = exc.__class__.__name__` assignment.
- **Fix:** Remove unused handlers. Deduplicate error type extraction.

### 9.9 Record request duration to Prometheus histogram
- **File:** `app/middleware/metrics.py:61-63`
- **Current:** Request duration measured in memory but never exported to Prometheus.
- **Fix:** Create `REQUEST_DURATION_SECONDS = Histogram(...)` and call `.observe(duration)`.

### 9.10 Fix logging configuration to respect settings
- **File:** `app/core/logging.py:41-50`
- **Current:** Hard-coded `INFO` level ignoring `settings.LOG_LEVEL`.
- **Fix:** Read `settings.LOG_LEVEL` and apply to root and app loggers.

### 9.11 Implement proper job processor shutdown
- **File:** `app/core/events.py:334-336`
- **Current:** `logger.info("Stopping job processor...")` then `logger.info("Job processor stopped")` - no actual shutdown code.
- **Fix:** Add worker cancellation, pending job draining, and `await asyncio.wait_for(shutdown(), timeout=10)`.

---

## Phase 10: Cross-cutting Cleanup (~15 hours)

### 10.1 Replace hardcoded magic numbers with named constants
- Audit all timeout values, retry counts, threshold numbers, port numbers appearing inline across `app/`.
- Create per-module `constants.py` files (already done for reconciler in Phase 1.3).

### 10.2 Remove dead code and TODOs
- Clean up TODO/FIXME comments that reference completed work.
- Delete deprecated methods without `@deprecated` decorator.
- Remove commented-out code blocks.

### 10.3 Standardize logging across modules
- Ensure all modules use `structlog` or `logging.getLogger(__name__)` consistently.
- Remove all emoji prefixes from log messages.
- Ensure `logger.exception()` is used (not `logger.error(f"...{e}")`) for exception logging to capture stack traces.

---

## Verification Strategy

After each phase:

1. **Run full test suite:** `./bouy test` (pytest + mypy + black + ruff + bandit)
2. **Run specific component tests:** `./bouy test --pytest tests/test_<component>/`
3. **Check type safety:** `./bouy test --mypy app/<component>/`
4. **Check formatting:** `./bouy test --black app/<component>/`
5. **Check for regressions:** Compare API responses before/after for key endpoints
6. **Verify no import cycles:** Run application startup: `./bouy up` and check logs

For the critical fixes in Phase 0:
- **0.1:** Verify no print() output in `./bouy logs app` during job processing
- **0.2:** Run `./bouy test --bandit` and confirm no B608 warnings
- **0.3:** Write test that verifies out-of-state coordinates are rejected
- **0.4:** Verify schedule data loads in single query using `./bouy test --pytest -- -v -k schedule`

---

## Execution Summary

| Phase | Component | Tasks | Est. Hours | Priority |
|-------|-----------|-------|------------|----------|
| **0** | Critical Fixes | 4 | 4 | P0 - Immediate |
| **1** | Reconciler | 8 | 24-28 | P1 - Week 1-2 |
| **2** | Publisher | 7 | 40-50 | P1 - Week 2-4 |
| **3** | LLM Module | 6 | 25-30 | P1 - Week 3-5 |
| **4** | Validator | 6 | 30-35 | P2 - Week 4-6 |
| **5** | Database & API | 9 | 25-30 | P2 - Week 5-7 |
| **6** | Geocoding | 5 | 15-20 | P2 - Week 6-8 |
| **7** | Content Store | 4 | 8-10 | P3 - Week 7-8 |
| **8** | Scraper Framework | 4 | 6-8 | P3 - Week 8-9 |
| **9** | Core/Config/Shared/Infra | 11 | 30-38 | P3 - Week 8-11 |
| **10** | Cross-cutting Cleanup | 3 | 10-15 | P4 - Week 11-12 |
| | **TOTAL** | **67 tasks** | **~217-268 hrs** | **~12 weeks** |
