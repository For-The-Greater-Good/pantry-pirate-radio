# Data Pipeline Audit — 2026-02-27

## Executive Summary

A deep code-level audit of the data pipeline — LLM layer, validator, reconciler, and
all handoff points between them — revealed **11 confirmed bugs** that are actively
degrading output data quality. The single most damaging finding: **the reconciler
throws away all work the validator does** because it re-parses the original LLM text
instead of using the enriched data that the validator spent time geocoding, correcting,
and scoring.

These bugs fall into three severity tiers:

| Tier | Count | Summary |
|------|-------|---------|
| **CRITICAL** | 4 | Direct data loss — geocoded coordinates discarded, records orphaned, locations silently dropped |
| **HIGH** | 4 | Data corruption — schedule information collapsed, LLM output discarded, job collisions, log noise |
| **MEDIUM** | 3 | Code quality — dead code with wrong defaults, name-based mapping collisions, crash on time formats |

### Where Bugs Occur in the Pipeline

```
Scrapers
   |
   v
Content Store -----> LLM Queue -----> [BUG #7: Job ID collisions]
                        |
                        v
                   LLM Processing ---> [BUG #6: JSON parse replaces content]
                        |               [BUG #8: Debug prints in production]
                        |
            +-----------+-----------+
            |                       |
            v                       v
     Validator Queue         Reconciler Queue
            |                (validator disabled)
            |                       |
            v                       |
      Validation &                  |
      Enrichment ---------> [BUG #3: Enrichment failures drop data quality]
            |                [BUG #2: Hardcoded rejection threshold]
            |                [BUG #9: Dead code with wrong defaults]
            |                       |
            v                       |
    enriched_job_result             |
    (job_result.data)               |
            |                       |
            +--------> Reconciler <-+
                            |
                  [BUG #1:  Re-parses result.text, ignores job_result.data]
                  [BUG #4:  Phone None -> orphaned language records]
                  [BUG #5:  Schedule dedup ignores byday]
                  [BUG #10: Location name collisions]
                  [BUG #11: Time format crash]
                            |
                            v
                       PostgreSQL
```

---

## TIER 1 — CRITICAL: Direct Data Loss

---

### BUG #1: Reconciler Ignores All Validator Enrichment

**Severity:** CRITICAL
**Impact:** Geocoded coordinates, corrected states, enriched postal codes — all thrown away
**Files:**
- `app/reconciler/job_processor.py:303` (re-parses original text)
- `app/reconciler/job_processor.py:652-655` (tries to read enrichment from wrong source)
- `app/validator/job_processor.py:104-105` (stores enrichment in `job_result.data`)

#### The Problem

The validator enriches data (geocodes missing coordinates, corrects states, fills postal
codes) and stores the enriched result in `job_result.data`:

```python
# validator/job_processor.py:103-105
enriched_job_result = job_result.model_copy()
enriched_job_result.data = result.get("data", {})
```

But the reconciler **re-parses the original LLM text** as its primary data source:

```python
# reconciler/job_processor.py:302-303
json_text = self._extract_json_from_markdown(job_result.result.text)
```

The reconciler does read `job_result.data` as `validation_data` (line 287-289), but only
uses it for **score lookups** — it never reads the enriched coordinates from it:

```python
# reconciler/job_processor.py:285-289
validation_data = None
if hasattr(job_result, "data") and job_result.data:
    validation_data = job_result.data
```

Then at lines 652-655, the reconciler tries to get validation fields from the location
objects it parsed from `result.text`. But those objects came from the **original LLM
output** and don't have any validation fields:

```python
# reconciler/job_processor.py:652-655
loc_confidence_score = location.get("confidence_score")    # Always None
loc_validation_status = location.get("validation_status")  # Always None
loc_validation_notes = location.get("validation_notes")    # Always None
loc_geocoding_source = location.get("geocoding_source")    # Always None
```

These are always `None`, so it falls through to the name-based matching fallback at line
665. That fallback only extracts scores, **not the enriched coordinates**.

The killer consequence: if the LLM didn't provide coordinates (common), the validator
successfully geocodes them, but the reconciler reads from the original text which has
`latitude: null, longitude: null`, and **skips the location entirely**:

```python
# reconciler/job_processor.py:774-780
else:
    location_name = location.get("name", "Unknown")
    logger.warning(
        f"Skipping location '{location_name}' - no coordinates after validation"
    )
    continue  # <-- Location silently dropped
```

