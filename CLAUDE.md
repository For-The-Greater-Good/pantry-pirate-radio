# CLAUDE.md

You must follow the constitution in [constitution.md](constitution.md) when doing any work in this repository.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Most Common Commands

```bash
# First time setup
./bouy setup                 # Interactive setup wizard
./bouy up --with-init        # Start with database initialization

# Daily development
./bouy up                    # Start services
./bouy test --pytest         # Run tests
./bouy logs app              # Check logs
./bouy shell app             # Debug in container
./bouy down                  # Stop services

# Before committing
./bouy test                  # Run ALL checks (required for PR)
```

## Quick Command Reference

**IMPORTANT: All commands use bouy - no local dependencies except Docker required!**

```bash
# Initial Setup Commands
./bouy setup                 # Interactive setup wizard (creates .env file)
./bouy op status             # 1Password: show pointer + sign-in + fields
./bouy op push               # 1Password: upload local .env files into the vault
./bouy op pull --field dev   # 1Password: print a stored field (stdout)
./bouy --help                # Show help with all commands
./bouy help                  # Same as --help (alternative syntax)
./bouy --version             # Show bouy version (v1.0.0)
./bouy version               # Same as --version (alternative syntax)

# Essential Commands
./bouy up                    # Start all services (development mode by default)
./bouy up --prod             # Start services in production mode
./bouy up --test             # Start services in test mode
./bouy up --with-init        # Start with database initialization
./bouy down                  # Stop all services
./bouy test                  # Run all tests and checks (pytest, mypy, black, ruff, bandit)
./bouy logs                  # View all logs (follows by default)
./bouy logs app              # View specific service logs
./bouy shell app             # Open shell in container (bash or sh)
./bouy ps                    # List running services
./bouy clean                 # Stop services and remove volumes

# Testing Commands
./bouy test                  # Run all CI checks
./bouy test --pytest         # Run pytest with coverage
./bouy test --mypy           # Type checking only
./bouy test --black          # Code formatting check (auto-updates files)
./bouy test --ruff           # Linting only
./bouy test --bandit         # Security scan only
./bouy test --coverage       # Analyze existing coverage reports (run after --pytest)
./bouy test --vulture        # Dead code detection
./bouy test --safety         # Dependency vulnerability scan
./bouy test --pip-audit      # Pip audit for vulnerabilities
./bouy test --xenon          # Code complexity analysis

# Scraper Commands (Local)
./bouy scraper --list         # List all available scrapers
./bouy scraper --all          # Run all scrapers sequentially
./bouy scraper NAME           # Run specific scraper by name
./bouy scraper scouting-party # Run all scrapers in parallel (default: 5 concurrent)
./bouy scraper scouting-party 10 # Run with custom concurrency (10 scrapers)
./bouy scraper full-broadside # Run all scrapers in parallel (max firepower!)
./bouy scraper-test NAME      # Test specific scraper (dry run)
./bouy scraper-test --all     # Test all scrapers (dry run)

# Scraper Commands (AWS)
./bouy scraper --aws NAME              # Run scraper on AWS via Step Functions
./bouy scraper --aws NAME1 NAME2       # Run multiple scrapers on AWS
./bouy scraper --aws --all             # Run all default scrapers on AWS
./bouy scraper --aws scouting-party    # Run all scrapers on AWS (parallel)
./bouy scraper --aws --status          # List recent pipeline executions
./bouy scraper --aws --status EXEC_ARN # Check specific execution status
./bouy scraper --aws --logs            # Tail AWS scraper CloudWatch logs

# Submarine Commands (Local)
./bouy submarine scan                          # Scan all locations with gaps
./bouy submarine scan --scraper NAME           # Filter to one scraper
./bouy submarine scan --scraper NAME --limit 5 # Controlled rollout
./bouy submarine status                        # Show crawl counts
./bouy submarine logs                          # Follow submarine worker logs

# Submarine Commands (AWS)
./bouy submarine --aws                         # Full scan via Step Functions (scan → crawl → batch extract)
./bouy submarine --aws --scraper NAME          # Filter by scraper

# Service Management
./bouy build                # Build all services
./bouy build app            # Build specific service
./bouy build --prod worker  # Build for production
./bouy exec app CMD         # Execute command in container
./bouy pull                 # Pull all latest container images
./bouy pull v1.2.3          # Pull specific version tags

# Validator Service Commands
./bouy validator status     # Check validator service status
./bouy logs validator       # View validator service logs
./bouy shell validator      # Debug in validator container

# Global Flags (work with all commands)
./bouy --help               # Show help
./bouy --version            # Show version
./bouy --programmatic CMD   # Structured output for automation
./bouy --json CMD           # JSON output (implies --programmatic)
./bouy --quiet CMD          # Suppress non-error output
./bouy --verbose CMD        # Enable verbose/debug output
./bouy --no-color CMD       # Disable colored output
```

## Initial Setup

### NEW USERS: Interactive Setup Wizard

**For new installations, always start with the setup wizard:**

```bash
./bouy setup                # Interactive setup wizard - creates .env configuration
./bouy up                   # Start services (development mode by default)
./bouy test                 # Verify everything works (runs all CI checks)
```

The setup wizard will:
- Create `.env` file from template with interactive prompts
- Configure database passwords (default: 'pirate')
- Set up LLM provider selection (OpenAI via OpenRouter vs Claude/Anthropic)
- Handle Claude authentication options (API key vs Claude Code CLI)
- Configure HAARRRvest repository tokens (or 'skip' for read-only mode)
- Create timestamped backups of existing `.env` files

## Environment Configuration

### Shared Pipeline Config (`config/defaults.yml`)

`config/defaults.yml` is the **single source of truth** for values that must be identical across local Docker and AWS deployments. Both `app/core/config.py` (runtime) and `infra/shared_config.py` (CDK) read from it.

**Variable categories:**
1. **Shared Pipeline Config** → `config/defaults.yml` (LLM params, validation, geocoding, enrichment)
2. **Environment-Specific** → `.env` (local) / CDK hardcoded (AWS) — legitimately different per env
3. **Secrets** → `.env` locally, Secrets Manager on AWS. CDK reads `.env` at deploy time via `infra/shared_config.py`
4. **Local-Only** → `.env` only (backup settings, rate limits, etc.)
5. **AWS-Only** → CDK only (SQS URLs, DB host, S3 buckets, etc.)

Environment variables **always override** shared defaults. Never put secrets in `config/defaults.yml`.

### 1Password secret loading (no `.env` on disk)

bouy can source per-environment config from 1Password instead of a `.env` file:

- **A `.env` (or `.env.test`/`.env.prod`) on disk always wins** — 1Password is not
  consulted, so OSS contributors are unaffected. Prod falls back to `.env` when
  `.env.prod` is absent.
- With no override file, container-using commands read the matching field
  (`dev`/`test`/`prod`) from a 1Password item via `op read` and inject the values
  into containers through a runtime, names-only passthrough overlay. **Secrets are
  never written to disk.** Auth is the `op` desktop-app biometric integration;
  `help`/`version`/`setup`/`op` never trigger a prompt.
- Pointer config: the **account has no built-in default** (it is org-specific) —
  set it via `config/op.conf` (a gitignored local pointer like `.env`, copied from
  the committed `config/op.conf.example`) or the `OP_ACCOUNT` env var; blank means
  bouy omits the `op --account` flag and the op CLI uses its default account. Vault
  and item still default to `Pantry Pirate Radio` / `bouy-env`. Precedence:
  env > op.conf > built-in.
- `--no-1password` / `USE_1PASSWORD=false` force the file path; `--1password` /
  `USE_1PASSWORD=true` force the vault. Auto-detect is the default.

Commands:
- `./bouy op status` — show pointer, sign-in state, which fields exist.
- `./bouy op push [--field dev|test|prod|all]` — upload local `.env*` files into
  the vault (one-command migration).
- `./bouy op pull [--field dev] [--out FILE]` — print a field for inspection
  (writes a file only with `--out`).

CI and AWS are unchanged (GitHub Secrets and Secrets Manager respectively).

### Required Environment Variables

The setup wizard configures these automatically, but you can also set them manually:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/pantry_pirate_radio
REDIS_URL=redis://localhost:6379/0

