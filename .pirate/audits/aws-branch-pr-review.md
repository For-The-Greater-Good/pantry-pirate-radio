# PR Review: `aws` Branch — Comprehensive Audit Report

**Branch:** `aws` | **PR:** #396 | **Scope:** 180 files, ~30K insertions, 25 commits
**Review Date:** 2026-03-08
**Methodology:** 17 specialized review agents across 8 functional areas

---

## Executive Summary

The `aws` branch adds complete AWS deployment infrastructure to Pantry Pirate Radio: CDK stacks, SQS pipeline workers, S3/DynamoDB content store, Bedrock LLM provider, Lambda API, batch inference, monitoring, and operational tooling. The architecture is well-conceived — protocol-based backend abstractions, shared pipeline config, and dual-environment support are strong design choices.

However, the review identified **23 critical issues**, **40 important issues**, and **10 suggestions**. The most dangerous findings fall into three categories:

1. **Security vulnerabilities** — SQL injection, SSRF, script injection in CI
2. **Silent data loss paths** — Missing error handling in requeue/delete operations, silent config fallbacks, workers that exit cleanly on fatal errors
3. **Monitoring gaps** — DLQ naming mismatch (alarms will never fire), missing `treat_missing_data` (scale-from-zero broken for 3 services), EventBridge rule too broad

The codebase also has notable strengths: thorough poison pill testing, good protocol compliance verification, comprehensive retry decorator coverage, and well-designed batch partial failure handling.

**Recommended priority:** Fix security issues first (items C1-C5), then data loss paths (C6-C13), then monitoring/infrastructure (C14-C23).

---

## CRITICAL — 23 Issues

### Security (Fix Immediately)

**C1. SQL Injection via f-string in map/services.py**
- **File:** `app/api/v1/map/services.py`
- **Issue:** `f" ORDER BY ... LIMIT {limit}"` — user-controlled `limit` parameter interpolated directly into SQL
- **Impact:** Arbitrary SQL execution against the production database
- **Fix:** Use parameterized queries: `text("... LIMIT :limit").bindparams(limit=limit)`

**C2. SSRF vulnerability in geolocate endpoint**
- **File:** `app/api/v1/map/router.py`
- **Issue:** User-controlled URL passed to geocoding service with no allowlist
- **Impact:** Attacker can probe internal network, access metadata endpoints (169.254.169.254)
- **Fix:** Validate URL against allowlisted geocoding provider domains

**C3. Script injection in CI via unsanitized diff output**
- **File:** `.github/workflows/cdk-test.yml`
- **Issue:** `${{ github.actor }}` and diff output injected into PR comment body without sanitization
- **Impact:** Malicious PR author can inject arbitrary markdown/scripts into PR comments
- **Fix:** Use `${{ github.event.pull_request.user.login }}` with sanitization, or write to file first

**C4. Overly broad IAM in bootstrap.sh**
- **File:** `infra/scripts/bootstrap.sh`
- **Issue:** `iam:*` permissions granted — full IAM access including creating admin users
- **Impact:** Privilege escalation from CDK deploy role to full AWS account admin
- **Fix:** Scope to `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PassRole` for specific resource ARNs

**C5. Internal error details leaked to API consumers**
- **File:** `app/api/v1/router.py`
- **Issue:** `detail=f"Error fetching location data: {str(e)}"` exposes SQLAlchemy internals
- **Impact:** Information disclosure — table names, query structure, driver versions
- **Fix:** Return generic error message; log details server-side with correlation ID

### Data Loss (Fix Before Production)

**C6. `_requeue_to_llm` has no error handling — orphans remaining jobs**
- **File:** `app/llm/queue/batch_result_processor.py:218-235`
- **Issue:** Single SQS requeue failure in batch failure recovery aborts entire Lambda — remaining jobs permanently lost
- **Impact:** Food bank data permanently lost with no recovery path
- **Fix:** Wrap each requeue in try/except, continue loop, track failures, raise after all attempts

**C7. Validator worker silently ignores missing `RECONCILER_QUEUE_URL`**
- **File:** `app/validator/fargate_worker.py:73-74`
- **Issue:** If env var not set, `next_queue_url=None` → validated records deleted from SQS but never forwarded
- **Impact:** Complete silent data loss — pipeline appears healthy but no records reach reconciler
- **Fix:** Fail fast if `RECONCILER_QUEUE_URL` is not set when running as validator

