## Amendment Log

*No amendments yet. This is the initial ratification.*

# Pantry Pirate Radio Constitution

## Core Principles

### I. Docker-First Development (NON-NEGOTIABLE)

All development, testing, and execution commands MUST use the `./bouy` CLI exclusively. Developers MUST NOT install local Python, PostgreSQL, Redis, or other runtime dependencies. The only local prerequisite SHALL be Docker and Docker Compose.

- Direct `docker compose`, `poetry run`, `pytest`, or `python` commands MUST NOT be used outside of bouy
- New commands MUST be added to bouy, never as standalone scripts requiring local dependencies
- CI/CD pipelines MUST use the same bouy commands that developers use locally
- Pre-commit hooks MUST execute through Docker containers via bouy

**Rationale**: Docker-first development eliminates "works on my machine" problems and ensures perfect environment parity between development, CI, and production. This project has 90+ scrapers developed across contributors with varied setups. The bouy wrapper is the single interface that guarantees consistent behavior. Allowing local-dependency shortcuts creates a two-class system where some contributors can test differently than others, introducing subtle environment-dependent bugs in a pipeline that serves vulnerable communities.

---

### II. HSDS Specification Compliance (NON-NEGOTIABLE)

All data output MUST conform to the OpenReferral Human Services Data Specification (HSDS).

- Pydantic models in `app/models/hsds/` MUST be the canonical schema definition
- SQLAlchemy models in `app/database/models.py` MUST mirror HSDS Pydantic models structurally
- API responses MUST validate against HSDS schema before delivery
- New data fields MUST NOT be invented; they MUST map to HSDS entities (Organization, Service, Location, Service_at_Location, Address, Schedule, Phone, Language, Service_Area, Accessibility)
- The HSDS submodule (`docs/HSDS/`) MUST be the authoritative schema reference
- HSDS version changes MUST be treated as major version bumps requiring migration planning

**Rationale**: HSDS compliance is what makes this project interoperable with the broader human services ecosystem. The HAARRRvest publisher distributes data publicly. Downstream consumers (211 services, food bank networks, community organizations) depend on HSDS-conformant data. Schema drift or custom field additions create silent data loss when consumers parse our output. This is data that connects hungry people to food -- correctness is not optional.

---

### III. Test-Driven Development (NON-NEGOTIABLE)

Tests MUST be written before implementation code. The Red-Green-Refactor cycle is mandatory:

1. Write tests that define desired behavior
2. Verify tests fail (Red)
3. Implement minimum code to pass tests (Green)
4. Refactor while keeping tests green

- All tests MUST run through `./bouy test --pytest` (never local pytest)
- Pull requests without corresponding tests SHALL NOT be merged
- Code coverage MUST NOT regress (enforced by ratcheting mechanism with 2% tolerance)
- Coverage reports MUST be generated with `./bouy test --pytest` and analyzed with `./bouy test --coverage`

**Testing Infrastructure**:
- **Unit Tests**: Business logic, models, utilities (majority of tests)
- **Integration Tests**: Database operations, Redis interactions, API endpoints (marked with `@pytest.mark.integration`)
- **Scraper Tests**: VCR-recorded HTTP interactions, mock data validation
- **Async Tests**: Use `pytest-asyncio` with `asyncio_mode=auto`
- **Property Tests**: Use Hypothesis for HSDS model validation

**Rationale**: The pipeline processes real-world data that directly affects people's ability to find food. Untested code in the reconciler could silently drop valid locations. Untested validation rules could reject legitimate food pantries. Untested scrapers could silently fail and leave communities without updated data. TDD ensures every behavior is captured as an executable specification before it ships.

**Exception**: Exploratory spikes for evaluating new scraping patterns or LLM providers MAY defer testing, but MUST be rewritten with tests before merging.

---

### IV. Pipeline Stage Boundaries (Separation of Concerns)

Each pipeline stage MUST have clear input/output contracts and single responsibility.

- Scrapers MUST NOT parse data into HSDS format (LLM workers handle alignment)
- Scrapers MUST NOT write to the database (reconciler handles persistence)
- Scrapers MUST NOT perform geocoding (validator service handles enrichment)
- LLM workers MUST NOT write directly to the database
- The validator MUST NOT skip the reconciler to write data
- The reconciler MUST be the exclusive path to database writes for scraped data
- The API MUST be read-only for public consumers