# LLM Provider (choose one: openai, claude, bedrock)
LLM_PROVIDER=claude  # or "openai" or "bedrock"
ANTHROPIC_API_KEY=your_key  # For Claude
OPENROUTER_API_KEY=your_key  # For OpenAI

# AWS Bedrock (if using bedrock provider)
AWS_DEFAULT_REGION=us-east-1
AWS_PROFILE=your_sso_profile

# Validator Service Configuration
VALIDATOR_ENABLED=true  # Enable/disable validation service
VALIDATION_REJECTION_THRESHOLD=10  # Confidence threshold for rejection (default: 10)
ENRICHMENT_CACHE_TTL=86400  # Cache TTL for enrichment in seconds (default: 24 hours)

# HAARRRvest Publisher
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=github_pat_xxx  # GitHub PAT with repo access

# Content Store
CONTENT_STORE_PATH=/path/to/content-store
CONTENT_STORE_BACKEND=file  # Backend type: "file" (default) or "s3" (AWS deployment)
CONTENT_STORE_STALE_JOB_THRESHOLD_HOURS=72  # SQS-mode: age after which a result-less job link is re-enqueued (default 72)

# Submarine Enrichment
SUBMARINE_ENABLED=false  # Enable/disable submarine enrichment (default: false)
SUBMARINE_CRAWL_TIMEOUT=30  # Crawl timeout in seconds
SUBMARINE_MAX_PAGES_PER_SITE=3  # Max pages to crawl per site

# Lambda API (set automatically in AWS, not needed locally)
AWS_LAMBDA_FUNCTION_NAME=  # Auto-set by Lambda runtime; triggers Lambda-optimized behavior
DATABASE_SECRET_ARN=       # Secrets Manager ARN for DB password (Lambda uses this instead of DATABASE_PASSWORD)
```

### Test Environment
```bash
# .env.test required for testing
TEST_DATABASE_URL=postgresql://postgres:password@db:5432/test_pantry_pirate_radio
TEST_REDIS_URL=redis://cache:6379/1
```

## Development Commands

### IMPORTANT: Docker-Only Development

**All development commands must use bouy** - no local Python dependencies are required except Docker.

### Using @agent-test-suite-monitor

**CRITICAL: Use @agent-test-suite-monitor for ALL testing needs. This agent is your dedicated test execution and monitoring system.**

#### When to Use @agent-test-suite-monitor

**Always use @agent-test-suite-monitor in these scenarios:**

1. **After implementing new features or fixing bugs** - to verify your changes work correctly
2. **When tests are failing unexpectedly** - to get detailed failure analysis and diagnostics
3. **Before committing changes** - to ensure all tests pass and code quality standards are met
4. **After making significant code changes** - to verify nothing has been broken
5. **When investigating CI/CD failures** - to reproduce and debug test failures locally
6. **For regular test health checks** - to monitor test suite performance and coverage
7. **When you need to run specific test categories** - the agent runs tests individually for better control

**Examples of using @agent-test-suite-monitor:**
```bash
# After implementing a new feature
@agent-test-suite-monitor "Run full test suite after implementing new user API endpoint"

# When tests fail unexpectedly
@agent-test-suite-monitor "Debug failing authentication tests and provide detailed analysis"

# Before creating a pull request
@agent-test-suite-monitor "Run all test categories individually before PR"

# After refactoring code
@agent-test-suite-monitor "Verify all tests pass after refactoring database models"

# For specific test investigation
@agent-test-suite-monitor "Run only pytest tests for the API module"

# When monitoring test performance
@agent-test-suite-monitor "Check test execution times and identify slow tests"
```

#### What @agent-test-suite-monitor Does

The test-suite-monitor agent:
- **Runs tests individually by category** (pytest, black, ruff, mypy, bandit) for better control
- **Analyzes test failures** with detailed error reporting and likely causes
- **Tracks changes between test runs** to identify regressions
- **Monitors test performance** and execution times
- **Provides coverage analysis** to identify untested code
- **Suggests specific debugging commands** when tests fail
- **Uses proper output management** (--programmatic, --quiet, --json) for clean results

#### Important Notes

- The agent will NEVER use `./bouy test` without specifying a test type
- It runs each test category separately for clearer results and better failure isolation
- It provides structured failure reports with actionable recommendations
- It tracks test results within the session to identify patterns
- It never modifies code - only reports and analyzes test results

### Test-Driven Development (TDD) Workflow

This project follows Test-Driven Development principles. Always write tests before implementing features:

1. **Red Phase**: Write a failing test that defines the desired behavior
2. **Green Phase**: Write the minimum code necessary to make the test pass
3. **Refactor Phase**: Improve the code while keeping tests passing

#### TDD Process for New Features
```bash
# 1. Create test file first
touch tests/test_new_feature.py

# 2. Write failing test and run with bouy
./bouy test --pytest  # Should fail

# 3. Implement minimal code to pass
# ... write implementation ...

# 4. Run test again
./bouy test --pytest  # Should pass

# 5. Refactor and ensure tests still pass
./bouy test --pytest

# 6. Run full test suite before committing
./bouy test  # Runs all CI checks
```

## Testing with Bouy

### Running All Tests
```bash
./bouy test                  # Run all CI checks (pytest, mypy, black, ruff, bandit)
```

### Running Specific Test Types
```bash
./bouy test --pytest         # Run pytest with coverage
./bouy test --mypy           # Type checking only
./bouy test --black          # Code formatting only
./bouy test --ruff           # Linting only
./bouy test --bandit         # Security scan only
./bouy test --coverage       # Pytest with coverage threshold check
```

### Running Specific Test Files
```bash
# Test a specific file
./bouy test --pytest tests/test_api.py

# Test a directory
./bouy test --pytest tests/test_scraper/

# Multiple files
./bouy test --pytest tests/test_api.py tests/test_reconciler.py
./bouy test --pytest tests/test_validator/  # Test validator module
```

### Passing Additional Arguments to Tests

Use `--` to pass arguments to the underlying test command:

```bash
# Verbose output
./bouy test --pytest -- -v

# Run tests matching pattern
./bouy test --pytest -- -k test_name
./bouy test --pytest -- -k "test_api or test_reconciler"

# Stop on first failure
./bouy test --pytest -- -x

# Drop to debugger on failure
./bouy test --pytest -- --pdb

# Show local variables
./bouy test --pytest -- -l

# Run specific test function
./bouy test --pytest -- tests/test_api.py::TestAPI::test_get_organizations

# Combine options
./bouy test --pytest -- -vsx -k test_name
```

### Test Output Formats
```bash
# Normal output (default)
./bouy test --pytest

# Programmatic mode (structured output for CI)
./bouy --programmatic test --pytest

# JSON output
./bouy --json test --pytest

# Quiet mode (minimal output)
./bouy --quiet test --pytest

# No color (for log files)
./bouy --no-color test --pytest

# Combine modes
./bouy --programmatic --quiet test
```

### Coverage Analysis
```bash
# Run tests with coverage check
./bouy test --coverage

# Coverage reports are automatically generated:
# - htmlcov/index.html (HTML report)
# - coverage.xml (XML report for CI)
# - coverage.json (JSON report for automation)

# View coverage report in browser (macOS/Linux)
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Type Checking Specific Files
```bash
# Check specific paths
./bouy test --mypy app/api/
./bouy test --mypy app/api/ app/llm/
```

### Code Formatting
```bash
# Check formatting (updates files automatically)
./bouy test --black

# Check specific paths
./bouy test --black app/api/
```

### Security Scanning
```bash
# Run security scan
./bouy test --bandit

# With custom severity
./bouy test --bandit -- -ll  # Low severity and above
```

### CI/CD Testing Examples
```bash
# GitHub Actions / CI pipelines
./bouy --programmatic --quiet test              # All checks, minimal output
./bouy --programmatic --quiet test --pytest     # Just tests
./bouy --programmatic --quiet test --mypy       # Just type checking
./bouy --json test --pytest                     # JSON test results

# Combine with error checking
./bouy --programmatic --quiet test || exit 1
```