**C8. PipelineWorker exits code 0 after max errors — ECS won't restart**
- **File:** `app/pipeline/sqs_worker.py:314-337`
- **Issue:** Unlike `FargateWorker` which calls `sys.exit(1)`, `PipelineWorker.run()` returns normally
- **Impact:** Validator/reconciler/recorder die silently, queues stack up indefinitely, ECS sees healthy exit
- **Fix:** Add `sys.exit(1)` when exiting due to consecutive errors (matches `FargateWorker` pattern)

**C9. Batch result processor skips content store result storage**
- **File:** `app/llm/queue/batch_result_processor.py`
- **Issue:** On-demand path stores LLM results in content store before routing; batch path skips this step
- **Impact:** Pipeline parity violation — batch results cannot be audited or replayed
- **Fix:** Add `content_store.write_content()` call mirroring `processor.py` behavior

**C10. Non-atomic SQS-then-DynamoDB write ordering**
- **File:** `app/llm/queue/backend_sqs.py`
- **Issue:** SQS message sent first, DynamoDB tracking record written second — crash between creates phantom SQS message with no tracking
- **Impact:** Orphaned messages processed without job tracking, or duplicate processing on retry
- **Fix:** Write DynamoDB first (idempotent), then SQS; or use SQS message attributes to carry job ID

**C11. Batch error records silently dropped when `original_job` missing**
- **File:** `app/llm/queue/batch_result_processor.py:299-312`
- **Issue:** Error records from Bedrock with no matching `original_jobs` entry: increments counter, no log, no requeue
- **Impact:** Food bank data permanently lost without any diagnostic trail
- **Fix:** Add `logger.error()` with record_id and error details (matches successful record path at lines 318-325)

**C12. `_delete_messages` has no per-message error handling**
- **File:** `app/llm/queue/batcher.py:104-125`
- **Issue:** First delete failure aborts remaining deletes; on batch path, messages reappear causing duplicate processing
- **Impact:** Duplicate LLM processing of food bank data (wasted cost and potential data conflicts)
- **Fix:** Wrap each delete in try/except, continue loop, return failure count

**C13. Poison pill messages deleted without DLQ or audit trail**
- **Files:** `app/llm/queue/backend_sqs.py`, `app/pipeline/sqs_worker.py`
- **Issue:** Malformed messages are deleted with only a log warning — no DLQ routing, no persistent record
- **Impact:** Cannot diagnose recurring bad data sources; no way to replay/investigate deleted messages
- **Fix:** Route to DLQ instead of deleting, or write to S3 audit bucket before deleting

### Infrastructure (Fix Before Scale)

**C14. DLQ naming mismatch in MonitoringStack**
- **File:** `infra/stacks/monitoring_stack.py`
- **Issue:** Monitoring references DLQ names that don't match `queue_stack.py` naming pattern (`pantry-pirate-radio-{name}-dlq-{env}.fifo`)
- **Impact:** DLQ depth alarms will never fire — poison pills accumulate silently
- **Fix:** Align DLQ names with `queue_stack.py` pattern, or import references from QueueStack

**C15. `treat_missing_data` missing from ServicesStack scaling alarms**
- **File:** `infra/stacks/services_stack.py`
- **Issue:** Fix applied in `compute_stack.py` but NOT in `services_stack.py` — validator/reconciler/recorder scaling alarms treat missing data as "not breaching"
- **Impact:** Scale-from-zero broken for 3 services; tasks stay at 0 when queue has messages
- **Fix:** Add `treat_missing_data=cloudwatch.TreatMissingData.BREACHING` to all ServicesStack scaling alarms

**C16. Deploy workflow silently swallows ECS deployment failures**
- **File:** `.github/workflows/deploy-aws.yml`
- **Issue:** Multiple `|| true` and `|| echo` patterns on ECS service updates
- **Impact:** Deployment appears successful even when services fail to update — broken deployments go unnoticed
- **Fix:** Remove `|| true`; use proper error handling with rollback

**C17. EventBridge rule matches ALL Bedrock batch events**
- **File:** `infra/stacks/batch_stack.py`
- **Issue:** Rule not scoped to this account's/project's batch jobs
- **Impact:** Result processor Lambda triggered by other teams' batch jobs, causing errors and wasted compute
- **Fix:** Add job name prefix filter to EventBridge rule pattern

### Config & Code Quality