**Pipeline Stage Contracts**:
```
Scraper       → outputs: raw content string (JSON/HTML/text)
Content Store → outputs: deduplicated content entry with SHA-256 hash
LLM Worker    → outputs: HSDS-aligned structured data
Validator     → outputs: enriched data with confidence score
Reconciler    → outputs: canonical database records with version tracking
API           → outputs: HSDS-compliant JSON responses
Publisher     → outputs: HAARRRvest repository commits
```

**Rationale**: The pipeline has seven distinct stages, each owned by a different module under `app/`. When stages leak responsibilities (scrapers geocoding, LLM workers writing to the database), bugs become impossible to isolate, testing requires end-to-end setup instead of unit mocking, and changes to one stage cascade unpredictably. The current architecture already follows this pattern well; this principle prevents regression as the system grows.

---

### V. Scraper Consistency

All scrapers MUST follow established patterns for maintainability across 90+ implementations.

- All scrapers MUST inherit from `ScraperJob` base class in `app/scraper/utils.py`
- All scraper files MUST follow the naming convention `{name}_scraper.py`
- All scraper classes MUST follow the naming convention `{Name}Scraper`
- All scrapers MUST implement the `async scrape(self) -> str` method
- All scrapers MUST include a module docstring with: description, data source URL, coverage area, and GitHub issue reference
- All scrapers MUST use `httpx` for HTTP requests (not `requests`, `urllib`, or `aiohttp`)
- All scrapers MUST use `self.submit_to_queue()` for job submission
- All scrapers MUST return raw content as strings; HSDS alignment is the LLM's job
- Scrapers MUST NOT exceed 500 lines of code
- Each scraper MUST have a corresponding test file at `tests/test_scraper/test_{name}_scraper.py`
- Scraper tests MUST use VCR cassettes or mock data (no live HTTP calls in CI)

**Rationale**: With 90+ scrapers and growing, consistency is the difference between a maintainable system and a sprawling mess. Every scraper that deviates from the pattern becomes a special case that contributors must understand individually. The `ScraperJob` base class, the naming conventions, and the file structure exist specifically to make scraper development predictable. A contributor should be able to read one scraper and understand the pattern for all of them.

---

### VI. Data Quality for Vulnerable Populations (NON-NEGOTIABLE)

All location data MUST pass through the confidence scoring system before persistence.

- Locations with confidence scores below the rejection threshold (configurable, default: 10) MUST be rejected
- Coordinates of (0,0) or outside continental US bounds (lat 25-49, lon -125 to -67) MUST be flagged
- Test data patterns ("test", "demo", "example", "sample", "dummy", "fake", "anytown", "unknown") MUST be detected and rejected
- Placeholder addresses MUST be detected via regex patterns and rejected
- Geocoding enrichment MUST attempt ALL configured providers before accepting failure
- Data MUST NOT be published to HAARRRvest without validation
- All validation decisions MUST be logged with reasoning for auditability
- Published data MUST be traceable to its source scraper and processing chain

**Rationale**: This system publishes data that food-insecure people use to find their next meal. A false location sends someone to a place that does not exist. A missing location means someone does not learn about a nearby food pantry. Low-quality data is worse than no data because it erodes trust in the system. The validator service, confidence scoring, and enrichment pipeline exist specifically to ensure that what we publish is actionable and accurate. Every data quality shortcut is a decision to potentially waste a hungry person's time.

---

### VII. Privacy and Security

The system MUST NOT collect, store, or process Personally Identifiable Information (PII).

- All data collected MUST be publicly available information about organizations, not individuals
- API endpoints MUST be read-only for public consumers; write operations MUST be internal-only
- Environment secrets (API keys, database credentials) MUST use environment variables via `.env` files
- `.env` files MUST NEVER be committed to version control
- Test data MUST use fictional information only: `555-xxx-xxxx` phones, `example.com` domains, clearly fake addresses
- Security scanning (bandit, safety, pip-audit) MUST pass before merging
- All database access MUST use parameterized queries via SQLAlchemy (no raw SQL string interpolation)
- Error messages exposed via the API MUST NOT leak internal system details

**PR Checklist**:
- [ ] No secrets or credentials in code
- [ ] Test data uses fictional information exclusively
- [ ] `./bouy test --bandit` passes
- [ ] No PII in test files or fixtures