### Development Setup
```bash
# Start all services (no local dependencies needed)
./bouy up                    # Development mode (default)
./bouy up --prod            # Production mode (includes Datasette viewer)
./bouy up --test            # Test mode
./bouy up --with-init       # With database initialization
./bouy up --dev --with-init # Combine options

# Start specific services
./bouy up app worker        # Start only app and worker

# Service management
./bouy down                 # Stop all services
./bouy ps                   # List running services
./bouy logs                 # View all logs (follows by default)
./bouy logs app             # View specific service logs
./bouy logs -f worker       # Follow worker logs (explicit follow)
./bouy shell app            # Open shell in container (bash or sh)
./bouy exec app python --version  # Execute command in container
./bouy clean                # Stop services and remove volumes

# Build services
./bouy build                # Build all services
./bouy build app            # Build specific service
./bouy build --prod worker  # Build for production

# Programmatic mode for automation
./bouy --json ps            # Get service status as JSON
./bouy --quiet up           # Start with minimal output
./bouy --programmatic exec app python -c "print('test')"
```

## Testing Guidelines

### IMPORTANT: Always Use ./bouy test Commands
- **ALWAYS use `./bouy test --pytest` for running tests** - do NOT use `./bouy exec app poetry run pytest`
- For specific test files: `./bouy test --pytest tests/test_api.py`
- For specific test functions: `./bouy test --pytest -- tests/test_api.py::TestAPI::test_function`
- The `./bouy test` command properly handles test environments, coverage, and dependencies

### Standards-conformance testing (constitution v1.7.0 — machinery, not memory)
When implementing ANY external standard (RFC, W3C, C2SP, HSDS, …), **first ask: does the
standard publish its own test vectors / reference implementation / conformance suite?** If yes,
using them is MANDATORY (constitution Principle III, v1.7.0): vendor them under
`tests/<area>/vendor/<suite>/` with a README pinning source URL + commit + license (pattern:
`tests/test_federation/vendor/jcs_rfc8785/`). A self-derived oracle written alongside the
implementation shares its author's blind spots and is NOT conformance evidence — the RFC 8785
UTF-16 key-ordering defect shipped green against self-derived tests labeled "official vectors"
and was caught only by the spec author's real suite (#555). Existing external anchors: cyberphone
JCS suite (canonical.py); Go `sumdb/note` PeterNeumann vector reproduced byte-for-byte
(checkpoint.py); transparency-dev/Google-CT RFC-6962 roots + consistency proofs (merkle.py,
verified live — vendored with P1 Task 11); RFC 9421 Appendix B.2.6 (signing.py, same). Test
levels expected on RED-tier (crypto/concurrency) code: unit + Hypothesis property +
external-KAT + DB-backed + real-OS-process concurrency + independent-verifier integration +
negative/guard paths. Where two valid spec readings exist, only cross-implementation interop
(the P2 two-node loop, the PR-D reference second node) settles it — pin your reading in a
fixture until then.

### Common Testing Workflows
```bash
# Before committing changes
./bouy test                  # Run all CI checks

# Quick iteration during development
./bouy test --pytest tests/test_module.py  # Test specific module
./bouy test --mypy app/module.py          # Type check specific file
./bouy test --black app/                  # Format code in directory

# Debugging test failures
./bouy test --pytest -- -v               # Verbose output
./bouy test --pytest -- -x               # Stop on first failure
./bouy test --pytest -- --pdb            # Drop to debugger on failure
./bouy test --pytest -- -k pattern       # Run tests matching pattern

# Coverage analysis
./bouy test --pytest                     # Generate coverage
./bouy test --coverage                   # Analyze coverage reports
open htmlcov/index.html                  # View HTML report
```

## Additional Commands

### HAARRRvest Publisher
```bash
./bouy haarrrvest             # Manually trigger publishing run
./bouy haarrrvest run         # Same as above
./bouy haarrrvest logs        # Follow publisher logs
./bouy haarrrvest status      # Check publisher service status
```

### Content Store Management
```bash
./bouy content-store status      # Show content store status
./bouy content-store report      # Generate detailed report
./bouy content-store duplicates  # Find duplicate content
./bouy content-store efficiency  # Analyze storage efficiency
```

### Data Recording and Replay
```bash
./bouy recorder                          # Save job results to JSON
./bouy recorder --output-dir /custom/path # Custom output directory
./bouy replay --file FILE                # Replay single JSON file (validates by default)
./bouy replay --directory DIR            # Replay all files in directory (validates by default)
./bouy replay --use-default-output-dir   # Use default outputs directory (validates by default)
./bouy replay --dry-run                  # Preview without executing
./bouy replay --skip-validation          # Skip validation service (legacy mode)
```

**Note:** As of Issue #369, replay now routes through the validation service by default for data enrichment and confidence scoring. Use `--skip-validation` to bypass validation and route directly to the reconciler (legacy behavior).

### Claude Authentication
```bash
./bouy claude-auth           # Interactive Claude authentication
./bouy claude-auth setup     # Setup Claude authentication
./bouy claude-auth status    # Check authentication status
./bouy claude-auth test      # Test Claude connection
./bouy claude-auth config    # Show Claude configuration
```

### AWS Deployment
```bash
./bouy deploy dev                    # Full deploy (build + CDK + push + redeploy)
./bouy deploy dev --diff             # Show CDK diff without deploying
./bouy deploy dev --infra-only       # CDK deploy only (assumes images exist)
./bouy deploy dev --images-only      # Build and push Docker images only
./bouy deploy dev --destroy          # Tear down all stacks
./bouy deploy dev --infra-only --stack BatchStack  # Deploy single stack
./bouy deploy dev --diff --stack ComputeStack      # Diff single stack
```

**Daily SQLite Publisher (AWS)**:
- Publisher runs daily at 4 AM UTC via EventBridge schedule (enabled in prod)
- Exports Aurora data to SQLite, uploads to S3 exports bucket
- Public SQLite URL: `https://pantry-pirate-radio-exports-{env}.s3.amazonaws.com/sqlite-exports/latest/pantry_pirate_radio.sqlite`
- Daily archives kept for 30 days at `sqlite-exports/{date}/pantry_pirate_radio.sqlite`

**Metabase Cloud Access**:
- NLB in public subnets forwards TCP 5432 to RDS Proxy (MetabaseAccessStack)
- Access restricted to Metabase Cloud static IPs via security group
- Lambda resolves RDS Proxy DNS every minute and syncs NLB target IPs
- Metabase Cloud DB config: Host = NLB DNS (from stack output `MetabaseAccessStack-dev.NlbDnsName`), Port = 5432, DB = `pantry_pirate_radio`, User = `pantry_pirate`, Password = from Secrets Manager, SSL = required

**Bastion / Ad-hoc DB Access**:
```bash
# Connect to Aurora via SSM port forwarding (requires AWS CLI + Session Manager plugin)
INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:aws:cloudformation:stack-name,Values=BastionStack-dev" --query 'Reservations[0].Instances[0].InstanceId' --output text)
PROXY_ENDPOINT=$(aws rds describe-db-proxies --query 'DBProxies[?DBProxyName==`pantry-pirate-radio-proxy-dev`].Endpoint' --output text)

aws ssm start-session --target $INSTANCE_ID \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$PROXY_ENDPOINT\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}"

# Then connect locally to: localhost:5432, user: pantry_pirate, SSL: required
```

### Data Reconciliation
```bash
./bouy reconciler            # Run reconciler service
./bouy reconciler --force    # Force processing (bypass checks)
```

**Backfill scripts** (one-shot cleanup for duplicates the reconciler historically created):
```bash
# Narrow same-org/same-name dupes (older script, ~111m radius)
./bouy exec app python scripts/dedupe_same_org_locations.py             # dry-run
./bouy exec app python scripts/dedupe_same_org_locations.py --apply     # commit

# Tier 3 fuzzy dupes (~200m radius, different name AND different org, same physical pantry)
./bouy exec app python scripts/dedupe_near_duplicate_locations.py            # dry-run
./bouy exec app python scripts/dedupe_near_duplicate_locations.py --apply    # commit
./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py    # prod dry-run
./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py --apply  # prod commit
```

Both scripts pick a survivor canonical, repoint FK children onto it (location_source, address, phone, schedule, service_at_location, etc.), and soft-delete the duplicates via `is_canonical=FALSE`. Rows with `verified_by IN ('admin','source','claimed')` are exempt — never merged into. The Tier 3 script mirrors the reconciler's Tier 3 detection SQL (`app/reconciler/dedup.py`) and the PTF API's survivor pick (FANO > confidence > id), so prevent-on-ingest, hide-on-serve, and drain-the-backlog stay aligned.

#### Tier 3 dedup — operator runbook