**C18. Config loader silently swallows ALL errors, falls back to hardcoded defaults**
- **Files:** `app/core/config.py:8-35`, `config/__init__.py:115-125`
- **Issue:** `except Exception: pass` on YAML loading — corrupted config, permission errors, YAML syntax errors all silently ignored
- **Impact:** System runs with hardcoded defaults while operators believe their config is active; potential config drift
- **Fix:** Catch only `ImportError`; let other exceptions propagate. At minimum, log a warning.

**C19. Module-level `Settings()` with no error handling in Lambda**
- **File:** `app/api/lambda_app.py:18`
- **Issue:** Secrets Manager failure during cold start produces opaque `Runtime.ImportModuleError`
- **Impact:** Operators debug code import issues when the real problem is AWS service dependency
- **Fix:** Wrap in try/except with explicit error message about Secrets Manager/IAM

**C20. `store_path` corrupts S3 URIs to invalid Path objects**
- **File:** `app/content_store/store.py`
- **Issue:** `Path("s3://bucket/key")` strips protocol and produces platform-dependent paths
- **Impact:** S3 URI lookups return wrong paths; content store operations fail silently
- **Fix:** Return `str` for S3 backend, `Path` for file backend (or always `str`)

**C21. `reverse_geocode` falsely rejects valid coordinates at lat=0 or lon=0**
- **File:** `app/core/geocoding/service.py`
- **Issue:** `if not latitude or not longitude` — Python falsiness rejects `0.0` as invalid
- **Impact:** Locations on the equator or prime meridian cannot be reverse-geocoded
- **Fix:** Use `if latitude is None or longitude is None`

**C22. Static `-retry` suffix for FIFO dedup ID silently deduplicates retries**
- **File:** `app/llm/queue/batch_result_processor.py`
- **Issue:** All retried messages get `{job_id}-retry` as dedup ID; SQS FIFO deduplicates for 5 minutes
- **Impact:** Multiple failed records retried within 5 minutes: only first one actually enqueued, rest silently dropped
- **Fix:** Use unique suffix per retry: `{job_id}-retry-{uuid4()}`

**C23. Timer thread race condition in visibility extension**
- **File:** `app/llm/queue/fargate_worker.py:105-162`
- **Issue:** Self-rescheduling `threading.Timer` chain has no synchronization; `cancel()` may target wrong timer
- **Impact:** Stale timer fires after job completion; mostly benign but indicates fragile design
- **Fix:** Replace with single background thread + `threading.Event` for shutdown

---

## IMPORTANT — 40 Issues

### Infrastructure

| # | Issue | File | Impact |
|---|-------|------|--------|
| I1 | No VPC endpoints for S3/DynamoDB/SQS/SecretsManager | CDK stacks | Data via NAT gateway; cost + security |
| I2 | No WAF on API Gateway HTTP API | lambda_api_stack.py | No rate limiting or DDoS protection |
| I3 | RDS Proxy SG `allow_all_outbound=True` | database_stack.py | Broader than needed |
| I4 | Hardcoded role name cross-reference between stacks | pipeline_stack.py ↔ services_stack.py | Fragile coupling; rename breaks deploy |
| I5 | Public S3 exports bucket with partial `BlockPublicAccess` | storage_stack.py | Unintended public access risk |
| I6 | CDK synth failure swallowed in CI | cdk-test.yml | Broken CDK passes CI |
| I7 | Bootstrap creates only 2 of 7 ECR repos | bootstrap.sh | Deploy fails for 5 services |
| I8 | `--require-approval broadening` blocks CI deploys | deploy-aws.yml | Manual approval needed in CI |

### Pipeline & Workers

| # | Issue | File | Impact |
|---|-------|------|--------|
| I9 | Error threshold only tracks poll failures | fargate_worker.py:256-310 | Worker with 100% job failure runs forever |
| I10 | PipelineWorker has no visibility extension | sqs_worker.py:179-252 | Long geocoding → message redelivery |
| I11 | Missing env var validation in batcher/processor | batcher.py, batch_result_processor.py | Empty string URLs → cryptic errors |
| I12 | Bedrock `generate` wraps all exceptions to `ValueError` | bedrock.py:435-439 | Retry logic can't distinguish error types |
| I13 | Malformed JSONL lines silently skipped | batch_result_processor.py:114-123 | Records lost without alert |
| I14 | S3 backend missing `_ensure_initialized()` on 8 methods | backend_s3.py | Operations on unverified resources |
| I15 | `initialize()` swallows transient errors before retry | backend_s3.py | Retry decorator never sees the error |
| I16 | `ContentHash` NewType declared but never used | backend.py | Dead code |
| I17 | Partial batch commit: Bedrock job submitted but metadata not written | batcher.py:339-347 | Orphaned batch job, results unprocessable |
| I18 | Empty `output_key_prefix` lists entire S3 bucket | batch_result_processor.py:63-80 | Cross-contamination of batch results |
| I19 | Missing DynamoDB item returns empty data silently | batch_result_processor.py:63-80 | All results discarded |
| I20 | Empty job IDs cause dict key collision | batcher.py:232-248 | Multiple records mapped to same key |

