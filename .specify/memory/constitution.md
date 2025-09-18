# Pantry Pirate Radio Constitution

## Core Principles

### I. Test-Driven Development (NON-NEGOTIABLE)
TDD is mandatory: Tests written → Tests fail → Implementation → Tests pass. The Red-Green-Refactor cycle must be strictly enforced. No implementation before tests. No skipping the RED phase. Use @agent-test-suite-monitor for all test execution. Minimum 90% test coverage required. All tests must use `./bouy test` commands exclusively.

### II. Food Security First
Every feature must serve the mission of improving food access. No personal data collection. Only aggregate publicly available information. Geographic focus on Continental US (25°N-49°N, -125°W to -67°W). HSDS v3.1.1 compliance is mandatory for all data structures.

### III. Container-Native Development
All development through Docker containers via bouy commands. No local Python dependencies except Docker. Zero local environment setup beyond `.env` file. Consistent development environment across all contributors. Use `./bouy` for ALL operations - never direct docker or poetry commands.

### IV. Data Quality & Validation
All data must pass validation pipeline with confidence scoring (0-100 scale). Automatic rejection of test/placeholder data (threshold: 30). Geocoding with exhaustive provider fallback. Content deduplication via SHA-256 hashing. Redis-based validation service with caching.

### V. Privacy & Transparency
No collection or storage of personal information. Clear attribution of all data sources. Anonymous usage always possible. Open source with public domain dedication. Transparent data provenance tracking.

### VI. Type Safety & Code Quality
Strict mypy type checking (no Any types). Black formatting enforced. Ruff linting required. Bandit security scanning mandatory. All code must pass `./bouy test` before commit.

### VII. Distributed Architecture
Microservices with clear boundaries. Redis-based job queue for scalability. PostgreSQL with PostGIS for spatial data. Content store for deduplication. HAARRRvest publisher for data distribution.

## Development Workflow

### Version Control
- Feature branches for all development (`fix-*`, `feature-*`, `update-*`)
- Semantic versioning (MAJOR.MINOR.PATCH)
- Conventional commits required
- Pull requests mandatory for main branch
- All commits must pass CI checks

### Testing Requirements
- TDD workflow: Red → Green → Refactor
- Use `./bouy test` for all testing
- Specific test types: `--pytest`, `--mypy`, `--black`, `--ruff`, `--bandit`
- Coverage analysis with `./bouy test --coverage`
- Integration tests for API endpoints
- Scraper dry-run testing before deployment

### Code Quality Gates
- 90% test coverage minimum
- Zero mypy errors
- Black formatting applied
- Ruff checks passing
- Bandit security scan clean
- Docker builds successful

### Documentation Standards
- CLAUDE.md for AI assistant guidance
- API documentation via OpenAPI/Swagger
- Scraper documentation required
- Architecture decisions recorded
- README kept current

## Technical Constraints

### Required Technologies
- Python 3.11+
- FastAPI for API layer
- PostgreSQL with PostGIS
- Redis for job queue
- Docker for all services
- Poetry for dependency management (containerized)

### Data Standards
- HSDS v3.1.1 specification compliance
- Pydantic models for validation
- JSON for data interchange
- UTF-8 encoding throughout
- ISO 8601 timestamps

### Performance Requirements
- API response time < 200ms p95
- Scraper timeout 30 seconds max
- LLM processing timeout 2 minutes
- Content store lookup < 10ms
- Geocoding cache TTL 24 hours

### Security Requirements
- No secrets in code or commits
- Environment variables for configuration
- SQL injection prevention via ORM
- Rate limiting on all endpoints
- CORS properly configured

## Operational Excellence

### Monitoring & Observability
- Structured JSON logging
- Request ID tracking
- Job queue monitoring via RQ Dashboard
- Health check endpoints
- Error tracking and alerting

### Deployment Process
- Docker images for all services
- Environment-based configuration
- Database migrations versioned
- Zero-downtime deployments
- Rollback capability maintained

### Data Pipeline Integrity
- Content deduplication before processing
- Validation service quality gates
- Reconciler version tracking
- HAARRRvest daily publishing
- Audit trail for all changes

## Governance

### Constitution Authority
This constitution supersedes all other development practices and guides all technical decisions. It represents our commitment to food security and data quality.

### Amendment Process
Amendments require:
1. Problem statement with impact on food security mission
2. Proposed solution with technical rationale
3. Test coverage for changes
4. Migration plan for existing code
5. Update all dependent documents per `.specify/memory/constitution_update_checklist.md`
6. Review via pull request with CI passing

### Compliance Verification
- All pull requests must verify constitutional compliance
- `./bouy test` must pass completely
- Test coverage must be maintained or improved
- HSDS compliance verified for data changes
- Use `CLAUDE.md` for runtime development guidance

### Enforcement
- CI/CD pipeline enforces all quality gates
- @agent-test-suite-monitor for test verification
- Code review required for main branch
- Breaking changes require major version bump
- Non-compliance blocks merge

**Version**: 1.0.0 | **Ratified**: 2025-09-16 | **Last Amended**: 2025-09-16