Tier 3 fuzzy dedup has real blast radius: every `--apply` run **hard-deletes** rows that conflict on UNIQUE constraints (same scraper_id on `location_source`, same service_id on `service_at_location`). Soft-deletes and FK repoints are reversible from `dedup_run_audit`; UNIQUE-skip DELETEs require Aurora PITR to actually restore. **Always run the staged rollout below for prod.**

**Pre-flight (before every prod `--apply`):**

1. **Manual Aurora snapshot** — explicit, labeled, doesn't expire on a 30-day clock:
   ```bash
   aws rds create-db-cluster-snapshot \
     --db-cluster-identifier pantry-pirate-radio-prod \
     --db-cluster-snapshot-identifier pre-tier3-dedup-$(date -u +%Y-%m-%d-%H%M)
   ```
2. **HAARRRvest dump freshness** — script checks this automatically; aborts if no `record_version` row was written in the last 12h. Override only in emergencies via `--skip-freshness-check`.
3. **Diagnostic count** — every run prints `pair_count` and `locations_involved_proxy` before any writes. Read it.

**Staged rollout:**

```bash
# Stage 1: 50-cluster canary. Run, wait 30 minutes, spot-check 5 random clusters.
./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py \
  --max-clusters 50 --apply
# Note the run_id printed in the log.

# Stage 2: 500-cluster ramp. Same drill, wait ~2h.
./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py \
  --max-clusters 500 --apply

# Stage 3: full run.
./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py \
  --apply
```

