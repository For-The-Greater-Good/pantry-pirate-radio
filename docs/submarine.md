# Submarine Service

The submarine service is a post-reconciler web crawling enrichment system that fills missing data fields on existing locations by crawling food bank websites. It uses crawl4ai for markdown extraction and LLM-based field extraction to populate phone numbers, hours, email addresses, and descriptions that were not available during the initial scraping and reconciliation pass.

## Overview

After the reconciler creates or updates a location, the submarine dispatcher checks whether the location has a website URL and is missing any of the four target fields: phone, hours, email, or description. If gaps are detected and the location is not in cooldown, a `SubmarineJob` is enqueued for the submarine worker. The worker crawls the website, filters for food-related content, extracts structured fields using an LLM, and sends the enriched data back to the reconciler for a selective update.

Submarine results bypass the validator service intentionally. Submarine targets existing validated locations (coordinates already verified) and only fills missing text fields that have no geographic validation requirements. The reconciler's `SubmarineLocationHandler` handles merge logic with selective field updates.

## Data Pipeline Integration

The submarine operates as a feedback loop after the main pipeline:

```
Main Pipeline:
Scrapers -> Content Store -> LLM Queue -> Workers -> Validator -> Reconciler -> Database

Submarine Loop (triggered by Reconciler):
Database -> Dispatcher (gap detection) -> Submarine Queue -> Crawler -> LLM Extractor
    -> Result Builder -> Reconciler Queue -> Reconciler (selective update) -> Database
```

On AWS, the crawl and extraction phases are decoupled:

```
Database -> Scanner (ECS task) -> Submarine Queue -> Fargate Crawlers
    -> Submarine Staging Queue -> Batcher Lambda
        -> [>=100 records] Bedrock Batch Inference (50% cost savings)
        -> [<100 records]  Submarine Extraction Queue -> Fargate Extraction Workers
    -> Result Processor -> Reconciler Queue -> Reconciler -> Database
```

## Architecture

### Components

1. **SubmarineDispatcher** (`app/reconciler/submarine_dispatcher.py`)
   - Called by the reconciler after processing a location
   - Checks for website URL (organization, location, or linked service)
   - Detects missing target fields by querying the database
   - Enforces adaptive cooldown based on previous crawl status
   - Prevents re-entry cycles (rejects jobs where `scraper_id == "submarine"`)
   - Enqueues `SubmarineJob` to Redis (local) or SQS (AWS)

2. **Scanner** (`app/submarine/scanner.py`)
   - Batch scanner for manual or Step Functions-triggered scans
   - Queries the database for all locations with website URLs and non-rejected validation status
   - Supports filtering by scraper ID and limiting the number of jobs
   - Bypasses `SUBMARINE_ENABLED` flag (manual trigger works even when auto-dispatch is off)
   - Entry point: `python -m app.submarine scan`

3. **SubmarineCrawler** (`app/submarine/crawler.py`)
   - Crawls food bank websites using crawl4ai with headless Chromium
   - Fetches the main page and extracts markdown content
   - Identifies relevant internal links (Contact, Hours, About, Services) via regex patterns
   - Follows up to `max_pages - 1` relevant links (default max_pages: 3)
   - Skips irrelevant links (Donate, Volunteer, Blog, News, etc.)
   - Returns combined markdown from all crawled pages as a `CrawlResult`
   - Enforces per-domain rate limiting via `SubmarineRateLimiter`
   - Browser configuration: headless, text-only, stealth mode, overlay removal

4. **SubmarineExtractor** (`app/submarine/extractor.py`)
   - Extracts structured HSDS fields from crawled markdown using the project's LLM provider
   - Builds extraction prompts with field descriptions for phone, hours, email, description
   - Always includes `is_food_related` as a secondary content relevance signal
   - Parses LLM JSON response, filtering to only non-null requested fields
   - Returns empty dict if the LLM determines content is not food-related
   - Raises `ExtractionError` on LLM failures (maps to 14-day cooldown, not 90-day)
   - Truncates input to ~12,000 characters to stay within token limits

5. **SubmarineResultBuilder** (`app/submarine/result_builder.py`)
   - Converts `SubmarineResult` into a `JobResult` for the reconciler queue
   - Maps extracted fields to HSDS-structured data (organizations, locations, services)
   - Only includes fields that are in `job.missing_fields` AND were actually extracted
   - Validates phone numbers against `PhoneInfo` Pydantic model
   - Validates schedules against `ScheduleInfo` Pydantic model
   - Normalizes day names to RFC 5545 RRULE abbreviations (e.g., "monday" to "MO")
   - Sets metadata: `scraper_id="submarine"`, `source_type="submarine"`, `location_id`
   - Submarine results are excluded from source corroboration scoring