### API & Data Quality

| # | Issue | File | Impact |
|---|-------|------|--------|
| I21 | `KeyError` globally mapped to 404 | middleware/errors.py:38 | Internal bugs return "Not Found" |
| I22 | Malformed cursor silently restarts pagination | ptf/services.py:33-41 | Client loops on page 1 forever |
| I23 | No error handling on batch SQL queries | ptf/services.py:235-243 | One table lock → entire sync fails |
| I24 | Phone/ZIP as integers drops leading zeros | ptf/models.py | NJ (07102→7102), MA (01002→1002) |
| I25 | NYC exclusion hardcoded | ptf/services.py | Not configurable |
| I26 | DB password with special chars breaks URL | config.py | No `urllib.parse.quote_plus` |
| I27 | One bad record fails entire PTF batch transform | ptf/services.py:330-405 | 1 corrupt record → 1000 records lost |
| I28 | ETag WHERE clause inconsistent with sync query | ptf/services.py | Cache busted without data changing |

### Type Design

| # | Issue | File | Impact |
|---|-------|------|--------|
| I29 | `PtfSyncResponse.meta.returned != len(organizations)` not enforced | ptf/models.py | Metadata lies about payload |
| I30 | Lat/lng lack range validation on `PtfOrganization` | ptf/models.py | Invalid coordinates reach partner |
| I31 | `dict[str, Any]` anti-pattern in service layer | ptf/services.py | Type errors caught at serialization |
| I32 | Lambda/Docker split has no shared app factory | lambda_app.py vs main.py | CORS config duplicated |

### Geocoding Cache

| # | Issue | File | Impact |
|---|-------|------|--------|
| I33 | Cache get/set errors return None/silent discard | cache_backend.py, cache_dynamodb.py | Infra failure = cache miss |
| I34 | Triple fallback silently degrades DynamoDB→Redis→None | cache_backend.py:95-132 | Explicit DynamoDB config ignored |
| I35 | Secrets Manager errors wrapped in generic `ValueError` | config.py:228-235 | Transient vs permanent indistinguishable |
| I36 | DynamoDB status update failure swallowed | batch_result_processor.py:369-395 | Stale "submitted" status in monitoring |

### File Size / Constitution Violations

| # | Issue | File | Lines | Over By |
|---|-------|------|-------|---------|
| I37 | locations.py | app/api/v1/locations.py | 805 | 205 |
| I38 | map/router.py | app/api/v1/map/router.py | 782 | 182 |
| I39 | service.py | app/core/geocoding/service.py | 750 | 150 |
| I40 | services_stack.py | infra/stacks/services_stack.py | 600 | At limit |

### Logging Violations

| # | Issue | Files |
|---|-------|-------|
| I41 | `print()` used alongside structlog | All Fargate workers |
| I42 | `logging` module used instead of `structlog` | processor.py, cache_dynamodb.py, multiple API files |

---

## SUGGESTIONS — 10 Items

| # | Suggestion | File |
|---|-----------|------|
| S1 | CDK PR workflow creates new comments instead of updating existing | cdk-test.yml |
| S2 | `aws-marketplace:ViewSubscriptions` permission may be unnecessary | CDK IAM policies |
| S3 | DynamoDB full table scan for `index_get_statistics` | backend_s3.py |
| S4 | `Union[Path, str]` return type for `store_path` is a code smell | backend.py |
| S5 | FIFO dedup uses UUID (no real deduplication benefit) | backend_sqs.py |
| S6 | Shared conftest fixtures for AWS mocks (duplicated across 3 test files) | test_llm/, test_pipeline/ |
| S7 | Reconciler limited to 0-1 instances but no app-level enforcement | reconciler/fargate_worker.py |
| S8 | Split `test_queue_backend_sqs.py` (1149 lines) | tests/test_llm/ |
| S9 | Split `test_backend_s3.py` (875 lines) | tests/test_content_store/ |
| S10 | Split `test_services_stack.py` (727 lines) | infra/tests/ |

---

## STRENGTHS — 12 Items