**Rationale**: This project serves communities that are already vulnerable. While this system only collects public organizational data, maintaining strict privacy discipline prevents scope creep toward collecting user data. The public API is intentionally unauthenticated to maximize accessibility, which makes security of the backend infrastructure even more critical.

---

### VIII. Content Deduplication

All scraped content MUST pass through the Content Store before processing.

- Content MUST be identified by SHA-256 hash for deduplication
- Content already processed (matching hash with existing job ID) MUST NOT be re-queued
- The Content Store MUST be the single entry point between scrapers and the LLM queue
- Content Store operations MUST be atomic (store + check in single operation)

**Rationale**: LLM processing is the most expensive stage in the pipeline (both in time and API cost). Without deduplication, running 90+ scrapers repeatedly would re-process identical content on every execution. The Content Store's SHA-256 hashing ensures that only genuinely new or changed content reaches the LLM workers. This is not merely an optimization -- it is an architectural requirement that makes the system economically viable to operate at scale.

---

### IX. File Size and Complexity Limits

Application source files MUST NOT exceed 600 lines of code.

- Files approaching 500 lines SHOULD be evaluated for refactoring during code review
- Cyclomatic complexity MUST NOT exceed 15 per function (enforced by ruff `C90` rule)
- Files exceeding limits MUST be refactored before new features are added to them
- When splitting files, extract along responsibility boundaries (not arbitrary line counts)

**Known Violations Requiring Cleanup**:

| File | Lines | Status |
|------|-------|--------|
| `app/haarrrvest_publisher/service.py` | 1669 | Needs decomposition |
| `app/reconciler/job_processor.py` | 1568 | Needs decomposition |
| `app/llm/hsds_aligner/schema_converter.py` | 1498 | Needs decomposition |
| `app/datasette/exporter.py` | 1181 | Needs decomposition |
| `app/reconciler/service_creator.py` | 990 | Needs decomposition |
| `app/validator/enrichment.py` | 931 | Needs decomposition |

**Exemptions**: Generated files, migration files, and test fixtures are excluded from line limits. Test files have a soft limit of 800 lines.

**Rationale**: Large files concentrate too many responsibilities, making them difficult to understand, test in isolation, and modify safely. The reconciler's `job_processor.py` at 1568 lines handles the critical path of data persistence. Smaller files enforce single responsibility and reduce the blast radius of changes. The 600-line limit is higher than the reference constitutions' 400-500 line limits because Python pipeline code often has legitimate density (config, logging, error handling) that inflates line counts.

---

### X. Consistent Quality Gates

All code MUST pass the following checks before merge (enforced via `./bouy test`):

1. **black**: Code formatting (88 character line length)
2. **ruff**: Linting with security rules (E, F, I, C90, N, B, S, RUF, UP)
3. **mypy**: Type checking for non-excluded modules
4. **bandit**: Security scanning
5. **pytest**: All tests passing with coverage ratchet enforced

- Pre-commit hooks MUST run all quality gates through Docker via bouy
- CI pipelines MUST run identical checks to local pre-commit hooks
- Quality gate failures MUST block merge; there are no exceptions for "just this once"

**Additional Quality Tools** (SHOULD run regularly):
- `./bouy test --vulture` for dead code detection
- `./bouy test --safety` for dependency vulnerability scanning
- `./bouy test --pip-audit` for package audit
- `./bouy test --xenon` for code complexity analysis

**Rationale**: Quality gates exist to catch problems before they reach production. This project has an extensive toolchain that represents significant investment in code quality infrastructure. Every bypass weakens the gates for future changes. The toolchain is deliberately run through Docker so that local environment differences cannot cause false passes.

---

### XI. Pipeline Resilience and Error Handling

All pipeline stages MUST handle errors gracefully without losing data.

- Scraper failures MUST NOT prevent other scrapers from executing
- LLM provider failures MUST trigger retry with exponential backoff
- Redis queue operations MUST have configurable TTL for both results and failures
- Database transactions MUST use proper rollback on failure
- All async operations MUST have timeouts configured
- Error messages MUST be logged with structlog and include: stage name, operation, scraper ID (where applicable), and error details
- Failed jobs MUST be preserved for inspection (configurable retention)
- The scouting-party (parallel scraper execution) mode MUST isolate failures per-scraper