**Dry-run with sample inspection** (eyeball N random clusters' before-state before any apply):

```bash
./bouy run-script --aws --prod scripts/dedupe_near_duplicate_locations.py \
  --dry-run-sample 20
```

**Post-apply spot-check** (run after each stage):

```sql
-- Recently merged clusters from this run.
SELECT cluster_id, survivor_id, COUNT(*) AS rows_logged
FROM dedup_run_audit
WHERE run_id = '<run_id>'
GROUP BY cluster_id, survivor_id
ORDER BY rows_logged DESC
LIMIT 10;

-- Pick a survivor, verify its fields look right.
SELECT id, name, confidence_score, verified_by
FROM location
WHERE id = '<survivor_id>';
```

**Reversing a bad run:**

```bash
# Dry-run the undo first; review what would be reversed.
./bouy run-script --aws --prod scripts/undo_dedup_run.py --run-id <uuid>

# Commit the undo.
./bouy run-script --aws --prod scripts/undo_dedup_run.py --run-id <uuid> --apply
```

`undo_dedup_run.py` reverses every repoint and soft-delete logged in `dedup_run_audit`. It also prints `RECOVERY_TICKET <json>` lines for each UNIQUE-skip DELETE — those rows are gone from the live DB and need Aurora PITR or a HAARRRvest SQL dump replay. The full row payload is in the ticket, so you know exactly what to restore.

**"A pantry disappeared from the public site after the dedup run":**

1. Find the location id (from `support_request` or via PTF API logs).
2. Check `dedup_run_audit` for the row id:
   ```sql
   SELECT * FROM dedup_run_audit WHERE row_id = '<location_id>' OR duplicate_id = '<location_id>';
   ```
3. If `action='soft_delete'`: the pantry was correctly identified as a duplicate of the survivor in the same row. If the user expected this specific id, point them to the survivor. If the merge was wrong, run `undo_dedup_run.py --run-id <id>` for just that run.
4. If no audit row: the disappearance is unrelated to this script (check `record_version`, `validation_status`, etc.).

### Scraper Development Workflow

**Interactive Slash Command: `/scrape`**

The `/scrape` command provides a guided workflow for creating new food bank scrapers from Feeding America GitHub issues.

```bash
# Pick next priority task (weighted by population served)
/scrape next

# Work on specific issue
/scrape 123
```

**What it does:**
1. **Issue Selection** - Fetches issue details and displays food bank info
2. **Vivery Detection** - Critical check to avoid duplicate scrapers (Vivery sites already covered)
3. **Website Analysis** - Uses browser tools to analyze page structure and suggest approach
4. **Code Generation** - Creates scraper and test files from templates with smart suggestions
5. **Testing** - Validates syntax and runs dry run to verify scraper works
6. **Documentation** - Creates implementation notes capturing decisions and patterns

**Manual Scripts (for advanced use):**
```bash
# List all Feeding America scraper issues
gh issue list --label scraper --label feeding-america

# Pick next priority task
./bouy exec app python3 scripts/feeding-america/pick_next_scraper_task.py

# Check if site uses Vivery (already covered)
./bouy exec app python3 scripts/feeding-america/check_vivery_usage.py

# Generate scraper boilerplate from issue
./bouy exec app python3 scripts/feeding-america/create_scraper_from_issue.py [issue-number]

# Update scraper progress on GitHub
./bouy exec app python3 scripts/feeding-america/update_scraper_progress.py

# Mark scraper as completed
./bouy exec app python3 scripts/feeding-america/update_scraper_progress.py --completed [issue-number]
```

**Key Guidelines:**
- **ALWAYS check for Vivery first** - Vivery sites are already covered by `vivery_api_scraper.py`
- **NO geocoding in scrapers** - The validator service handles all geocoding automatically
- **Use similar scrapers as reference** - Find patterns that work and adapt them
- **Test before committing** - Run `./bouy scraper-test [name]` for dry run validation

**Implementation Notes:**
- Generated files: `.pirate/specs/[issue-number]-[name]/notes.md`
- Scraper location: `app/scraper/scrapers/[name]_scraper.py`
- Test location: `tests/test_scraper/test_[name]_scraper.py`

### Data Viewing and Endpoints
When services are running, the following endpoints are available:
- **API**: http://localhost:8000 (REST API)
- **API Docs**: http://localhost:8000/docs (Interactive Swagger UI)
- **Datasette Viewer**: http://localhost:8001 (in production mode only)
- **RQ Dashboard**: http://localhost:9181 (job queue monitoring)

**PTF partner endpoints** (public, no auth, Plentiful /map/locations wire shape):
- `GET /api/v1/partners/ptf/locations` — list with `limit`/`offset`, `lat1/lng1/lat2/lng2` bbox, `q` substring
- `GET /api/v1/partners/ptf/locations/{location_id}` — single location detail
- Both responses include a `feeding_america_food_bank` block (id + name, plus richer fields when in catalogue) when the location's ZIP matches `feeding_america_zip_coverage`; `null` otherwise.

**Beacon partner endpoints** (internal; feed the static directory-site build):
- `GET /api/v1/partners/beacon/sync` — full location records (schedules, phones, languages, accessibility) for static page rendering. Cursor-paginated, `is_canonical=TRUE` quality gate (`app/api/v1/partners/beacon/services.py`).
- `GET /api/v1/partners/beacon/redirects` — dead (dedup-soft-deleted) location ids → surviving canonical address components, so beacon publishes 301s for URLs it deleted. Read-only; follows the transitive survivor chain to its terminal still-canonical row (cycle/depth-guarded) via `dedup_run_audit`; tolerates a missing audit table (returns `[]`). Beacon turns same-locality survivors into 301s and everything else into 410 at the CloudFront edge — see `plugins/ppr-beacon/CLAUDE.md` → "SEO indexing recovery" for the edge `noindex`/301/410 behavior and the English-first surface shrink.

Datasette provides:
- SQL interface to explore published HAARRRvest data
- Read-only access to the SQLite database
- Data export in various formats (CSV, JSON)

## Architecture Overview

### System Flow
```
Web Sources → Scrapers → Content Store → Redis Queue → LLM Workers
                ↓                                           ↓
            Dedup Check                                 HSDS Alignment
                                                           ↓
                                                      Validator Service
                                                           ↓
                                                    Confidence Scoring
                                                           ↓
PostgreSQL ← Reconciler ← Job Creation ← Enrichment & Quality Control
    ↓                          ↓
    ├→ Submarine:
    │     Scanner → Crawl websites → Content filter → Staging Queue
    │     → Batcher Lambda (≥100: Bedrock batch 50% off, <100: on-demand)
    │     → Result Processor → Reconciler (enriched data)
    ├→ FastAPI → Clients  JSON Archives → HAARRRvest Repository
    │                                         ↓
    │                                   GitHub Pages → Public Access
    │
    └→ Publisher (daily) → SQLite → S3 Exports Bucket → Public Access
```

#### AWS Batch Inference Path (Bedrock)

On AWS, scrapers enqueue to a **staging SQS queue** instead of the LLM queue.
After all scrapers complete, Step Functions invokes a **Batcher Lambda** that:
- **>= 100 records**: Builds JSONL, submits Bedrock Batch Inference job (50% cost savings)
- **< 100 records**: Re-enqueues to LLM queue for on-demand Fargate processing

Batch results are routed by a **Result Processor Lambda** (triggered by EventBridge)
through the same validator/reconciler pipeline. No scraper code is changed — the
routing is entirely infrastructure (CDK env var override for `SQS_QUEUE_URL`).

**Durable drain (LLM-2, `app/llm/queue/batcher.py`):** the staging queue is FIFO, so
`_drain_staging_queue` must delete each 10-message batch immediately to unlock the
message group. To avoid losing scraped records if the Lambda crashes after delete but
before the batch is handed off (Bedrock submit / on-demand re-enqueue), each batch's
**raw message bodies are checkpointed to S3 verbatim** (`recovery/{source}/{recovery_id}/{seq}.jsonl`,
single `put_object`) **before** the SQS delete. If the checkpoint put fails, that batch's
delete is skipped and the drain continues (messages return via visibility timeout — no
loss, no wedge). The checkpoint prefix is deleted only at the **commit point** — batch
path after the DynamoDB metadata write; on-demand path only when every re-enqueue
succeeded — so a surviving checkpoint always means the handoff did not complete. At the
start of every invocation, `_recover_orphaned_checkpoints` replays orphaned checkpoints
(from a prior crashed run) **verbatim via raw `send_message`** back to the staging queue
(never `send_to_sqs`, which would re-wrap the envelope and corrupt the job). Recovery is
**age-gated**: a prefix is replayed only when its newest object is older than
`_ORPHAN_MIN_AGE_S` (1200s > the 900s Lambda timeout), so an in-flight prefix from a
concurrent pipeline execution is never grabbed. `recovery_id` is derived from
`context.aws_request_id` (globally unique per invocation), not the second-granularity
`s3_safe_id`, so drain-loop re-invocations and retries can't overwrite each other's
checkpoints. The 7-day S3 lifecycle on the batch bucket is the final backstop. Grep
CloudWatch for `checkpoint_put_failed`, `batcher_recovery_replayed`, `batcher_recovery_scan_failed`,
`checkpoint_cleanup_failed`. **Residual (documented, downstream-idempotent):** if a crash
lands between a successful Bedrock submit+DynamoDB write and the checkpoint-prefix delete,
a later run replays those records → a second Bedrock job; the result processor is per-record
idempotent, so this is bounded waste, not loss or duplication of canonical data.

### Key Components

#### Pantry Pirate Radio Core Services
- **Scraper Framework**: Public framework for building scrapers (`ScraperJob` base class, utilities)
  - **Private Scrapers Submodule**: 30+ production scrapers in `app/scraper/scrapers/` (requires access)
  - **Sample Scraper**: Example implementation available for all contributors
- **Content Store**: SHA-256 deduplication preventing duplicate processing
  - **Backend Abstraction**: Pluggable `ContentStoreBackend` protocol supports local filesystem (`file`) or AWS S3+DynamoDB (`s3`)
  - **Stale job-link recovery (SQS mode)**: `index_set_job_id` stamps a `job_linked_at` timestamp (SQLite column / DynamoDB attribute). In SQS mode (no Redis to probe RQ liveness) `store_content` clears a result-less `job_id` once it is older than `CONTENT_STORE_STALE_JOB_THRESHOLD_HOURS` (default 72) so a terminally-failed record re-enqueues instead of dedup-skipping forever. Recent (in-flight) links and legacy links with no timestamp are left alone, avoiding the historic 124k re-enqueue storm. Grep CloudWatch for `content_store_stale_job_link_cleared`.
- **LLM Workers**: HSDS schema alignment with OpenAI/Claude/Bedrock providers
- **Validator Service**: Confidence scoring, data enrichment, and quality control
- **Reconciler**: Creates canonical records with version tracking
- **Submarine**: Post-reconciler web crawling enrichment using crawl4ai to fill missing hours/phone/email/description. Two-phase architecture: crawl (Fargate, real-time) then extract (Bedrock batch inference at 50% cost, or on-demand fallback). Includes content relevance filtering (keyword gate + LLM signal). Only updates fields that were actually missing (selective field update). Weekly scanner via Step Functions (prod), manual via `./bouy submarine --aws` (dev).
- **API**: Read-only HSDS v3.1.1 compliant REST endpoints
  - **AWS Deployment**: Lambda + API Gateway HTTP API (serverless, zero idle cost)
  - **Local Development**: Docker via `./bouy up` (unchanged, uses `app/main.py`)
  - **Lambda Entry Point**: `app/api/lambda_app.py` (no Redis/LLM deps), handler via Mangum
  - **ECR Repository**: `api-lambda` (slim ~300MB image vs 10GB full image)
- **HAARRRvest Publisher**: Syncs processed data to public repository

#### Data Validation Pipeline
- **Confidence Scoring**: Build-up model — scraped data starts at base 60, earns bonuses for completeness. Capped at 90 for scraped data; only human corrections (Write API) reach 91-100.
- **Source Corroboration**: Locations confirmed by multiple scrapers receive +5 (2 sources) or +10 (3+ sources) bonus, applied during reconciliation.
- **Matched-location merge (field-level, source-aware)** (`app/reconciler/location_commit.py:_commit_matched_location` → `MergeStrategy.merge_location`; extracted from `job_processor.py` in the P1 §IX decomposition): when an incoming scrape matches an existing canonical row, the reconciler does **not** last-write-wins overwrite name/description/coordinates. It records the scrape in `location_source`, then `merge_location` recomputes the canonical fields across **all** of the location's scraper sources — name by majority vote, description = longest non-empty, coordinates = most-recent — and applies the source-corroboration bonus in the same pass (owner-protected rows are skipped; drift events emitted). Corroboration is applied **once**, by `merge_location` (the old separate `_apply_corroboration_bonus` helper was removed — keeping both double-applied the bonus). `merge_location` is passed the per-job validator score (not the canonical's already-bonused score) so the bonus stays idempotent across reprocesses, and runs inside a try/except logging `merge_location_failed` so a merge failure can't abort the job (Principle XI). **Organization link**: `merge_location` never touches `organization_id`; the matched branch fills it **only when the canonical row has none** (`UPDATE ... SET organization_id WHERE organization_id IS NULL` + owner guard) — this enriches a missing link without ever wiping or flipping an existing one (the old path bound `organization_id=NULL` on org-less re-scrapes, the same class as SUB-1). Submarine jobs are enrichment, not confirmation (v1.5.1), and are excluded — they use `SubmarineLocationHandler` and never route through `merge_location`. Known limitation: `record_version` still logs each job's raw submission, so for multi-source locations it diverges from the merged canonical row (audit-of-submission vs merged-state). Coordinate selection remains most-recent (per-source geocoder quality is not stored on `location_source`, so "coords by best geocoder" is a future change gated on adding that column).
- **Reconciler Location Matching Tiers** (`app/reconciler/location_creator.py:find_matching_location_with_lock`): Three-tier match under one advisory lock. **Tier 1** strict coord-only within `RECONCILER_LOCATION_TOLERANCE` (~11m). **Tier 2** wider coord within `RECONCILER_DUPLICATE_TOLERANCE` (~165m) + exact-name OR same-organization gate; fires only when `name` or `organization_id` is supplied. **Tier 3** widest coord within `_DEDUP_LOOSE_DEG` (~200m) + pg_trgm fuzzy gate (`similarity(name) > 0.5` OR `similarity(address_1) > 0.7` AND zip5 agreement); fires only when `name` or `address_1+zip5` is supplied. Tier 3 excludes `verified_by IN ('admin','source','claimed')` so human-curated rows are never merged into. Shared constants live in `app/reconciler/dedup.py` and are imported by the PTF API endpoint so the prevent-on-ingest and hide-on-serve paths stay in lockstep. Grep CloudWatch for `reconciler_tier3_fuzzy_merge` and watch the `PantryPirateRadio/Reconciler/Tier3FuzzyMerge` metric.
- **Schedule recurrence-identity upsert** (`app/reconciler/service_creator.py:update_or_create_schedule`): the existing-row lookup keys on the entity (service_at_location / service / location) **AND** the recurrence identity (`freq`, `byday`, `bymonthday`) via NULL-safe `IS NOT DISTINCT FROM`. This keeps a location's distinct windows (e.g. Mon 9–12 and Thu 1–5) as separate rows instead of collapsing them under the old entity-only `LIMIT 1` lookup, while an unchanged recurrence with corrected hours/description still updates in place. Identity excludes `opens_at`/`closes_at`, so a same-day window with different hours currently coincides on `byday` (rare). The lookup never deletes — a *changed* recurrence (e.g. MWF→MTWThF) leaves the prior row; cleaning those orphans safely needs source/job attribution on the `schedule` table (no attribution today → deletion would risk clobbering another source's valid window), tracked as follow-up.
- **Enrichment**: Enhances incomplete data using geocoding services
- **Rejection**: Filters out test data and low-quality records
- **Caching**: Redis-based caching for performance optimization
- **RFC 5545 `schedule.byday` + `schedule.bymonthday` enforcement**: Canonical normalizers (`normalize_byday`, `normalize_bymonthday`) at `app/utils/ical.py` (duplicated verbatim to `plugins/ppr-write-api/app/ical.py`) are the single source of truth. Enforced at four seams:
  1. Submarine result builder (`app/submarine/result_builder.py`) — each hours entry must carry `freq` + exactly one of `byday`/`bymonthday`; otherwise dropped with `submarine_schedule_entry_incomplete` / `submarine_schedule_entry_inconsistent` warn logs.
  2. Reconciler `_transform_schedule` (`app/reconciler/job_processor.py`) — coerces or drops to NULL with `reconciler_byday_dropped` / `reconciler_bymonthday_dropped` warn logs.
  3. `ScheduleInfo` Pydantic model (`app/models/hsds/response.py`) — `@field_validator` on both `byday` and `bymonthday` normalizes or raises.
  4. Write API `ScheduleUpdate` (`plugins/ppr-write-api/app/models.py`) — same validators for authenticated edits.

  **byday** coerces: Unicode minus (U+2212) → ASCII `-`; `L<DAY>` → `-1<DAY>`; prose (`Third Tuesday` → `3TU`, whitelist of `first..fifth,last` × weekdays); full day names → 2-letter codes. Rejects: `today`/relative dates, truncated codes (`3F`), bare integers, any token that doesn't match `^[+-]?[1-5]?(MO|TU|WE|TH|FR|SA|SU)$`.

  **bymonthday** accepts day-of-month numbers 1..31 or -1..-31, comma-separated (e.g., `15`, `1,15`, `1,-1`, `-1`). Rejects: 0, 32+, prose, weekday codes, leading zeros, anything not matching `^-?([1-9]|[12][0-9]|3[01])$` per token.

  Grep CloudWatch for `ical_byday_unrecognized` / `ical_bymonthday_unrecognized` / `reconciler_byday_dropped` / `reconciler_bymonthday_dropped` / `submarine_schedule_entry_*` to find new drift patterns.

