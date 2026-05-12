# Feeding America ZIP → Food Bank Crosswalk

**Date:** 2026-05-12
**Status:** Draft — pending implementation

## Motivation

We are exploring a contract opportunity with Feeding America (FA). A clean, downloadable crosswalk from US ZIP code → FA member food bank is the simplest tangible artifact we can produce that demonstrates value. FA publishes a live lookup API (`GetOrganizationsByZip`) but does not (publicly) publish a downloadable crosswalk. Materializing the crosswalk into our pipeline:

- Makes it joinable to our scraped `location` data (gap analysis later).
- Gives FA a queryable, exportable artifact (Datasette + SQLite via HAARRRvest).
- Frees consumers (Plentiful, Beacon, future tooling) from hitting FA's live API at user-request scale.

This spec covers the **minimal viable crosswalk only** — `(zip, fa_org_id, fa_org_name)`. County-level food-insecurity data, coverage-gap dashboards, and per-foodbank drilldowns are explicitly out of scope and tracked separately if pursued.

## Data source

`https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=NNNNN`

Returns an `Organization[]` array. Each element includes `OrganizationID` (canonical FA org ID) and `FullName`. **One ZIP can return multiple organizations** — e.g., 10001 returns both Food Bank For New York City (10) and City Harvest (297). The crosswalk must preserve this many-to-many relationship.

No authentication. No documented rate limit. We will be polite (1 req/sec).

## Architecture

```
Census ZCTA list (~33k ZIPs, static file)
        ↓
build_zip_crosswalk.py (one-shot, resumable)
        ↓ (1 req/sec to FA API)
GetOrganizationsByZip → upsert rows
        ↓
Postgres: feeding_america_zip_coverage
        ↓
Datasette (port 8001, prod mode)  →  CSV/JSON export per query
        ↓
HAARRRvest publisher (existing)   →  SQLite export → S3 public URL
```

Nothing new in the runtime pipeline. The script is invoked manually (or via `./bouy fa-crosswalk`) and writes to the main pipeline Postgres database. Datasette and the HAARRRvest publisher pick up the new table automatically since both reflect the full schema.

## Schema

```sql
CREATE TABLE feeding_america_zip_coverage (
    zip          TEXT        NOT NULL,  -- 5-digit ZCTA
    fa_org_id    INTEGER     NOT NULL,  -- Feeding America OrganizationID
    fa_org_name  TEXT        NOT NULL,  -- snapshot of FullName at fetch time
    last_seen_at TIMESTAMPTZ NOT NULL,  -- timestamp of most recent confirmation by FA API
    PRIMARY KEY (zip, fa_org_id)
);

CREATE INDEX idx_fa_zip_coverage_org ON feeding_america_zip_coverage(fa_org_id);
```