#### Suggested Fix

Change the reconciler to use `job_result.data` as the primary data source when it
exists, falling back to `result.text` only when `data` is absent (validator disabled):

```python
# reconciler/job_processor.py — replace lines 294-303
if hasattr(job_result, "data") and job_result.data:
    raw_data = job_result.data  # Use enriched data from validator
    validation_data = raw_data  # Same source for validation lookups
    logger.info("Using enriched data from validator")
else:
    # Validator disabled — parse from original LLM text
    if not job_result.result:
        raise ValueError("Job result has no result")
    json_text = self._extract_json_from_markdown(job_result.result.text)
    raw_data = json.loads(json_text)
    validation_data = None
```

---

### BUG #2: Hardcoded Rejection Reason Threshold

**Severity:** CRITICAL
**Impact:** Rejected locations have no rejection reason logged — impossible to debug
**File:** `app/validator/job_processor.py:684`

#### The Problem

The `_get_rejection_reason` method uses a hardcoded `>= 10` threshold:

```python
# validator/job_processor.py:684-685
def _get_rejection_reason(self, confidence_score, validation_results):
    if confidence_score >= 10:
        return None  # <-- Hardcoded 10, ignores settings
```

But the actual rejection threshold is configurable via `VALIDATION_REJECTION_THRESHOLD`
and defaults to 10 in settings, used by the scorer:

```python
# validator/scoring.py:21-24
self.rejection_threshold = self.config.get(
    "rejection_threshold",
    getattr(settings, "VALIDATION_REJECTION_THRESHOLD", 10),
)
```

If someone sets `VALIDATION_REJECTION_THRESHOLD=30`, the scorer marks locations with
scores 10-29 as `"rejected"`, but `_get_rejection_reason` returns `None` for those same
locations because it only checks `>= 10`.

Result: rejected locations have no rejection reason in their `validation_notes`, making
it impossible to understand why data was dropped.

#### Suggested Fix

```python
# validator/job_processor.py:684 — replace hardcoded 10
from app.core.config import settings

rejection_threshold = getattr(settings, "VALIDATION_REJECTION_THRESHOLD", 10)
if confidence_score >= rejection_threshold:
    return None
```

---

### BUG #3: Enrichment Exception Silently Degrades Data Quality

**Severity:** CRITICAL
**Impact:** Transient geocoding failures cause permanent data loss
**File:** `app/validator/job_processor.py:378-383`

#### The Problem

When geocoding enrichment throws any exception (rate limit, timeout, service unavailable),
the validator catches it and continues with the original unenriched data:

```python
# validator/job_processor.py:378-383
except Exception as e:
    self.logger.warning(f"Enrichment failed: {e}", exc_info=True)
    self._enrichment_error = str(e)
    # Return original data if enrichment fails
    return data  # <-- Unenriched data continues to scoring
```

The unenriched data then flows into `validate_data()` where locations without coordinates
immediately score 0:

```python
# validator/scoring.py:44-48
if not validation_results.get("has_coordinates", False):
    return 0  # <-- Score 0 = rejected
```

A location that **could have been geocoded** (it has a valid address) is rejected because
of a transient geocoding failure. This is a permanent data loss — the location won't be
retried.

#### Suggested Fix

When enrichment fails, flag locations that needed enrichment as `needs_review` instead of
letting them score 0:

```python
except Exception as e:
    self.logger.error(f"Enrichment failed: {e}", exc_info=True)
    self._enrichment_error = str(e)
    # Mark locations that needed enrichment so they aren't auto-rejected
    for location in data.get("location", []):
        if location.get("latitude") is None or location.get("longitude") is None:
            location["enrichment_failed"] = True
    return data
```

Then in the scorer, check for `enrichment_failed` and score as `needs_review` (e.g., 30)
instead of 0.

---

### BUG #4: Phone Creation Returns None, Language Records Orphaned