#### FANO Allowlist (PTF endpoints)

The PTF partner endpoints (`/api/v1/partners/ptf/locations` and `/locations/{id}`) emit a `feeding_america_food_bank` enrichment block and an `affiliations` array (`["FANO"]` for Feeding America Network Organization affiliates). Both are gated on a curated allowlist of scrapers at `app/api/v1/partners/ptf/fano_allowlist.tsv` — locations whose only sources are aggregators (`foodfinder_us`, `food_helpline_org`, `getfull_app_api`, `the_food_pantries_org`, `freshtrak`), enrichments (`submarine` source_type, `human_update`, `portal_ingest`), or non-FA regional indexes do not receive FANO add-on data. A SQL `qualifying_source` CTE in `app/api/v1/partners/ptf/locations_queries.py` computes the gate; the transformer in `app/api/v1/partners/ptf/locations_transformer.py` emits `ptf_fano_suppressed_no_qualifying_source` (INFO) when the ZIP matches `feeding_america_zip_coverage` but the source did not qualify.

## Troubleshooting Common Issues

### Docker Issues
```bash
# Check Docker is running
docker --version
docker ps

# Clean up Docker resources
docker system prune -a       # Remove all unused containers, networks, images
./bouy clean                 # Remove project volumes and containers

# Rebuild from scratch
./bouy clean
./bouy build --no-cache
./bouy up --with-init
```

### Test Failures
```bash
# Run specific failing test with verbose output
./bouy test --pytest -- -vsx tests/test_failing.py

# Check for formatting issues
./bouy test --black          # Auto-fixes formatting
./bouy test --ruff           # Shows linting issues

# Type checking issues
./bouy test --mypy -- --show-error-codes
```

### Database Issues
```bash
# Reset database completely
./bouy down
./bouy clean
./bouy up --with-init        # Reinitialize database

# Check database connection
./bouy shell db
psql -U postgres -d pantry_pirate_radio -c "SELECT 1;"
```

### Service Issues
```bash
# Check service logs
./bouy logs app              # Check application logs
./bouy logs worker           # Check worker logs
./bouy logs db               # Check database logs

# Restart specific service
./bouy down app
./bouy up app

# Check service health
./bouy ps                    # Shows all service statuses
```

## Constitution Requirements

See [constitution.md](constitution.md) for full details. Key principles:

1. **Docker-First Development (NON-NEGOTIABLE)** - Everything via `./bouy`. No local Python/poetry/docker-compose.
2. **HSDS Specification Compliance (NON-NEGOTIABLE)** - All data output conforms to HSDS. Pydantic models are canonical schema.
3. **Test-Driven Development (NON-NEGOTIABLE)** - Tests before code. Coverage ratchet enforced (no regression).
4. **Pipeline Stage Boundaries** - Clear contracts per stage. Scrapers don't geocode or write to DB.
5. **Scraper Consistency** - All scrapers use `ScraperJob` base class, naming conventions, file patterns.
6. **Data Quality for Vulnerable Populations (NON-NEGOTIABLE)** - Confidence scoring, test data rejection, validation before publish.
7. **Privacy and Security** - No PII. Read-only public API. bandit/safety must pass.
8. **Content Deduplication** - SHA-256 content store is mandatory path between scrapers and LLM queue.
9. **File Size and Complexity Limits** - 600 lines max for app files. Cyclomatic complexity <=15.
10. **Consistent Quality Gates** - black + ruff + mypy + bandit + pytest must all pass. No exceptions.
11. **Pipeline Resilience** - Failures isolated per-scraper. Retry with backoff. No silent data loss.
12. **Structured Logging** - structlog only. Structured context fields. Prometheus metrics.
13. **Documentation Maintenance** - CLAUDE.md updated with code changes. Docs not deferred.

## Write API (ppr-write-api plugin)

The authenticated write API for location data management is now a separate plugin at `plugins/ppr-write-api/`. It runs as a Lambda function in VPC with RDS Proxy access, exposed via function URL.

See `plugins/ppr-write-api/CLAUDE.md` for full documentation.

## Federation (HSDS federation core)

### Federation (core) — P0 foundations

Every PPR deployment is (becoming) a federating node in an open HSDS food-resource network — peers discover each other, publish signed snapshots of their data, and pull/corroborate each other's records. Federation is a **core capability, on by default** (gated by nothing in P0; the `FEDERATION_ENABLED` kill switch the publish surface will sit behind is fully enforced in P1). Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`; living plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`; epic #519.

**P0 surface shipped (discoverable in BOTH Uvicorn and the slim Lambda):** registered via `app/federation/routes_public.py:register_federation_public_routes`, wired into both apps.
- `GET /.well-known/hsds-federation` — federation discovery doc.
- `GET /.well-known/did.json` — `did:web` document with the ordered recovery-key schema (design §6.1a). Returns 404 until both `FEDERATION_DID` and `FEDERATION_SIGNING_KEY` are configured.
- `GET /.well-known/webfinger?resource=` — RFC 7033 JRD.
- `GET /api/v1/federation/actor` — ActivityStreams actor document.