- **Composite PK** `(zip, fa_org_id)` — natural key, supports many-to-many.
- **`fa_org_name`** is a denormalized snapshot. We do not maintain a separate `fa_organization` dimension table in this spec (out of scope; can be added if/when option B is pursued).
- **`last_seen_at`** lets a future refresh detect coverage drift. On rerun: rows present in the new fetch get their `last_seen_at` updated; rows missing from the new fetch are deleted (i.e., FA's API is treated as authoritative on each pass).

Added via a new Alembic migration in `app/database/migrations/`.

## Populator script

**Location:** `scripts/feeding-america/build_zip_crosswalk.py`
**Invocation:** `./bouy fa-crosswalk` (new bouy subcommand) or `./bouy exec app python scripts/feeding-america/build_zip_crosswalk.py`

### ZIP universe

A static text file checked into `scripts/feeding-america/data/zcta_us.txt`, one ZIP per line, sourced from the US Census Bureau ZCTA (ZIP Code Tabulation Area) gazetteer. Approximately 33,000 entries. Bundling it eliminates a runtime dependency on Census's servers and makes the input set reproducible.

**ZCTA vs ZIP note:** ZCTAs are Census's polygon approximation of ZIP delivery areas. Some USPS ZIPs (PO-Box-only, military APO/FPO) have no ZCTA equivalent and will be absent from the crosswalk; conversely, ZCTAs map cleanly to the residential ZIPs that constituents enter into a "find a food bank near me" form, which is the use case the crosswalk serves. We accept this tradeoff explicitly rather than try to reconcile USPS's proprietary ZIP universe.

### Flow

1. Read ZIPs from `zcta_us.txt`.
2. Load resume state from `scripts/feeding-america/data/.crosswalk_state.json` (gitignored). If present, skip ZIPs already completed in this run.
3. For each remaining ZIP, throttled to 1 req/sec:
   a. `GET GetOrganizationsByZip?zip=NNNNN` with a 30s timeout.
   b. Retry with exponential backoff (3 attempts: 2s, 4s, 8s) on network errors or 5xx responses.
   c. Parse `Organization[]`. For each org, upsert `(zip, fa_org_id, fa_org_name, last_seen_at=now())`.
   d. If `Organization[]` is empty, no rows are inserted for this ZIP. That is a valid signal (coverage gap).
   e. On malformed response or final retry failure, append the ZIP to `scripts/feeding-america/data/.crosswalk_failed_zips.txt` and continue.
   f. Update resume state every 100 ZIPs (so a crash loses at most ~100s of work).
4. After all ZIPs processed: delete any rows in the table whose `last_seen_at` is older than the run's start timestamp (purges stale coverage from previous runs).
5. Exit nonzero if >5% of ZIPs failed; otherwise exit zero and log a summary (rows upserted, rows pruned, ZIPs with no coverage, ZIPs failed).

### Rate limit and runtime

1 request/second × 33,000 ZIPs ≈ 9.2 hours for a cold full run. Acceptable for a one-shot. Resume state makes a crashed run cheap to restart.

We do not parallelize. Politeness toward FA's API matters more than wall time, since this is a one-off.

### Logging

Structured `structlog` events:
- `fa_crosswalk_zip_fetched` (zip, org_count, elapsed_ms)
- `fa_crosswalk_zip_failed` (zip, attempt, error)
- `fa_crosswalk_run_completed` (total_zips, rows_upserted, rows_pruned, zips_no_coverage, zips_failed, duration_s)

## Bouy integration

Add `./bouy fa-crosswalk` as a subcommand that runs the populator script in the `app` container. Standard bouy plumbing — no new compose service. Document in `CLAUDE.md` under the existing Feeding America section.

## Surfaces

### Datasette

Already enabled in production mode. The new table appears automatically. ZIP-based query example:
```
SELECT * FROM feeding_america_zip_coverage WHERE zip = '10001';
```
Datasette provides CSV/JSON export per query out of the box.

### HAARRRvest

The existing publisher exports the full Postgres schema to SQLite and pushes to S3. No code change required. Public SQLite URL (already used by the daily publisher) will include the crosswalk after the next publisher run following a successful crosswalk build.

### No REST API endpoint

Out of scope. Adding `GET /v1/fa-coverage/{zip}` later is trivial if requested by FA.

## Refresh cadence

**One-time bootstrap only** in this spec. No cron, no scheduler. If FA wants quarterly refreshes, add a Step Functions schedule (or rerun manually) — out of scope here.

## Error handling

| Failure mode | Handling |
|---|---|
| Network / 5xx | Retry 3× with exponential backoff, then record to failed-ZIPs file |
| Empty `Organization[]` | Valid — no rows inserted; counted as "no coverage" |
| Malformed JSON | Log error, skip ZIP, record to failed-ZIPs file |
| >5% ZIPs failed | Exit nonzero so operator notices |
| Process killed | Resume from `.crosswalk_state.json` on next run |

No silent data loss. FA's API is treated as authoritative — if a (zip, org) pair disappears from a fresh run, the row is pruned at the end.

## Testing

`tests/test_scripts/test_build_zip_crosswalk.py`:

- **Unit:** parse the multi-org case (captured 10001 response), single-org case, empty case, malformed case. Each asserts the correct rows are returned by the parsing function.
- **Unit:** retry logic — first two attempts 5xx, third succeeds, asserts one set of rows produced.
- **Unit:** retry exhaustion — all three attempts fail, asserts ZIP recorded to failed file.
- **Integration:** run the script end-to-end against a 3-ZIP fixture file (`["10001", "00000", "94110"]`) with `responses` or `httpx_mock` stubbing the FA API. Asserts: correct rows in DB, correct `last_seen_at` semantics on rerun (rows updated, stale rows pruned), state file written and consumed correctly.
- **Migration:** the Alembic migration is tested via the existing migration test harness.

Coverage target: matches the project's ratchet. No new exemptions.

## Out of scope (explicit non-goals)

- County-level food-insecurity (Map the Meal Gap) data — handled by a future spec if option B is pursued.
- `fa_organization` dimension table (full FA org metadata) — out of scope.
- Coverage-gap dashboard, map UI, per-foodbank drilldown — option C, future.
- Joining to our `location` table via `fa_org_id` — separate spec, not required for the FA deliverable.
- REST API endpoint for ZIP lookup — trivial to add later.
- Scheduled refresh — one-time bootstrap suffices.
- Territorial ZIPs (PR, VI, GU) — included only if present in the Census ZCTA gazetteer; not specifically curated.

## Deliverables

1. Alembic migration creating `feeding_america_zip_coverage`.
2. `scripts/feeding-america/build_zip_crosswalk.py` populator.
3. `scripts/feeding-america/data/zcta_us.txt` (Census ZCTA list).
4. `./bouy fa-crosswalk` subcommand wired up.
5. Unit + integration tests.
6. `CLAUDE.md` documentation update under the Feeding America section.
7. One successful production run, producing a populated table visible in Datasette and the next HAARRRvest SQLite export.