6. **SubmarineLocationHandler** (`app/reconciler/submarine_location_handler.py`)
   - Handles submarine-specific location resolution and updates in the reconciler
   - Resolves target location by direct ID lookup (not coordinate matching)
   - Builds dynamic SQL SET clause so omitted fields are not overwritten
   - Persists extracted schedules directly to the location record (submarine results have no services, so schedules cannot flow through the normal `service_at_location` path)

7. **SubmarineRateLimiter** (`app/submarine/rate_limiter.py`)
   - Per-domain request throttling for polite web crawling
   - Tracks last request timestamp per domain
   - Enforces configurable minimum delay between requests (default: 5 seconds)
   - Identifies itself with a descriptive User-Agent string

### AWS-Specific Components

8. **Fargate Crawler Worker** (`app/submarine/fargate_worker.py`)
   - Polls SQS submarine queue for jobs
   - Delegates to the standard `process_submarine_job` function
   - Forwards enriched `JobResult` to the reconciler SQS queue via `PipelineWorker`

9. **Staging Pipeline** (`app/submarine/staging.py`)
   - On AWS, after a successful crawl + relevance gate, the worker stages the pre-built extraction prompt to the submarine-staging SQS queue instead of extracting inline
   - `SubmarineStagingMessage` carries the prompt, original job context, and crawl metadata
   - The batcher Lambda drains these messages and decides batch vs on-demand

10. **Extraction Worker** (`app/submarine/extraction_worker.py`)
    - On-demand fallback path when the batcher has fewer than 100 records
    - Consumes `SubmarineStagingMessage` from the submarine-extraction queue
    - Calls Bedrock Converse API directly for LLM extraction
    - Builds `JobResult` and sends to reconciler queue

11. **SubmarineStack** (`infra/stacks/submarine_stack.py`)
    - Step Functions state machine orchestrating the full scan-crawl-extract pipeline
    - Inline check-queue Lambda that polls SQS depth
    - EventBridge rule for weekly scheduling (enabled in prod, disabled in dev)

## Content Relevance Filtering

Submarine uses a two-tier content relevance system to avoid extracting data from non-food-related websites:

### Tier 1: Keyword Gate (Pre-LLM)

Located in `app/submarine/worker.py`, the `_check_content_relevance()` function performs a case-insensitive keyword scan on the crawled markdown. At least 2 distinct keyword matches are required from this list:

- food bank, food pantry, food distribution, food assistance
- food shelf, food closet, food program, food insecurity
- free food, food box, pantry, grocery
- hunger, feeding, snap, wic, meal program

Content that fails the keyword gate is rejected with status `no_data` and reason `content_not_food_related`. This avoids spending LLM tokens on irrelevant content.

### Tier 2: LLM `is_food_related` Signal (During Extraction)

The extractor always includes `is_food_related` in the LLM prompt alongside the requested fields. If the LLM explicitly returns `is_food_related: false`, the extractor returns an empty dict, which results in a `no_data` status with 90-day cooldown.

## Selective Field Updates

Submarine only updates fields that were actually missing at dispatch time. This is enforced at multiple levels:

1. **Dispatcher**: `_detect_missing_fields()` queries the database for each target field (phone, hours/schedules, email, description). Only fields confirmed missing are included in `SubmarineJob.missing_fields`.

2. **Result Builder**: `_build_hsds_data()` only maps fields that are in `job.missing_fields` AND were returned by the LLM. Fields not in the missing list are omitted from the HSDS data dict entirely.

3. **Location Handler**: `update_location()` builds a dynamic SQL SET clause from only the fields present in the location dict. Omitted fields are not touched in the database.

4. **Schedule Persistence**: `persist_schedules()` writes extracted schedules directly to the location via `update_or_create_schedule`, since submarine results have no services to attach schedules to.

## Adaptive Cooldown

The dispatcher enforces cooldown periods between crawl attempts based on the outcome of the last crawl. Cooldown values are configured in `config/defaults.yml` and can be overridden via environment variables:

| Last Status | Cooldown | Rationale |
|-------------|----------|-----------|
| `success` / `partial` | 30 days | Data found; re-check monthly for updates |
| `no_data` / `blocked` | 90 days | Site has no useful data or blocks crawlers; long wait |
| `error` | 14 days | Transient failure; retry sooner |
| `staged` | Pending | Awaiting batch extraction; do not re-dispatch |
| `None` (never crawled) | 0 days | No cooldown; eligible immediately |