**Rationale**: This pipeline runs 90+ scrapers against external websites that break, change, or go down without warning. LLM APIs have rate limits, outages, and quota restrictions. Geocoding providers throttle aggressively. A resilient pipeline must treat failures as routine events, not exceptional ones. Data loss during processing is unacceptable because re-scraping may not yield the same content (websites change). Every stage must fail safely, preserve what it can, and allow the rest of the pipeline to continue.

---

### XII. Structured Logging and Observability

All application logging MUST use `structlog` (not `print()` or bare `logging`).

- Log entries MUST include structured context: module name, operation, and relevant identifiers
- Scraper execution MUST log: start, completion, item count, and duration
- Validation decisions MUST log: confidence score, rejection reason (if applicable), and enrichment actions taken
- Reconciler operations MUST log: match/create decisions and version changes
- Prometheus metrics MUST be maintained for: scraper job counts, LLM queue depth, validation pass/fail rates
- Log levels MUST follow standard conventions: DEBUG for flow tracing, INFO for operations, WARNING for recoverable issues, ERROR for failures

**Rationale**: A multi-stage data pipeline with 90+ scrapers, LLM providers, geocoding services, and database operations generates enormous operational complexity. Without structured logging, debugging a data quality issue requires guessing which stage, which scraper, and which record caused the problem. Structured logs with consistent context fields enable efficient filtering and correlation.

---

### XIII. Documentation Maintenance

Documentation MUST be updated as part of the same PR that introduces code changes.

- `CLAUDE.md` MUST be updated when bouy commands change or new commands are added
- Scraper documentation MUST be updated when scrapers are added or modified
- API documentation at `/docs` (Swagger UI) is auto-generated and MUST NOT diverge from actual endpoints
- New pipeline features MUST be documented
- Documentation updates MUST NOT be deferred to separate PRs

**Rationale**: This project has extensive documentation that represents institutional knowledge. Documentation that falls out of sync with code is worse than no documentation because it actively misleads. The `CLAUDE.md` file specifically guides AI-assisted development -- if it describes bouy commands that do not exist or omits new ones, every AI-assisted session starts with incorrect context.

---

## Development Workflow

### Test-First Mandate

1. Write the test FIRST
2. Run `./bouy test --pytest tests/test_new_feature.py` and verify it fails
3. Write minimum implementation to make the test pass
4. Refactor for clarity
5. Run `./bouy test` (all checks) before committing

### Quality Gate Checklist (before every PR)

- [ ] `./bouy test --black` passes (auto-fixes formatting)
- [ ] `./bouy test --ruff` passes (no lint errors)
- [ ] `./bouy test --mypy` passes (type checking)
- [ ] `./bouy test --bandit` passes (security)
- [ ] `./bouy test --pytest` passes (all tests, coverage ratchet enforced)

### Commit Standards

- Conventional commits format: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Each commit should leave tests passing (supports git bisect)
- Atomic commits focused on single changes

### Branch Strategy

- `main` branch is protected; direct commits prohibited
- Feature branches: `feature/description` or `feat/description`
- Bug fixes: `fix/description`
- Chores: `chore/description`

## Governance

This constitution supersedes all informal practices and assumptions.

### Amendment Process

1. Propose amendment in written form with rationale
2. Document impact on existing code and CLAUDE.md
3. Update version according to semantic versioning:
   - **MAJOR**: Principle removal or incompatible redefinition
   - **MINOR**: New principle or material expansion
   - **PATCH**: Clarifications, wording fixes, non-semantic changes
4. Add entry to Amendment Log at top of file
5. Update dependent documentation (CLAUDE.md, CONTRIBUTING.md) if affected
6. Commit with version increment and amendment date

### Compliance Review

- All pull requests MUST pass constitution check before merge
- Principle violations MUST be explicitly justified with written rationale
- Simpler alternatives MUST be documented before accepting complexity

### Conflict Resolution

When the constitution conflicts with practical reality:

1. Document the conflict and context
2. Evaluate whether the constitution should be amended or the implementation adjusted
3. If amendment needed, follow the amendment process above
4. Constitution supersedes convenience but not impossibility

### Template Synchronization

Changes to principles MUST propagate to:

- `CLAUDE.md` (development instructions for AI-assisted work)
- `CONTRIBUTING.md` (contributor guidelines)
- `.pre-commit-config.yaml` (quality gate enforcement)
- `.github/workflows/ci.yml` (CI pipeline alignment)

**Version**: 1.0.0 | **Ratified**: 2026-02-27 | **Last Amended**: 2026-02-27