**Primitives in `app/federation/`:**
- `fetch.py` — SSRF-hardened outbound egress helper: HTTPS-only, blocks internal IPs / CGNAT / IPv6-ULA. **Note:** the DNS-rebinding connect-pin and the streaming byte-cap are deferred to P2/P3 and are hard gates on the first real outbound fetch (no live peer fetch happens in P0).
- `canonical.py` — RFC 8785 JCS canonicalization (minimal serializer, ES6 number formatting); the normative byte form used for hashing/signing. Entry point `jcs_bytes()`.
- `signing.py` — minimal RFC 9421 Ed25519 HTTP Message Signatures + RFC 9530 `Content-Digest`.
- `identity.py` — `did:web` doc, actor, WebFinger, Ed25519 key loading, base58btc multibase encoding **and decoding** (`public_key_from_multibase` — the byte-inverse of `public_key_multibase`: a federating peer resolves another node's trust anchor from the `publicKeyMultibase` in that node's `/.well-known/did.json` before verifying its checkpoints/envelopes; rejects a non-base58btc / non-ed25519-multicodec / wrong-length string rather than yielding a key a verifier would then trust).
- `discovery.py` — the discovery-doc builder.

**Config (on by default):**
- `FEDERATION_ENABLED` (default `True`) — the publish-surface kill switch (fully enforced in P1).
- `FEDERATION_DID`, `FEDERATION_SIGNING_KEY` (secret), `FEDERATION_HSDS_VERSIONS`, `FEDERATION_DOMAIN`, `FEDERATION_PROFILE_URI`, `FEDERATION_ALLOW_LIST_POLICY`, `FEDERATION_CONTACT`, `FEDERATION_RETENTION_DAYS`, `FEDERATION_DATE_SKEW_SECONDS`, `FEDERATION_INGEST_MAX_RECORDS_PER_PEER_PER_DAY`, `FEDERATION_INGEST_MAX_LLM_JOBS_PER_PEER_PER_DAY`, `FEDERATION_EXPORT_PAGE_SIZE`.

**HSDS version note (Principle II):** the API advertises HSDS **3.1.1** because the Pydantic models in `app/models/hsds/` genuinely implement the 3.1.1 shape. The vendored `docs/HSDS/` submodule is v3.2.3 — a spec-only bump; the models do **not** yet carry 3.2's `additional_websites` / `additional_urls` / `attributes` / `metadata`, so advertising 3.2.3 would overstate conformance. The multi-file HSDS Profile lives at `profiles/hsds-ppr/` (RFC 7386 merge patches adding optional `confidence_score` / `verified_by` / `sources`) and is advertised via the API root `profile` field (`= settings.FEDERATION_PROFILE_URI`).

**`source_type='federated_node'`:** the reserved `location_source.source_type` value that federated peers' records will carry once ingest lands (P2). Reserved only — **not yet wired in P0**.