Cooldown is tracked on the `location` table via two columns:
- `submarine_last_crawled_at`: Timestamp of the last crawl attempt
- `submarine_last_status`: Status string from `SubmarineStatus` enum

## Step Functions Orchestration (AWS)

The `SubmarineStack` creates a Step Functions state machine with the following flow:

```
RunSubmarineScan (ECS Fargate task)
    |
    v
WaitForCrawlSoak (30 minutes)
    |
    v
CheckCrawlersDone (Lambda checks SQS queue depth)
    |
    +--> Queue not empty --> WaitMoreForCrawlers (5 minutes) --> CheckCrawlersDone
    |
    +--> Queue empty --> RunBatcher (Lambda, source="submarine")
                            |
                            v
                        ScanComplete (Success)
```

Error handling:
- `RunSubmarineScan` retries up to 2 times with 120-second intervals and 2x backoff
- `RunBatcher` retries up to 2 times with 60-second intervals
- Both steps catch all errors and transition to terminal fail states (`ScanFailed`, `BatchFailed`)

The batcher Lambda (shared with the scraper pipeline) handles submarine-specific routing via the `source="submarine"` parameter:
- 100+ records: Bedrock batch inference at 50% cost savings
- Fewer than 100 records: Re-enqueues to the submarine-extraction queue for on-demand Fargate processing

### Scheduling

- **Production**: Weekly schedule via EventBridge (configurable, default `rate(7 days)`)
- **Development**: Schedule disabled by default; manual trigger via `./bouy submarine --aws`

## Data Models

### SubmarineJob

```python
class SubmarineJob(BaseModel):
    id: str
    location_id: str
    organization_id: str | None = None
    website_url: str
    missing_fields: list[str]       # e.g. ["phone", "hours", "email", "description"]
    source_scraper_id: str          # Original scraper that created this location
    location_name: str = ""
    latitude: float | None = None
    longitude: float | None = None
    attempt: int = 0
    max_attempts: int = 3
    created_at: datetime
    metadata: dict[str, Any] = {}
```

### SubmarineResult

```python
class SubmarineResult(BaseModel):
    job_id: str
    location_id: str
    status: SubmarineStatus         # success, partial, no_data, error, blocked, staged
    extracted_fields: dict[str, Any] = {}  # e.g. {"phone": "555-1234"}
    crawl_metadata: dict[str, Any] = {}    # url, pages_crawled, links_followed
    error: str | None = None
```

Validation rules:
- `success` or `partial` status requires non-empty `extracted_fields`
- `error` status requires a non-empty `error` string

### SubmarineStatus

```python
class SubmarineStatus(str, Enum):
    SUCCESS = "success"    # All requested fields extracted
    PARTIAL = "partial"    # Some but not all requested fields extracted
    NO_DATA = "no_data"    # Crawl succeeded but no useful data found
    ERROR = "error"        # Crawl or extraction failed
    BLOCKED = "blocked"    # Site blocked the crawler
    STAGED = "staged"      # Crawl succeeded, extraction staged for batch inference
```

### SubmarineStagingMessage

```python
class SubmarineStagingMessage(BaseModel):
    job_id: str
    location_id: str
    submarine_job: dict[str, Any]   # Serialized SubmarineJob for result building
    prompt: list[dict[str, str]]    # Chat messages for LLM extraction
    missing_fields: list[str]       # Which fields to extract
    crawl_metadata: dict[str, Any] = {}
    created_at: datetime
```

### Target Fields

The canonical set of fields submarine can extract is defined as a frozen set:

```python
SUBMARINE_TARGET_FIELDS = frozenset({"phone", "hours", "email", "description"})
```

## CLI Commands

### Local Commands

```bash
# Scan for locations with gaps and enqueue submarine jobs
./bouy submarine scan

# Scan with filters
./bouy submarine scan --scraper NAME           # Filter to one scraper
./bouy submarine scan --scraper NAME --limit 5 # Limit number of jobs

# Check submarine crawl status
./bouy submarine status

# Follow submarine worker logs
./bouy submarine logs
```

### AWS Commands

```bash
# Trigger full submarine pipeline via Step Functions
./bouy submarine --aws

# Filter by scraper on AWS
./bouy submarine --aws --scraper NAME
```

### Direct Module Invocation