| # | Strength | Details |
|---|----------|---------|
| + 1 | **Poison pill handling thoroughly tested** | Tested in queue backend, pipeline worker, and batcher — prevents processing paralysis |
| + 2 | **S3/DynamoDB error propagation well-tested** | Dedicated test classes for AccessDenied, throttling, missing resources |
| + 3 | **AWS retry decorator comprehensive** | Retryable vs non-retryable errors, backoff timing, max delay cap, metadata preservation |
| + 4 | **Protocol compliance verified for all abstractions** | `ContentStoreBackend`, `QueueBackend`, `GeocodingCacheBackend` all have protocol tests |
| + 5 | **Batch partial failure coverage excellent** | Full success, complete failure, per-record partial failure, empty queue no-op |
| + 6 | **CDK tests comprehensive** | 17 test files covering all stacks with template assertions |
| + 7 | **Double failure scenarios tested** | Worker survives processing failure + status update failure simultaneously |
| + 8 | **Signal handling and graceful shutdown tested** | SIGTERM, graceful shutdown, error-based exit distinction |
| + 9 | **Keyset pagination with PostGIS clustering** | Well-designed for large datasets; single source of truth for filter logic |
| +10 | **`send_to_sqs` has robust retry logic** | Exponential backoff with AWS-specific retryable error detection |
| +11 | **Shared pipeline config pattern** | `config/defaults.yml` as single source of truth is architecturally sound |
| +12 | **SQS message envelope traceability** | `job_id`, `data`, `source`, `enqueued_at` provide good debugging context |

---

## Test Coverage Gaps

| Priority | Gap | Criticality |
|----------|-----|-------------|
| 1 | No end-to-end AWS pipeline message format compatibility test | 9/10 |
| 2 | `_ensure_initialized()` guard never tested for negative path | 8/10 |
| 3 | DynamoDB pagination untested in `index_get_statistics()` | 8/10 |
| 4 | Bedrock JSONL record format compatibility not end-to-end tested | 7/10 |
| 5 | `forward-then-delete` ordering not verified in PipelineWorker | 6/10 |
| 6 | S3 read failure during batch result processing not tested | 6/10 |
| 7 | Lambda secret resolution from Secrets Manager not tested | 6/10 |

---

## Remediation Priority

### Tier 1 — Fix Before Merge (Security + Data Loss)
1. C1: SQL injection in map/services.py
2. C2: SSRF in geolocate endpoint
3. C3: Script injection in cdk-test.yml
4. C5: Internal error details leaked
5. C6: `_requeue_to_llm` error handling
6. C7: Validator `RECONCILER_QUEUE_URL` validation
7. C8: PipelineWorker exit code
8. C10: SQS/DynamoDB write ordering
9. C14: DLQ naming mismatch
10. C15: `treat_missing_data` in ServicesStack
11. C16: ECS deploy `|| true` removal

### Tier 2 — Fix Before Production Traffic
12. C4: Bootstrap IAM scoping
13. C9: Batch result processor content store parity
14. C11: Batch error record logging
15. C12: `_delete_messages` per-message handling
16. C17: EventBridge rule scoping
17. C18: Config loader error handling
18. C19: Lambda Settings() error handling
19. C20: store_path S3 URI handling
20. C21: Coordinate falsiness fix
21. C22: FIFO dedup suffix uniqueness
22. I11: Env var validation in batcher/processor

### Tier 3 — Fix During Stabilization
23. I1: VPC endpoints
24. I2: WAF on API Gateway
25. I9: Job failure rate tracking
26. I10: PipelineWorker visibility extension
27. I12: Bedrock exception types
28. I21: KeyError→404 mapping
29. I24: Phone/ZIP as strings
30. I33-I34: Cache error handling improvements
31. I37-I40: File size constitution compliance

### Tier 4 — Backlog
32. All remaining Important items
33. All Suggestions
34. Test coverage gaps
35. Logging standardization

---

## Existing PR Feedback Cross-Reference

PR #396 has 3 existing Claude reviews (near-identical duplicates) covering:
- Path type semantics for S3 backend ✓ (covered as C20)
- DynamoDB memory for large operations ✓ (covered as S3)
- SQS FIFO validation gaps ✓ (covered as S5, C22)

CDK diff CI is failing with `ModuleNotFoundError: No module named 'stacks.secrets_stack'` — this is a separate CI configuration issue that should be fixed as part of C6/I6.

---

*Generated by 17 specialized review agents across 8 functional areas. Total analysis: ~600K tokens of agent reasoning.*