**Severity:** CRITICAL
**Impact:** Orphaned language records with null foreign keys in the database
**Files:**
- `app/reconciler/service_creator.py:434-471` (`create_phone` returns None)
- `app/reconciler/job_processor.py:615-630` (caller doesn't check for None)

#### The Problem

`create_phone()` returns `None` for invalid phone numbers:

```python
# service_creator.py:466-471
def create_phone(self, number, phone_type, ...):
    if not number or number.strip() == "":
        return None  # <-- Returns None instead of UUID

    if number.upper() in ["UNKNOWN", "INVALID", "N/A", "NA", "NONE"]:
        return None  # <-- Returns None

    if not any(char.isdigit() for char in number):
        return None  # <-- Returns None
```

But the calling code at `job_processor.py` doesn't check the return value before creating
language records:

```python
# job_processor.py:615-630
phone_id = service_creator.create_phone(
    number=phone.get("number", ""),  # Could be empty string
    phone_type=phone.get("type", ""),
    organization_id=org_id,
    metadata=job_result.job.metadata,
    transaction=self.db,
)
# Add phone languages — NO NULL CHECK ON phone_id
if "languages" in phone:
    for language in phone["languages"]:
        service_creator.create_language(
            name=language.get("name", ""),
            code=language.get("code", ""),
            phone_id=phone_id,  # <-- phone_id is None!
            metadata=job_result.job.metadata,
        )
```

This creates language records in the database with `phone_id = NULL`, which are orphaned
rows that can never be linked to anything.

#### Suggested Fix

```python
phone_id = service_creator.create_phone(...)
if phone_id and "languages" in phone:  # <-- Guard with null check
    for language in phone["languages"]:
        service_creator.create_language(...)
```

---

## TIER 2 — HIGH: Data Corruption

---

### BUG #5: Schedule Deduplication Ignores `byday` Field

**Severity:** HIGH
**Impact:** Different-day schedules collapsed — "Mon 9-5" and "Tue 9-5" become one record
**File:** `app/reconciler/job_processor.py:1300-1314`

#### The Problem

The in-memory schedule deduplication before database insertion compares only four fields:

```python
# job_processor.py:1302-1311
for existing in schedules_to_create:
    if (
        existing["freq"]
        == loc_schedule["freq"]
        and existing["wkst"]
        == loc_schedule["wkst"]
        and existing["opens_at"]
        == loc_schedule["opens_at"]
        and existing["closes_at"]
        == loc_schedule["closes_at"]
    ):
        exists = True
        break
```

The `byday` field is **not compared**. So a schedule for Monday 9-5 and a schedule for
Tuesday 9-5 are treated as duplicates, and only one is created.

Note: the database-level `update_or_create_schedule` in `service_creator.py:875-886`
**does** compare `byday` and other fields. But by then it's too late — the in-memory
dedup already discarded the "duplicate".

#### Suggested Fix

Add `byday` to the comparison:

```python
if (
    existing["freq"] == loc_schedule["freq"]
    and existing["wkst"] == loc_schedule["wkst"]
    and existing["opens_at"] == loc_schedule["opens_at"]
    and existing["closes_at"] == loc_schedule["closes_at"]
    and existing.get("byday") == loc_schedule.get("byday")  # <-- Add this
):
```

---

### BUG #6: LLM JSON Parse Failure Replaces Content With Error String

**Severity:** HIGH
**Impact:** Actual LLM output discarded; retries run against a fake error string
**File:** `app/llm/providers/openai.py:398-427`

#### The Problem

When the LLM returns content that fails JSON parsing, the actual content is **replaced**
with the string literal `"Invalid JSON response"`:

```python
# openai.py:398-427
def _process_json_content(self, content, format):
    content = _extract_json_from_markdown(content)
    parsed = None
    if format and content:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse JSON response. Error: %s. Content length: %d. "
                "First 500 chars: %s",
                str(e), len(content),
                content[:500] if content else "(empty)",
            )
            if "cannot" in content.lower() or "refuse" in content.lower():
                return content, None
            return "Invalid JSON response", None  # <-- Original content GONE
    return content.strip(), parsed
```

This fake error string then flows to `processor.py` where it triggers a retry:

```python
# processor.py:124-126
if llm_result.text == "Invalid JSON response":
    retry_count += 1
    last_error = "Received 'Invalid JSON response' from LLM"
```

The original LLM output — which might have had a minor JSON issue fixable by `demjson3`
in the reconciler — is completely gone. The reconciler never gets a chance to try lenient
parsing.

#### Suggested Fix

Return the original content alongside a parse-failure flag instead of replacing it:

```python
except json.JSONDecodeError as e:
    logger.warning("JSON parse failed: %s", e)
    # Return original content — downstream can try lenient parsing
    return content, None
```

Then update the processor to check `parsed is None` instead of string comparison.

---

### BUG #7: Job ID Collision Risk With Timestamp

**Severity:** HIGH
**Impact:** Job metadata overwritten in RQ when two scrapers create jobs in the same second
**File:** `app/scraper/utils.py:237`

#### The Problem

Job IDs are generated from `datetime.now().timestamp()`:

```python
# scraper/utils.py:236-237
job = LLMJob(
    id=str(datetime.now().timestamp()),  # e.g., "1740691200.123456"
    ...
)
```

This is a float-to-string conversion with ~microsecond precision. Two scrapers running
simultaneously via `scouting-party` mode can produce the same timestamp string, causing
RQ job ID collisions. When a collision occurs, the second job's metadata overwrites the
first.

#### Suggested Fix

Use UUID4:

```python
import uuid
job = LLMJob(
    id=str(uuid.uuid4()),
    ...
)
```

---

### BUG #8: Debug Print Statements Left in Production Code

**Severity:** HIGH
**Impact:** Job metadata (including content hashes) dumped to stdout; log noise
**File:** `app/llm/queue/processor.py:87-88`

#### The Problem

Two debug statements were left in the production code:

```python
# processor.py:87-88
print(f"DEBUG: Job {job.id} metadata: {job.metadata}")
logger.warning(f"DEBUG: Job {job.id} metadata: {job.metadata}")
```

These run for **every single LLM job processed**, dumping the full metadata dict
(scraper_id, content_hash, etc.) to both stdout and the WARNING log level.

#### Suggested Fix

Delete both lines.

---

## TIER 3 — MEDIUM: Code Quality

---

### BUG #9: `_extract_validation_metadata` Is Dead Code With Wrong Defaults

**Severity:** MEDIUM
**Impact:** No functional impact currently, but misleading and would break if activated
**File:** `app/validator/job_processor.py:699-722`

#### The Problem

The method is called at line 477 but its returned metadata is never applied to actual
database records. It also has incorrect defaults:

```python
# validator/job_processor.py:699-722
def _extract_validation_metadata(self, data):
    metadata = {
        "confidence_score": 1.0,  # <-- Float, should be int 0-100
        "status": "validated" if not self._validation_errors else "failed",
                   # ^^^ "validated" doesn't match enum: verified/needs_review/rejected
        "notes": self._validation_errors.copy(),
        "field_count": len(data),
        "has_organization": "organization" in data,
        "has_locations": "locations" in data,  # <-- "locations" not "location"
        "has_services": "services" in data,    # <-- "services" not "service"
    }
    return metadata
```

Problems:
- `confidence_score: 1.0` — a float, while the rest of the system uses int 0-100
- `status: "validated"` — not a valid validation status (`verified`/`needs_review`/`rejected`)
- Key names `"has_locations"` and `"has_services"` check plural forms, but the HSDS data
  uses singular `"location"` and `"service"`
- Called at line 477 → `set_validation_fields(metadata)` → logs it, but never writes to DB

#### Suggested Fix

Either remove the dead code entirely, or fix the types and field names if it will be used.

---

### BUG #10: Location ID Mapping Uses Name Only — Duplicates Overwrite

**Severity:** MEDIUM
**Impact:** Service-at-location links for duplicate-named locations point to wrong location
**File:** `app/reconciler/job_processor.py` (location_ids dict)

#### The Problem

The reconciler maps location names to database IDs for service linking:

```python
# job_processor.py (location processing loop)
location_ids[location["name"]] = location_id
```

If a single job contains two locations with the same name (e.g., "Food Pantry" in
different cities), the second one overwrites the first in the map. When services are
later linked to locations:

```python
# job_processor.py:1236-1250
if loc_identifier in location_ids:
    # Uses location_ids[name] — may point to wrong location
```

All services for duplicate-named locations end up linked to the last location with that
name, not the correct one.

#### Suggested Fix

Use a composite key combining name and coordinates, or use an index-based approach:

```python
key = f"{location['name']}|{location.get('latitude')}|{location.get('longitude')}"
location_ids[key] = location_id
```

---

### BUG #11: Schedule Time Parsing Crashes on Non-HH:MM Formats

**Severity:** MEDIUM
**Impact:** One malformed schedule time crashes the entire reconciliation job
**File:** `app/reconciler/service_creator.py:728-733`

#### The Problem

Time parsing uses a single format with no error handling:

```python
# service_creator.py:728-733
opens_at_time = (
    datetime.strptime(opens_at, "%H:%M").time() if opens_at else None
)
closes_at_time = (
    datetime.strptime(closes_at, "%H:%M").time() if closes_at else None
)
```

If the LLM returns times in any other format — `"9:00 AM"`, `"09:00:00"`, `"9am"` —
`strptime` raises `ValueError` which propagates up and crashes the entire job,
losing **all locations** in that batch, not just the one with the bad schedule.

This same pattern appears at line 836-840 in `update_or_create_schedule`.

#### Suggested Fix

Try multiple time formats with fallback:

```python
def parse_time(time_str):
    if not time_str:
        return None
    for fmt in ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"]:
        try:
            return datetime.strptime(time_str.strip(), fmt).time()
        except ValueError:
            continue
    logger.warning(f"Could not parse time: {time_str}")
    return None
```

---

## Full Reference: Data Flow Through Pipeline

For context, here's how data flows through the system and where each bug intercepts:

### 1. Scraper Output
Scrapers produce raw HTML/JSON content as a string.

### 2. Content Store (Dedup)
`ScraperUtils.queue_for_processing()` → `ContentStore.store_content()`
- SHA-256 hash for deduplication
- Content stored to filesystem, indexed in SQLite
- **[BUG #7]** Job ID created from timestamp, risk of collision

### 3. LLM Processing
`process_llm_job()` calls provider to generate structured HSDS output.
- **[BUG #8]** Debug prints dump metadata to stdout
- **[BUG #6]** JSON parse failure replaces actual content with error string
- Routes to validator queue (if enabled) or reconciler queue (if disabled)

### 4. Validator (Optional)
`process_validation_job()` → `ValidationProcessor.process_job_result()`
- Parses LLM output → enriches with geocoding → scores confidence → rejects bad data
- **[BUG #3]** Enrichment exception discards all enrichment work
- **[BUG #2]** Rejection reason uses hardcoded threshold, not settings
- **[BUG #9]** Dead code extracts metadata with wrong types
- Stores enriched data in `enriched_job_result.data`, enqueues to reconciler

### 5. Reconciler
`process_job_result()` → creates database records
- **[BUG #1]** Re-parses `result.text` (original LLM output), ignoring enriched `data`
- **[BUG #4]** Phone creation returns None → language records orphaned
- **[BUG #5]** Schedule dedup ignores `byday` → different days collapsed
- **[BUG #10]** Location name mapping collisions → wrong service links
- **[BUG #11]** Time format crash → entire job lost

### 6. PostgreSQL → API → HAARRRvest
Records stored in PostgreSQL, served via read-only API, published to HAARRRvest.

---

## Recommended Fix Priority

| Priority | Bug | Effort | Impact |
|----------|-----|--------|--------|
| 1 | #1 — Reconciler ignores enrichment | Medium | Fixes the biggest data loss source |
| 2 | #4 — Phone/language orphaning | Small | One null check |
| 3 | #8 — Debug prints | Trivial | Delete 2 lines |
| 4 | #2 — Hardcoded threshold | Small | One-line fix |
| 5 | #5 — Schedule dedup | Small | Add one field to comparison |
| 6 | #3 — Enrichment failure | Medium | Design decision needed |
| 7 | #7 — Job ID collision | Small | Switch to UUID4 |
| 8 | #6 — JSON parse handling | Medium | Changes in provider + processor |
| 9 | #11 — Time parsing | Small | Add format fallbacks |
| 10 | #10 — Location name mapping | Small | Composite key |
| 11 | #9 — Dead code | Trivial | Remove or fix |

---

## Verification Plan

After fixes are applied:

1. **Run full test suite:** `./bouy test`
2. **End-to-end scraper test:** `./bouy scraper-test <name>` then `./bouy scraper <name>`
3. **Verify geocoded coordinates reach database:** Query locations that had no LLM-provided
   coordinates and confirm they now have geocoded coords
4. **Verify rejection reasons:** Check that rejected locations have reasons in
   `validation_notes`
5. **Check for orphans:** `SELECT * FROM language WHERE phone_id IS NULL`
6. **Replay existing data:** `./bouy replay --use-default-output-dir` and compare results
7. **Schedule coverage:** Verify locations with multi-day schedules have all days recorded