**P1 status (verifiable publish — ✅ COMPLETE, #522 CLOSED 2026-06-08):**
- **Shipped:** the verifiable Merkle log + signed C2SP checkpoints + `/api/v1/federation/export | state.txt | checkpoint | history` (PR-A/B/C); the HSDS-FX conformance suite (Level-1 wire vectors + Level-2 live-node loop, 10 areas, externally-anchored KATs; #567–#572).
- **The §15 P1 golden journey (the "raw sync" two-node loop)** — `tests/test_federation/test_hsdsfx_two_node.py`. Node B **discovers** Node A's trust anchor from A's served `/.well-known/did.json` (decodes the `#main-key` `publicKeyMultibase` via `identity.public_key_from_multibase` — nothing handed in), then pulls `/export@N` and cross-verifies A's signed checkpoint + every envelope signature + RFC-6962 inclusion proofs + a consistency proof across growth. Negatives: a swapped did.json key (proves the anchor flows from the served bytes, not a constant), a malformed multibase (rejected at discover), a forked second root (rejected by consistency). A and B are two **instances of the same code** sequenced over one `federation_log` table — genuine cross-node discovery + crypto-verification integration evidence and the partner-reuse seed, **NOT** a foreign-impl interop confirmation (that needs a non-PPR node, P7) and it promotes no `interop_pending` corpus row. Verify-only: pull INGEST / corroboration / authority / tombstone-redirect are P2.
- **Cold-start `_since=0` parity guard** — `tests/test_federation/test_coldstart_parity.py`. Locks Task 8's byte-equal invariant: a §8.2 aggregate rebuilt from the RAW tables (`build_location_aggregate`) byte-equals the `object` the live `/export` signed and serves (recovered via `log.read_export`, reconstructed byte-faithfully from `preimage_canonical`, never the float-normalized JSONB `object_canonical`). The load-bearing negative test proves a lossy `location_master`-style `DISTINCT ON (location_id)` schedule collapse produces different canonical bytes — so a flattened-view shortcut fails CI. Test-only; the aggregate already built from raw tables.
- **Archive tiering + retention prune (closes #522)** — `app/federation/retention.py`. The verifiable log recomputes every checkpoint root + proof on demand from the full `preimage_canonical` leaf bytes (no persisted Merkle frontier), so trimming a leaf would break `signed_checkpoint` and every proof spanning it. "Never destroy" (§6.2g) is therefore **archive-then-trim with read-back**: `prune_to_horizon` archives each over-SLA leaf's exact signed bytes to a never-expiring tier (write-ahead — archive durably BEFORE the live DELETE; an archive-put failure HALTS, no leaf loss) then trims the live Postgres window contiguously; `log.leaf_data` reads below-floor leaves back from the archive, so root@N + inclusion/consistency proofs across the trim boundary stay valid forever. `ArchiveBackend` = `LocalFsArchiveBackend` (Docker, atomic write) or `S3ArchiveBackend` (AWS, dedicated **no-lifecycle** bucket). `retention_horizon_sequence` (= `live_window_floor`) is exposed UNSIGNED on `/checkpoint` + an `X-Federation-Retention-Horizon` header on `/state.txt` (never in the signed C2SP note body). Dual-env (XV): `./bouy federation prune` (refuses without an archive tier) and an EventBridge-scheduled prune Lambda (`infra/stacks/federation_stack.py`, prod-only-enabled) — both call the same `prune_to_horizon`. XIV: a prune-Lambda Errors alarm (`monitoring_alarms.py`) → `pantry-pirate-radio-alerts-{env}`. Grep CloudWatch for `federation_archive_tiered` / `federation_archive_failed`. Below-floor `/export` still 410s (the cold-start S3/SQLite **snapshot** serving — bulk fresh-peer bootstrap — is the documented deferred follow-on; the archive WRITE + internal read-back ship here).

**Forthcoming (later phases):**
- **P2 (next — gate now lifted)** — pull ingest + corroboration: the "different datasets federating" scenario, `federated_node` source_type wiring, §117 verify-before-enqueue, §12.1 origin-dedup + CvRDT property test, Update/Announce/Delete authority + owner-guard, §11.6a equity caveat, per-peer budgets. **Headline acceptance = two LIVE PPR nodes (separate deployments/DBs/`did:web` DIDs/datasets) pull+verify+ingest+corroborate over real HTTP** — the demonstration that unlocks an unnamed partner who holds a complementary authoritative dataset and integrates once we show two of our own nodes federating live. ⚠️ There is **no Feeding America HSDS feed** (PPR scrapes FA sites; FA publishes none) — the old "live FA feed" P2 acceptance is void. A foreign/non-PPR node is P7.
- **P3** — `/inbox` push delivery.
- **P4** — the `./bouy federation` peer-add/remove/list/status command family.

**`federation_*` structlog grep targets:** none emitted in P0; these will be enumerated per phase starting P1 (per design §14) — e.g. (P1+: `federation_checkpoint_published`, `federation_proof_failed`, `federation_consistency_failed`, `federation_killswitch_active`, …).

## Plugin System

Plugins extend Pantry Pirate Radio with additional commands, compose overlays, and CDK stacks.

### Convention
- Plugins live in `plugins/<name>/`
- Each plugin has a `plugin.yml` manifest
- Optional compose overlay: `plugins/<name>/.docker/compose.yml`
- Optional commands: `plugins/<name>/commands/<subcmd>.sh`
- Optional CDK stacks: `plugins/<name>/infra/<module>.py`

### Bouy Integration
```bash
./bouy <plugin-name> <command>    # Run a plugin command
```

### CDK Discovery
Plugin CDK stacks are discovered automatically from `plugin.yml` → `infra.stacks[]` entries and added to the CDK app with dependencies on compute and secrets stacks.

## Recent Updates and Features

### Admin Portal Upload (`portal_ingest` scraper)
- **AWS-only feature** (Principle XV exemption): Lighthouse admin route `/admin/upload` lets operators bulk-ingest CSV/XLSX location rows.
- **Flow**: Lighthouse UI → `/api/upload` BFF (CSRF + admin role + `uploadData` permission + server-side parse) → `PPRClient.ingestUpload(rows, metadata)` → Write API `POST /ingest` → S3 ingest bucket → ECS RunTask launches the `portal_ingest` Fargate task → `PortalIngestScraper` reads S3 payload and emits one raw JSON row per entry via `self.submit_to_queue()` → Content Store (SHA-256 dedupe) → LLM → Validator → Reconciler (standard `verified_by='auto'`).
- **Scraper**: `app/scraper/scrapers/portal_ingest_scraper.py` (scrapers submodule). Reads from `UPLOAD_PAYLOAD_S3_URI` env var set by the ECS task override; stamps each row with `_portal_ingest: { upload_id, row_index, filename, uploaded_by }` for downstream attribution.
- **Provenance**: write-api-owned `ingest_audit` table (lazy `CREATE TABLE IF NOT EXISTS`, no cross-repo migration). Reconciled records still get a full `change_audit` row via the existing PUT /locations path when admins boost specific records.
- **Local Docker**: `/ingest` returns clean 503 — no docker-compose changes, no import errors (Principle XV exemption clause).
- **Permission**: `uploadData` admin-only in `plugins/ppr-lighthouse/src/lib/auth/permissions.ts`. Editors edit individual records via existing flows; bulk ingest requires admin.
- **Row limit**: 10,000 per upload (enforced client-side, server-side BFF, and Write API `IngestRequest` Pydantic model).

### Admin/editor confidence override
- **Inline editor in Lighthouse**: admins and editors can correct a location's `confidence_score` and `verified_by` directly from `/locations/[id]` via a pencil trigger next to the existing `ConfidenceBadge`. See `plugins/ppr-lighthouse/src/components/locations/confidence-editor.tsx`. Claimants never see the control.
- **Write API contract**: `PUT /locations/{id}` accepts three new optional fields on `LocationUpdateRequest` — `confidence_score` (0-100), `verified_by` (`auto`/`admin`/`source`/`claimed`), `reason` (max 500). Applied only when `caller_context.source in ('admin','editor')` **and** `caller_context.user_id` is present; any other source silently ignores them.
- **Audit trail**: successful overrides emit the structlog event `admin_confidence_override` with `user_id`, `username`, `actor_type`, `new_confidence_score`, `new_verified_by`, `reason`. Defense-in-depth rejections emit `admin_override_rejected_missing_user_id`. Grep CloudWatch for both.
- **No schema change**: the existing `location_source` audit row continues to carry full `caller_context` (including `reason`). Tier constants live in `app/validator/scoring.py:17-27`.

### Scraper Submarine (PR #404)
- **Post-Reconciler Enrichment**: Crawls food bank websites using crawl4ai to fill missing hours, phone, email, and description fields
- **Two-Phase Architecture**: Crawl (Fargate, real-time) → Staging Queue → Batch Extract (Bedrock batch inference at 50% cost) or on-demand fallback (<100 records)
- **Content Relevance Validation**: Two-tier filtering — keyword gate rejects non-food content before LLM extraction, LLM `is_food_related` signal provides secondary check
- **Selective Field Updates**: Only overwrites fields that were actually missing at dispatch time; extracted data validated against canonical HSDS Pydantic models
- **Schedule Persistence**: Hours extracted by submarine are persisted directly to location via `SubmarineLocationHandler`
- **Batch Inference Integration**: Extends existing batcher Lambda with `source="submarine"` parameter (DRY). ≥100 records → Bedrock batch (50% off), <100 → on-demand extraction queue
- **Step Functions Orchestration**: Weekly scans on AWS (prod). Scanner → Wait for crawlers → Batcher Lambda → Batch/on-demand extraction → Reconciler
- **Adaptive Cooldown**: success=30d, no_data=90d, error=14d, staged=pending. Prevents re-crawling
- **Scraper Filtering**: `--scraper NAME` flag to limit scans to locations from a specific scraper

### Data Validation Pipeline (Latest - Issues #362-#369)
- **Confidence Scoring System**: Build-up model — base score of 60, bonuses for data completeness (address +5, description +3, geocoder quality +5, phone/hours/website +3 each). Hard cap at 90 for scraped data; 100 reserved for human corrections via Write API (ppr-write-api).
- **Source Corroboration**: Multi-scraper confirmation boosts scores (+5 for 2 sources, +10 for 3+), applied during reconciliation merge.
- **Automated Data Enrichment**: Enhances incomplete data using geocoding services
- **Quality Rejection**: Automatically rejects test addresses and placeholder data
- **Redis-Based Service**: Distributed validation with caching for performance
- **Configurable Thresholds**: Customizable rejection threshold (default: 10)

### Geocoding Improvements
- **0,0 Coordinate Detection**: Automatic detection and correction of invalid (0,0) coordinates
- **Exhaustive Provider Fallback**: System now tries ALL available geocoding providers before accepting failure
- **Multi-Provider Support**: ArcGIS, Google Maps, Nominatim, and Census geocoding providers
- **Intelligent Caching**: TTL-based caching with rate limiting for geocoding requests

### Scraper Enhancements
- **scouting-party mode**: Run scrapers in parallel with configurable concurrency
- **full-broadside mode**: Maximum parallel execution for all scrapers
- **Dry run testing**: Test scrapers without processing using scraper-test command

### Docker Image Management
- **Pull command**: Fetch latest or specific version tags of all container images
- **Version tagging**: Support for pulling specific release versions (e.g., v1.2.3)

## Memories

### Test Command Notes
- Do not use 2>&1 in bouy test commands, it gets interpreted incorrectly
- Always use `./bouy test --pytest` for running tests, not `./bouy exec app poetry run pytest`
- Test commands automatically handle test environments, coverage, and dependencies
- The --coverage flag analyzes existing coverage reports (must run --pytest first)
- Black formatting check automatically updates files when run

### Docker and Container Notes
- All services run with consistent COMPOSE_PROJECT_NAME="pantry-pirate-radio"
- The shell command automatically detects bash or sh availability
- Logs follow by default, use -f flag for explicit follow if needed
- Clean command removes both services and volumes for fresh start
- Production mode includes Datasette viewer on port 8001

### Important Instructions
- NEVER create files unless they're absolutely necessary for achieving your goal
- ALWAYS prefer editing an existing file to creating a new one
- NEVER proactively create documentation files (*.md) or README files unless explicitly requested
- Do what has been asked; nothing more, nothing less
- Use bouy commands exclusively - no direct poetry or docker compose commands
- When debugging failures, use --verbose flag for detailed output
- For CI/CD integration, use --programmatic or --json flags for structured output

## Best Practices for Claude Code

### Command Usage
1. **Always use bouy** - Never use direct docker, docker-compose, or poetry commands
2. **Test before committing** - Run `./bouy test` to ensure all checks pass
3. **Use appropriate flags** - Add --verbose for debugging, --quiet for automation
4. **Check logs on failure** - Use `./bouy logs [service]` to diagnose issues

### Development Workflow
1. **Start fresh daily** - `./bouy down` then `./bouy up` to ensure clean state
2. **Test incrementally** - Use `./bouy test --pytest tests/specific_test.py` during development
3. **Format code automatically** - Run `./bouy test --black` to fix formatting
4. **Monitor services** - Use `./bouy ps` to check service health

### Debugging Tips
1. **Shell access** - Use `./bouy shell app` to debug inside container
2. **Verbose testing** - Add `-- -v` flag for detailed test output
3. **Stop on failure** - Use `-- -x` flag to stop tests at first failure
4. **Check coverage** - Run `./bouy test --coverage` after pytest

### Performance Tips
1. **Parallel scrapers** - Use `scouting-party` mode for faster scraping
2. **Selective services** - Start only needed services: `./bouy up app worker`
3. **Cached builds** - Reuse Docker cache unless changes require `--no-cache`
4. **JSON output** - Use `--json` flag for machine-readable output in scripts
- run all single test files using ./bouy exec app pytest \
./bouy test does not properly handle selecting test files.