```bash
python -m app.submarine scan [--limit N] [--location-id UUID] [--scraper NAME]
python -m app.submarine status
```

The scan command also accepts environment variables as fallbacks for Step Functions invocation:
- `SUBMARINE_LIMIT`: Maximum number of jobs to enqueue
- `SUBMARINE_SCRAPER_FILTER`: Filter to locations from a specific scraper

## Configuration

All submarine settings are defined in `config/defaults.yml` under the `submarine` key and exposed via `app/core/config.py`. Environment variables override defaults.

| Setting | Default | Description |
|---------|---------|-------------|
| `SUBMARINE_ENABLED` | `true` | Enable automatic dispatch from the reconciler |
| `SUBMARINE_CRAWL_TIMEOUT` | `30` | Crawl timeout in seconds (per page) |
| `SUBMARINE_MAX_PAGES_PER_SITE` | `3` | Maximum pages to crawl per website (1 main + N-1 links) |
| `SUBMARINE_MIN_CRAWL_DELAY` | `5` | Minimum seconds between requests to the same domain |
| `SUBMARINE_MAX_ATTEMPTS` | `3` | Maximum retry attempts per job |
| `SUBMARINE_COOLDOWN_SUCCESS_DAYS` | `30` | Cooldown after successful crawl |
| `SUBMARINE_COOLDOWN_NO_DATA_DAYS` | `90` | Cooldown after no useful data found |
| `SUBMARINE_COOLDOWN_ERROR_DAYS` | `14` | Cooldown after crawl error |

### AWS Environment Variables

These are set by CDK and are not configured manually:

| Variable | Description |
|----------|-------------|
| `QUEUE_BACKEND` | Set to `sqs` on AWS to enable SQS-based queue routing |
| `SUBMARINE_QUEUE_URL` | SQS FIFO queue URL for submarine jobs |
| `SUBMARINE_STAGING_QUEUE_URL` | SQS FIFO queue URL for crawled content awaiting extraction |
| `SUBMARINE_EXTRACTION_QUEUE_URL` | SQS FIFO queue URL for on-demand extraction fallback |
| `RECONCILER_QUEUE_URL` | SQS FIFO queue URL for forwarding results to the reconciler |
| `BEDROCK_MODEL_ID` | Model ID for Bedrock extraction (default: `us.anthropic.claude-haiku-4-5-20251001-v1:0`) |

## Code Locations

| Component | Path |
|-----------|------|
| Scanner | `app/submarine/scanner.py` |
| Crawler | `app/submarine/crawler.py` |
| Extractor | `app/submarine/extractor.py` |
| Models | `app/submarine/models.py` |
| Worker (local) | `app/submarine/worker.py` |
| Worker (AWS crawl) | `app/submarine/fargate_worker.py` |
| Worker (AWS extract) | `app/submarine/extraction_worker.py` |
| Staging model | `app/submarine/staging.py` |
| Rate limiter | `app/submarine/rate_limiter.py` |
| Result builder | `app/submarine/result_builder.py` |
| Status reporter | `app/submarine/status.py` |
| CLI entry point | `app/submarine/__main__.py` |
| Dispatcher | `app/reconciler/submarine_dispatcher.py` |
| Location handler | `app/reconciler/submarine_location_handler.py` |
| CDK stack | `infra/stacks/submarine_stack.py` |
| Shared config | `config/defaults.yml` (submarine section) |

## Error Handling

1. **Crawl Failures**
   - `crawl4ai` not installed: Returns `error` status immediately
   - Network/timeout errors: Returns `error` status if no pages crawled, `partial` if some pages succeeded
   - Empty content: Returns `no_data` status

2. **Content Filtering**
   - Keyword gate failure: Returns `no_data` with `rejection_reason: content_not_food_related`
   - LLM `is_food_related: false`: Returns empty extraction, maps to `no_data`

3. **Extraction Failures**
   - LLM provider error: Raises `ExtractionError`, maps to `error` status (14-day cooldown)
   - JSON parse failure: Raises `ExtractionError` with response preview
   - Invalid phone/schedule: Logged as warning, field skipped (other fields still processed)

4. **Queue Forwarding**
   - On local/Redis: Enqueues to reconciler queue, updates location status only after successful forwarding
   - On AWS/SQS: `PipelineWorker` handles forwarding; status updated after forwarding to prevent data loss window

5. **Cycle Prevention**
   - Dispatcher rejects jobs where `scraper_id == "submarine"` or `source_type == "submarine"`
   - Prevents infinite loops where submarine results trigger new submarine jobs
