# Feeding America ZIP → Food Bank Crosswalk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `(zip, fa_org_id, fa_org_name)` Postgres table populated from Feeding America's `GetOrganizationsByZip` API, surfaced via Datasette and the HAARRRvest SQLite export, as a deliverable artifact for a potential FA contract.

**Architecture:** A new Postgres table created by a Python migration script. A one-shot, resumable populator script iterates ~33k US ZIPs (Census ZCTA list) against FA's public API at 1 req/sec, upserting rows. After the run, rows not refreshed are pruned. Datasette + HAARRRvest publisher pick up the table automatically — no runtime plumbing changes.

**Tech Stack:** Python 3, SQLAlchemy 2.x (sync), `httpx`, `structlog`, Postgres 16, `pytest` + `httpx_mock`, bouy.

**Spec:** `docs/superpowers/specs/2026-05-12-fa-zip-crosswalk-design.md`

---

## File Structure

**Files to create:**
- `app/database/migrations/add_feeding_america_zip_coverage.py` — migration creating the table + index
- `scripts/feeding-america/build_zip_crosswalk.py` — populator script (single file, clearly separated functions for testability)
- `scripts/feeding-america/data/zcta_us.txt` — Census ZCTA gazetteer list (~33k lines, one ZIP per line)
- `scripts/feeding-america/data/.gitignore` — ignore runtime state files
- `tests/test_scripts/test_build_zip_crosswalk.py` — unit + integration tests
- `tests/test_scripts/fixtures/fa_api_10001.json` — captured FA API response (multi-org)
- `tests/test_scripts/fixtures/fa_api_single_org.json` — single-org case
- `tests/test_scripts/fixtures/fa_api_empty.json` — empty `Organization[]` case

**Files to modify:**
- `bouy` — add `fa-crosswalk)` subcommand case
- `CLAUDE.md` — document the new command under the Feeding America section

**Why this shape:** The populator stays as one file (~250-300 LOC) with clearly named functions (`parse_response`, `fetch_zip`, `upsert_rows`, `prune_stale_rows`, `load_state`, `save_state`, `main`). Each is independently unit-testable. Matches the existing convention in `scripts/feeding-america/` (other utilities there are single-file scripts).

---

## Task 1: Add migration for `feeding_america_zip_coverage` table

**Files:**
- Create: `app/database/migrations/add_feeding_america_zip_coverage.py`

- [ ] **Step 1: Write the migration script**

```python
#!/usr/bin/env python3
"""Migration: create feeding_america_zip_coverage table.

Run inside the app container:
    ./bouy exec app python app/database/migrations/add_feeding_america_zip_coverage.py
"""

import logging

from sqlalchemy import create_engine, text

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DDL = [
    """
    CREATE TABLE IF NOT EXISTS feeding_america_zip_coverage (
        zip          TEXT        NOT NULL,
        fa_org_id    INTEGER     NOT NULL,
        fa_org_name  TEXT        NOT NULL,
        last_seen_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (zip, fa_org_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fa_zip_coverage_org ON feeding_america_zip_coverage(fa_org_id)",
]


def main() -> None:
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        for stmt in DDL:
            logger.info("executing: %s", stmt.split("\n")[1].strip() if "\n" in stmt else stmt)
            conn.execute(text(stmt))
    logger.info("migration complete")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the dev database**

```bash
./bouy up --with-init
./bouy exec app python app/database/migrations/add_feeding_america_zip_coverage.py
```

Expected output: two `executing:` lines, then `migration complete`.

- [ ] **Step 3: Verify the table exists**

```bash
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "\d feeding_america_zip_coverage"
```

Expected: shows columns `zip text NOT NULL`, `fa_org_id integer NOT NULL`, `fa_org_name text NOT NULL`, `last_seen_at timestamp with time zone NOT NULL`, with PK `(zip, fa_org_id)` and index `idx_fa_zip_coverage_org`.

- [ ] **Step 4: Verify rerun is idempotent**

```bash
./bouy exec app python app/database/migrations/add_feeding_america_zip_coverage.py
```

Expected: same output, no errors (the `IF NOT EXISTS` guards both statements).

- [ ] **Step 5: Commit**

```bash
git add app/database/migrations/add_feeding_america_zip_coverage.py
git commit -m "feat: add feeding_america_zip_coverage table migration"
```

---

## Task 2: Source and commit the Census ZCTA list

**Files:**
- Create: `scripts/feeding-america/data/zcta_us.txt`
- Create: `scripts/feeding-america/data/.gitignore`

- [ ] **Step 1: Download the 2024 Census ZCTA national gazetteer**

```bash
mkdir -p /tmp/zcta
cd /tmp/zcta
curl -sSLO "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip"
unzip -o 2024_Gaz_zcta_national.zip
ls
```

Expected: an extracted `2024_Gaz_zcta_national.txt` file (tab-separated, header row + ~33k data rows; first column `GEOID` is the 5-digit ZCTA).

- [ ] **Step 2: Extract the ZIP column into the project**

```bash
cd /Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio
mkdir -p scripts/feeding-america/data
tail -n +2 /tmp/zcta/2024_Gaz_zcta_national.txt | awk -F'\t' '{print $1}' | sort -u > scripts/feeding-america/data/zcta_us.txt
wc -l scripts/feeding-america/data/zcta_us.txt
```

Expected: `33,791 scripts/feeding-america/data/zcta_us.txt` (the count is approximate; anything in the 33k-34k range is correct).

- [ ] **Step 3: Spot-check the file**

```bash
head -3 scripts/feeding-america/data/zcta_us.txt
grep -c "^10001$" scripts/feeding-america/data/zcta_us.txt
```

Expected: three 5-digit ZIPs (sorted, starting at `00601` for PR or similar), and `1` for the 10001 check (Manhattan must be present).

- [ ] **Step 4: Add a .gitignore for runtime state**

Create `scripts/feeding-america/data/.gitignore`:

```
.crosswalk_state.json
.crosswalk_failed_zips.txt
```

- [ ] **Step 5: Commit**

```bash
git add scripts/feeding-america/data/zcta_us.txt scripts/feeding-america/data/.gitignore
git commit -m "feat: add Census ZCTA list for FA crosswalk input"
```

---

## Task 3: Test fixtures for FA API responses

**Files:**
- Create: `tests/test_scripts/fixtures/fa_api_10001.json`
- Create: `tests/test_scripts/fixtures/fa_api_single_org.json`
- Create: `tests/test_scripts/fixtures/fa_api_empty.json`

- [ ] **Step 1: Capture the live 10001 response**

```bash
mkdir -p tests/test_scripts/fixtures
curl -sS "https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=10001" \
  | python3 -m json.tool > tests/test_scripts/fixtures/fa_api_10001.json
```

Expected: pretty-printed JSON. Open the file and verify it contains an `Organization` array with at least two entries (Food Bank For New York City, OrganizationID 10; City Harvest, OrganizationID 297).

- [ ] **Step 2: Create the single-org fixture**

Capture a single-org ZIP (e.g., a rural ZIP). Let's use `99501` (Anchorage, AK).

```bash
curl -sS "https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=99501" \
  | python3 -m json.tool > tests/test_scripts/fixtures/fa_api_single_org.json
```

Expected: the file's `Organization` array has exactly one entry. If the live API returns more than one for 99501, pick any other ZIP that returns exactly one (try `59401` for Great Falls, MT) and rename accordingly. Whichever ZIP you use, write its number as a comment-style first-line key — except JSON doesn't allow comments, so just remember/document which ZIP it represents in the test file.

- [ ] **Step 3: Create the empty fixture**

```bash
cat > tests/test_scripts/fixtures/fa_api_empty.json <<'EOF'
{
  "Organization": []
}
EOF
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_scripts/fixtures/
git commit -m "test: add FA API response fixtures for crosswalk tests"
```

---

## Task 4: TDD — `parse_response` (extract rows from API JSON)

**Files:**
- Create: `tests/test_scripts/test_build_zip_crosswalk.py`
- Create: `scripts/feeding-america/build_zip_crosswalk.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scripts/test_build_zip_crosswalk.py`:

```python
"""Tests for scripts/feeding-america/build_zip_crosswalk.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make the script importable as a module.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "feeding-america"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_zip_crosswalk as bzc  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestParseResponse:
    def test_parses_multi_org_response(self) -> None:
        rows = bzc.parse_response("10001", _load_fixture("fa_api_10001.json"))
        # Food Bank For NYC (10) + City Harvest (297) are both expected.
        org_ids = sorted(r.fa_org_id for r in rows)
        assert 10 in org_ids
        assert 297 in org_ids
        # All rows should be tagged with the queried ZIP.
        assert {r.zip for r in rows} == {"10001"}
        # Names are non-empty.
        assert all(r.fa_org_name for r in rows)

    def test_parses_single_org_response(self) -> None:
        rows = bzc.parse_response("99501", _load_fixture("fa_api_single_org.json"))
        assert len(rows) >= 1
        assert all(r.zip == "99501" for r in rows)

    def test_parses_empty_response(self) -> None:
        rows = bzc.parse_response("00000", _load_fixture("fa_api_empty.json"))
        assert rows == []

    def test_malformed_response_raises(self) -> None:
        with pytest.raises(ValueError):
            bzc.parse_response("10001", {"not_organization": []})

    def test_skips_org_with_missing_id(self) -> None:
        payload = {"Organization": [{"FullName": "No ID Org"}]}
        rows = bzc.parse_response("10001", payload)
        assert rows == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py -v
```

Expected: `ModuleNotFoundError: No module named 'build_zip_crosswalk'` (because the script doesn't exist yet).

- [ ] **Step 3: Write the minimal populator skeleton with `parse_response`**

Create `scripts/feeding-america/build_zip_crosswalk.py`:

```python
#!/usr/bin/env python3
"""Build the Feeding America ZIP -> food bank crosswalk table.

Iterates every US ZIP (from data/zcta_us.txt) against FA's
GetOrganizationsByZip API and upserts rows into
feeding_america_zip_coverage. Resumable, rate-limited, idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoverageRow:
    zip: str
    fa_org_id: int
    fa_org_name: str


def parse_response(zip_code: str, payload: dict[str, Any]) -> list[CoverageRow]:
    """Convert a GetOrganizationsByZip JSON payload into CoverageRows.

    Raises ValueError if the payload is missing the expected 'Organization' key.
    Silently drops orgs with missing/invalid OrganizationID.
    """
    if "Organization" not in payload:
        raise ValueError(f"missing 'Organization' key in FA response for zip {zip_code}")
    rows: list[CoverageRow] = []
    for org in payload["Organization"]:
        org_id = org.get("OrganizationID")
        name = org.get("FullName") or ""
        if not isinstance(org_id, int):
            continue
        rows.append(CoverageRow(zip=zip_code, fa_org_id=org_id, fa_org_name=name))
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestParseResponse -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/feeding-america/build_zip_crosswalk.py tests/test_scripts/test_build_zip_crosswalk.py
git commit -m "feat: parse FA GetOrganizationsByZip responses into CoverageRows"
```

---

## Task 5: TDD — `fetch_zip` (HTTP client with retries)

**Files:**
- Modify: `tests/test_scripts/test_build_zip_crosswalk.py`
- Modify: `scripts/feeding-america/build_zip_crosswalk.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_scripts/test_build_zip_crosswalk.py`:

```python
import httpx


class TestFetchZip:
    def test_returns_rows_on_200(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=10001",
            json=_load_fixture("fa_api_10001.json"),
        )
        client = httpx.Client(timeout=30.0)
        rows = bzc.fetch_zip(client, "10001", max_attempts=3, backoff_base=0.0)
        client.close()
        assert any(r.fa_org_id == 10 for r in rows)

    def test_retries_on_5xx_then_succeeds(self, httpx_mock) -> None:
        url = "https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=10001"
        httpx_mock.add_response(url=url, status_code=503)
        httpx_mock.add_response(url=url, status_code=502)
        httpx_mock.add_response(url=url, json=_load_fixture("fa_api_10001.json"))
        client = httpx.Client(timeout=30.0)
        rows = bzc.fetch_zip(client, "10001", max_attempts=3, backoff_base=0.0)
        client.close()
        assert len(rows) >= 2

    def test_raises_after_all_retries_fail(self, httpx_mock) -> None:
        url = "https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=10001"
        for _ in range(3):
            httpx_mock.add_response(url=url, status_code=503)
        client = httpx.Client(timeout=30.0)
        with pytest.raises(bzc.FetchError):
            bzc.fetch_zip(client, "10001", max_attempts=3, backoff_base=0.0)
        client.close()

    def test_empty_response_returns_empty_list(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=00000",
            json=_load_fixture("fa_api_empty.json"),
        )
        client = httpx.Client(timeout=30.0)
        rows = bzc.fetch_zip(client, "00000", max_attempts=3, backoff_base=0.0)
        client.close()
        assert rows == []
```

Note: `pytest-httpx` provides the `httpx_mock` fixture. Verify it's in `pyproject.toml` under dev dependencies; if missing, add it as a Step 1.5 before running the tests:

```bash
./bouy exec app poetry add --group dev pytest-httpx
```

Only run that if the import / fixture isn't available.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestFetchZip -v
```

Expected: failures with `AttributeError: module 'build_zip_crosswalk' has no attribute 'fetch_zip'`.

- [ ] **Step 3: Implement `fetch_zip` and `FetchError`**

Add to `scripts/feeding-america/build_zip_crosswalk.py`:

```python
import time

import httpx

FA_API_URL = "https://www.feedingamerica.org/ws-api/GetOrganizationsByZip"


class FetchError(RuntimeError):
    """Raised when fetching a ZIP exhausts all retries."""


def fetch_zip(
    client: httpx.Client,
    zip_code: str,
    *,
    max_attempts: int = 3,
    backoff_base: float = 2.0,
) -> list[CoverageRow]:
    """Fetch and parse a single ZIP, retrying on network/5xx errors.

    Backoff schedule: backoff_base * 2**attempt seconds between attempts
    (i.e. 2s, 4s, 8s for base=2.0). Pass backoff_base=0.0 in tests.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = client.get(FA_API_URL, params={"zip": zip_code})
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            payload = response.json()
            return parse_response(zip_code, payload)
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            last_exc = exc
            if attempt + 1 < max_attempts:
                time.sleep(backoff_base * (2**attempt))
    raise FetchError(f"failed to fetch zip {zip_code} after {max_attempts} attempts: {last_exc}")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestFetchZip -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/feeding-america/build_zip_crosswalk.py tests/test_scripts/test_build_zip_crosswalk.py
git commit -m "feat: fetch_zip with retries against FA API"
```

---

## Task 6: TDD — DB upsert + prune

**Files:**
- Modify: `tests/test_scripts/test_build_zip_crosswalk.py`
- Modify: `scripts/feeding-america/build_zip_crosswalk.py`

- [ ] **Step 1: Add failing DB tests**

Append to `tests/test_scripts/test_build_zip_crosswalk.py`:

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from app.core.config import settings


@pytest.fixture
def db_engine():
    """Connect to the test database and ensure a clean table state."""
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS feeding_america_zip_coverage (
                    zip          TEXT        NOT NULL,
                    fa_org_id    INTEGER     NOT NULL,
                    fa_org_name  TEXT        NOT NULL,
                    last_seen_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (zip, fa_org_id)
                )
                """
            )
        )
        conn.execute(text("DELETE FROM feeding_america_zip_coverage"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM feeding_america_zip_coverage"))


class TestUpsertRows:
    def test_inserts_new_rows(self, db_engine) -> None:
        now = datetime.now(timezone.utc)
        rows = [
            bzc.CoverageRow(zip="10001", fa_org_id=10, fa_org_name="Food Bank For NYC"),
            bzc.CoverageRow(zip="10001", fa_org_id=297, fa_org_name="City Harvest"),
        ]
        bzc.upsert_rows(db_engine, rows, now)
        with db_engine.connect() as conn:
            result = conn.execute(
                text("SELECT fa_org_id, fa_org_name FROM feeding_america_zip_coverage WHERE zip = '10001' ORDER BY fa_org_id")
            ).all()
        assert result == [(10, "Food Bank For NYC"), (297, "City Harvest")]

    def test_updates_last_seen_at_on_existing(self, db_engine) -> None:
        old = datetime.now(timezone.utc) - timedelta(days=30)
        new = datetime.now(timezone.utc)
        row = bzc.CoverageRow(zip="10001", fa_org_id=10, fa_org_name="Food Bank For NYC")
        bzc.upsert_rows(db_engine, [row], old)
        bzc.upsert_rows(db_engine, [row], new)
        with db_engine.connect() as conn:
            (last_seen,) = conn.execute(
                text("SELECT last_seen_at FROM feeding_america_zip_coverage WHERE zip='10001' AND fa_org_id=10")
            ).one()
        # last_seen should be ~new, not ~old.
        assert (last_seen - new).total_seconds() < 1

    def test_updates_org_name_on_existing(self, db_engine) -> None:
        now = datetime.now(timezone.utc)
        bzc.upsert_rows(db_engine, [bzc.CoverageRow("10001", 10, "Old Name")], now)
        bzc.upsert_rows(db_engine, [bzc.CoverageRow("10001", 10, "New Name")], now)
        with db_engine.connect() as conn:
            (name,) = conn.execute(
                text("SELECT fa_org_name FROM feeding_america_zip_coverage WHERE zip='10001' AND fa_org_id=10")
            ).one()
        assert name == "New Name"


class TestPruneStaleRows:
    def test_removes_rows_older_than_cutoff(self, db_engine) -> None:
        old = datetime.now(timezone.utc) - timedelta(days=30)
        new = datetime.now(timezone.utc)
        bzc.upsert_rows(db_engine, [bzc.CoverageRow("10001", 10, "Stale")], old)
        bzc.upsert_rows(db_engine, [bzc.CoverageRow("10001", 297, "Fresh")], new)
        cutoff = new - timedelta(minutes=1)
        pruned = bzc.prune_stale_rows(db_engine, cutoff)
        assert pruned == 1
        with db_engine.connect() as conn:
            remaining = conn.execute(
                text("SELECT fa_org_id FROM feeding_america_zip_coverage")
            ).all()
        assert remaining == [(297,)]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestUpsertRows tests/test_scripts/test_build_zip_crosswalk.py::TestPruneStaleRows -v
```

Expected: failures with `AttributeError: module 'build_zip_crosswalk' has no attribute 'upsert_rows'`.

- [ ] **Step 3: Implement `upsert_rows` and `prune_stale_rows`**

Add to `scripts/feeding-america/build_zip_crosswalk.py`:

```python
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine


def upsert_rows(engine: Engine, rows: list[CoverageRow], seen_at: datetime) -> None:
    """Insert or update rows, stamping last_seen_at."""
    if not rows:
        return
    stmt = text(
        """
        INSERT INTO feeding_america_zip_coverage (zip, fa_org_id, fa_org_name, last_seen_at)
        VALUES (:zip, :fa_org_id, :fa_org_name, :last_seen_at)
        ON CONFLICT (zip, fa_org_id) DO UPDATE
            SET fa_org_name  = EXCLUDED.fa_org_name,
                last_seen_at = EXCLUDED.last_seen_at
        """
    )
    params = [
        {
            "zip": r.zip,
            "fa_org_id": r.fa_org_id,
            "fa_org_name": r.fa_org_name,
            "last_seen_at": seen_at,
        }
        for r in rows
    ]
    with engine.begin() as conn:
        conn.execute(stmt, params)


def prune_stale_rows(engine: Engine, cutoff: datetime) -> int:
    """Delete rows with last_seen_at < cutoff. Returns the number deleted."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM feeding_america_zip_coverage WHERE last_seen_at < :cutoff"),
            {"cutoff": cutoff},
        )
        return result.rowcount or 0
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestUpsertRows tests/test_scripts/test_build_zip_crosswalk.py::TestPruneStaleRows -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/feeding-america/build_zip_crosswalk.py tests/test_scripts/test_build_zip_crosswalk.py
git commit -m "feat: upsert_rows and prune_stale_rows for FA crosswalk"
```

---

## Task 7: TDD — Resume state file

**Files:**
- Modify: `tests/test_scripts/test_build_zip_crosswalk.py`
- Modify: `scripts/feeding-america/build_zip_crosswalk.py`

- [ ] **Step 1: Add failing state-file tests**

Append to `tests/test_scripts/test_build_zip_crosswalk.py`:

```python
class TestState:
    def test_load_returns_empty_when_missing(self, tmp_path) -> None:
        state_path = tmp_path / "state.json"
        assert bzc.load_state(state_path) == set()

    def test_round_trip(self, tmp_path) -> None:
        state_path = tmp_path / "state.json"
        bzc.save_state(state_path, {"10001", "94110", "60601"})
        assert bzc.load_state(state_path) == {"10001", "94110", "60601"}

    def test_load_handles_corrupt_file(self, tmp_path) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text("not json {")
        # Corrupt state must not crash the run — treat as empty.
        assert bzc.load_state(state_path) == set()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestState -v
```

Expected: failures with `AttributeError: module 'build_zip_crosswalk' has no attribute 'load_state'`.

- [ ] **Step 3: Implement state file functions**

Add to `scripts/feeding-america/build_zip_crosswalk.py`:

```python
import json
from pathlib import Path


def load_state(state_path: Path) -> set[str]:
    """Load the set of already-completed ZIPs. Returns empty set if missing/corrupt."""
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text())
        if isinstance(data, list):
            return {str(z) for z in data}
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def save_state(state_path: Path, completed: set[str]) -> None:
    """Persist the set of completed ZIPs to a JSON file."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(sorted(completed)))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestState -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/feeding-america/build_zip_crosswalk.py tests/test_scripts/test_build_zip_crosswalk.py
git commit -m "feat: resume state file for FA crosswalk runs"
```

---

## Task 8: TDD — End-to-end `main()` orchestration

**Files:**
- Modify: `tests/test_scripts/test_build_zip_crosswalk.py`
- Modify: `scripts/feeding-america/build_zip_crosswalk.py`

- [ ] **Step 1: Add failing integration test**

Append to `tests/test_scripts/test_build_zip_crosswalk.py`:

```python
class TestRunCrosswalk:
    def test_end_to_end_three_zips(self, db_engine, tmp_path, httpx_mock) -> None:
        # ZIP universe file
        zcta = tmp_path / "zcta.txt"
        zcta.write_text("10001\n00000\n99501\n")

        # State and failed-zips files
        state = tmp_path / "state.json"
        failed = tmp_path / "failed.txt"

        # Mock FA API: 10001 multi-org, 00000 empty, 99501 single
        httpx_mock.add_response(
            url="https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=10001",
            json=_load_fixture("fa_api_10001.json"),
        )
        httpx_mock.add_response(
            url="https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=00000",
            json=_load_fixture("fa_api_empty.json"),
        )
        httpx_mock.add_response(
            url="https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=99501",
            json=_load_fixture("fa_api_single_org.json"),
        )

        result = bzc.run_crosswalk(
            engine=db_engine,
            zcta_path=zcta,
            state_path=state,
            failed_path=failed,
            rate_limit_seconds=0.0,
            checkpoint_every=1,
        )

        # Summary numbers
        assert result.zips_processed == 3
        assert result.zips_with_no_coverage == 1
        assert result.rows_upserted >= 3  # 2 from 10001 + >=1 from 99501
        assert result.zips_failed == 0

        # DB state
        with db_engine.connect() as conn:
            distinct_zips = conn.execute(
                text("SELECT DISTINCT zip FROM feeding_america_zip_coverage ORDER BY zip")
            ).all()
        assert distinct_zips == [("10001",), ("99501",)]

    def test_resume_skips_completed_zips(self, db_engine, tmp_path, httpx_mock) -> None:
        zcta = tmp_path / "zcta.txt"
        zcta.write_text("10001\n99501\n")
        state = tmp_path / "state.json"
        state.write_text(json.dumps(["10001"]))
        failed = tmp_path / "failed.txt"

        # Only 99501 should be requested — no mock for 10001.
        httpx_mock.add_response(
            url="https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=99501",
            json=_load_fixture("fa_api_single_org.json"),
        )

        result = bzc.run_crosswalk(
            engine=db_engine,
            zcta_path=zcta,
            state_path=state,
            failed_path=failed,
            rate_limit_seconds=0.0,
            checkpoint_every=1,
        )

        assert result.zips_processed == 1
        assert result.zips_skipped_resumed == 1

    def test_prunes_stale_rows(self, db_engine, tmp_path, httpx_mock) -> None:
        # Seed a stale row from a "previous run".
        stale_time = datetime.now(timezone.utc) - timedelta(days=30)
        bzc.upsert_rows(db_engine, [bzc.CoverageRow("99999", 9999, "Stale Foodbank")], stale_time)

        zcta = tmp_path / "zcta.txt"
        zcta.write_text("99501\n")
        state = tmp_path / "state.json"
        failed = tmp_path / "failed.txt"

        httpx_mock.add_response(
            url="https://www.feedingamerica.org/ws-api/GetOrganizationsByZip?zip=99501",
            json=_load_fixture("fa_api_single_org.json"),
        )

        result = bzc.run_crosswalk(
            engine=db_engine,
            zcta_path=zcta,
            state_path=state,
            failed_path=failed,
            rate_limit_seconds=0.0,
            checkpoint_every=1,
        )

        assert result.rows_pruned == 1
        with db_engine.connect() as conn:
            stale_rows = conn.execute(
                text("SELECT COUNT(*) FROM feeding_america_zip_coverage WHERE zip='99999'")
            ).scalar()
        assert stale_rows == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestRunCrosswalk -v
```

Expected: failures with `AttributeError: module 'build_zip_crosswalk' has no attribute 'run_crosswalk'`.

- [ ] **Step 3: Implement `run_crosswalk` and `RunResult`**

Add to `scripts/feeding-america/build_zip_crosswalk.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy.engine import Engine

log = structlog.get_logger(__name__)


@dataclass
class RunResult:
    zips_processed: int = 0
    zips_skipped_resumed: int = 0
    zips_with_no_coverage: int = 0
    zips_failed: int = 0
    rows_upserted: int = 0
    rows_pruned: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def run_crosswalk(
    *,
    engine: Engine,
    zcta_path: Path,
    state_path: Path,
    failed_path: Path,
    rate_limit_seconds: float = 1.0,
    checkpoint_every: int = 100,
    max_attempts: int = 3,
    backoff_base: float = 2.0,
) -> RunResult:
    """Iterate the ZCTA list, fetch each ZIP from FA, upsert into the DB.

    Resumable via state_path. Failed ZIPs are appended to failed_path.
    On completion, rows older than the run start are pruned.
    """
    result = RunResult()
    completed = load_state(state_path)
    zips = [z.strip() for z in zcta_path.read_text().splitlines() if z.strip()]
    log.info("fa_crosswalk_run_started", total_zips=len(zips), resumed=len(completed))

    failed_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30.0) as client:
        for zip_code in zips:
            if zip_code in completed:
                result.zips_skipped_resumed += 1
                continue

            try:
                rows = fetch_zip(
                    client,
                    zip_code,
                    max_attempts=max_attempts,
                    backoff_base=backoff_base,
                )
            except FetchError as exc:
                result.zips_failed += 1
                with failed_path.open("a") as f:
                    f.write(f"{zip_code}\n")
                log.warning("fa_crosswalk_zip_failed", zip=zip_code, error=str(exc))
                completed.add(zip_code)  # do not re-attempt on resume; failures are recorded
                if len(completed) % checkpoint_every == 0:
                    save_state(state_path, completed)
                if rate_limit_seconds > 0:
                    time.sleep(rate_limit_seconds)
                continue

            if rows:
                upsert_rows(engine, rows, datetime.now(timezone.utc))
                result.rows_upserted += len(rows)
            else:
                result.zips_with_no_coverage += 1

            result.zips_processed += 1
            completed.add(zip_code)
            log.info(
                "fa_crosswalk_zip_fetched",
                zip=zip_code,
                org_count=len(rows),
            )

            if len(completed) % checkpoint_every == 0:
                save_state(state_path, completed)
            if rate_limit_seconds > 0:
                time.sleep(rate_limit_seconds)

    save_state(state_path, completed)
    result.rows_pruned = prune_stale_rows(engine, result.started_at)
    log.info(
        "fa_crosswalk_run_completed",
        zips_processed=result.zips_processed,
        zips_with_no_coverage=result.zips_with_no_coverage,
        zips_failed=result.zips_failed,
        rows_upserted=result.rows_upserted,
        rows_pruned=result.rows_pruned,
    )
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py::TestRunCrosswalk -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full file to verify nothing regressed**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py -v
```

Expected: all tests pass (16-ish).

- [ ] **Step 6: Commit**

```bash
git add scripts/feeding-america/build_zip_crosswalk.py tests/test_scripts/test_build_zip_crosswalk.py
git commit -m "feat: end-to-end run_crosswalk orchestration with resume + prune"
```

---

## Task 9: CLI entrypoint and `__main__` block

**Files:**
- Modify: `scripts/feeding-america/build_zip_crosswalk.py`

- [ ] **Step 1: Add `cli_main()` and `__main__` block**

Append to `scripts/feeding-america/build_zip_crosswalk.py`:

```python
import argparse
import sys

from sqlalchemy import create_engine

from app.core.config import settings

DEFAULT_ZCTA_PATH = Path(__file__).parent / "data" / "zcta_us.txt"
DEFAULT_STATE_PATH = Path(__file__).parent / "data" / ".crosswalk_state.json"
DEFAULT_FAILED_PATH = Path(__file__).parent / "data" / ".crosswalk_failed_zips.txt"
FAILURE_RATE_THRESHOLD = 0.05


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Feeding America ZIP crosswalk.")
    parser.add_argument("--zcta", type=Path, default=DEFAULT_ZCTA_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--failed", type=Path, default=DEFAULT_FAILED_PATH)
    parser.add_argument("--rate-limit", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--checkpoint-every", type=int, default=100)
    args = parser.parse_args(argv)

    engine = create_engine(settings.DATABASE_URL)
    result = run_crosswalk(
        engine=engine,
        zcta_path=args.zcta,
        state_path=args.state,
        failed_path=args.failed,
        rate_limit_seconds=args.rate_limit,
        checkpoint_every=args.checkpoint_every,
    )

    total = result.zips_processed + result.zips_failed
    if total > 0 and (result.zips_failed / total) > FAILURE_RATE_THRESHOLD:
        log.error(
            "fa_crosswalk_failure_rate_exceeded",
            failed=result.zips_failed,
            total=total,
            threshold=FAILURE_RATE_THRESHOLD,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
```

- [ ] **Step 2: Smoke-test against a tiny ZCTA file**

```bash
./bouy exec app bash -c "echo '10001' > /tmp/tiny_zcta.txt && python scripts/feeding-america/build_zip_crosswalk.py --zcta /tmp/tiny_zcta.txt --state /tmp/tiny_state.json --failed /tmp/tiny_failed.txt --rate-limit 0 --checkpoint-every 1"
```

Expected: structured log lines, exit code 0, and the database contains rows for ZIP 10001:

```bash
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT * FROM feeding_america_zip_coverage WHERE zip='10001';"
```

Expected: two rows (Food Bank For NYC and City Harvest).

- [ ] **Step 3: Clean up the smoke-test rows**

```bash
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "DELETE FROM feeding_america_zip_coverage WHERE zip='10001';"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/feeding-america/build_zip_crosswalk.py
git commit -m "feat: CLI entrypoint for build_zip_crosswalk"
```

---

## Task 10: Add `./bouy fa-crosswalk` subcommand

**Files:**
- Modify: `bouy`

- [ ] **Step 1: Read the existing dispatch block to pick an insertion point**

Read `bouy` around lines 1880-1900 to find a good place near the other Feeding America-flavored subcommands. Insert the new case immediately before `content-store)` (around line 1884).

- [ ] **Step 2: Add the case**

Edit `bouy`, inserting the following before the `content-store)` case (approximately line 1884):

```bash
    fa-crosswalk)
        shift
        # Ensure database is running.
        if ! $COMPOSE_CMD $COMPOSE_FILES ps db 2>/dev/null | grep -q "Up"; then
            output info "Database service is not running. Starting it..."
            $COMPOSE_CMD $COMPOSE_FILES up -d db
            wait_for_database || exit 1
        fi

        # Build command with any pass-through args.
        cmd="python scripts/feeding-america/build_zip_crosswalk.py"
        for arg in "$@"; do
            case $arg in
                --dev|--prod|--test|--with-init)
                    ;;
                *)
                    cmd="$cmd $arg"
                    ;;
            esac
        done

        output info "Building Feeding America ZIP crosswalk (this takes ~9 hours at default rate limit)..."
        $COMPOSE_CMD $COMPOSE_FILES exec -T app bash -c "$cmd"
        ;;
```

- [ ] **Step 3: Verify the subcommand is recognized**

```bash
./bouy fa-crosswalk --help
```

Expected: the argparse help text from `build_zip_crosswalk.py` (usage line + flag descriptions).

- [ ] **Step 4: Commit**

```bash
git add bouy
git commit -m "feat: add ./bouy fa-crosswalk subcommand"
```

---

## Task 11: Documentation update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the Feeding America section in CLAUDE.md**

Open `CLAUDE.md` and find the "Scraper Development Workflow" section that already documents `/scrape` and the `scripts/feeding-america/` helpers (around the "Manual Scripts (for advanced use):" block).

- [ ] **Step 2: Add a new subsection above "Manual Scripts (for advanced use):"**

Insert:

```markdown
**ZIP → Food Bank Crosswalk:**

A separate one-shot script builds a Postgres table mapping every US ZIP to the
Feeding America member food banks that serve it (many-to-many; e.g., ZIP 10001
has both Food Bank For NYC and City Harvest). Used as a deliverable artifact
for FA contract conversations and surfaced via Datasette + HAARRRvest SQLite
export.

```bash
./bouy fa-crosswalk                    # full run (~9 hours at 1 req/sec)
./bouy fa-crosswalk --rate-limit 0.5   # faster run for testing
```

The script is resumable — state is persisted to
`scripts/feeding-america/data/.crosswalk_state.json` every 100 ZIPs. Failed
ZIPs are recorded to `.crosswalk_failed_zips.txt` in the same directory.
Rows not seen in the latest run are pruned at the end. Schema:
`feeding_america_zip_coverage (zip, fa_org_id, fa_org_name, last_seen_at)`.
```

- [ ] **Step 3: Add `fa-crosswalk` to the Quick Command Reference**

In the top "Quick Command Reference" block, add under the "Scraper Commands (Local)" section (or its own block):

```bash
# Feeding America Crosswalk
./bouy fa-crosswalk          # Build ZIP -> food bank crosswalk (~9 hours)
./bouy fa-crosswalk --help   # Show options
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document FA ZIP crosswalk command"
```

---

## Task 12: Full quality gates

**Files:** none (verification)

- [ ] **Step 1: Run the focused tests**

```bash
./bouy exec app pytest tests/test_scripts/test_build_zip_crosswalk.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run black**

```bash
./bouy test --black scripts/feeding-america/build_zip_crosswalk.py tests/test_scripts/test_build_zip_crosswalk.py app/database/migrations/add_feeding_america_zip_coverage.py
```

Expected: no diffs (or auto-formatted files; if formatting changes, recommit).

- [ ] **Step 3: Run ruff**

```bash
./bouy test --ruff
```

Expected: no lint errors in the new files.

- [ ] **Step 4: Run mypy on the new code**

```bash
./bouy test --mypy scripts/feeding-america/build_zip_crosswalk.py
```

Expected: no type errors.

- [ ] **Step 5: Run bandit**

```bash
./bouy test --bandit
```

Expected: no new high/medium findings in the new files.

- [ ] **Step 6: Run the full CI gate**

```bash
./bouy test
```

Expected: all checks pass.

- [ ] **Step 7: If any of the above auto-fixed files, commit the fixes**

```bash
git status
git diff
# If there are changes:
git add -A
git commit -m "style: apply black/ruff fixes to FA crosswalk code"
```

---

## Task 13: Operational run (handoff)

This task is not implementation — it is the bootstrap run the operator performs after merge.

- [ ] **Step 1: Confirm the migration has been applied to the target database**

```bash
./bouy exec app python app/database/migrations/add_feeding_america_zip_coverage.py
```

- [ ] **Step 2: Kick off the full run**

```bash
./bouy fa-crosswalk
```

Expected: ~9 hours of structured `fa_crosswalk_zip_fetched` log lines, then `fa_crosswalk_run_completed` with summary counts.

- [ ] **Step 3: Verify table is populated**

```bash
./bouy exec db psql -U postgres -d pantry_pirate_radio -c \
  "SELECT COUNT(*) AS rows, COUNT(DISTINCT zip) AS zips, COUNT(DISTINCT fa_org_id) AS orgs FROM feeding_america_zip_coverage;"
```

Expected: ~30k+ ZIPs and ~200 distinct food bank orgs.

- [ ] **Step 4: Confirm Datasette exposes the table**

In production mode, browse to `http://localhost:8001` and verify `feeding_america_zip_coverage` appears in the table list and CSV export works.

- [ ] **Step 5: Wait for the next daily HAARRRvest publisher run**

Confirm the SQLite export at the public S3 URL now includes the table.

---

## Self-Review Notes

**Spec coverage:**
- Schema → Task 1 ✓
- ZIP universe (Census ZCTA) → Task 2 ✓
- Populator script (parse, fetch w/ retries, upsert, prune, resume state) → Tasks 4–8 ✓
- CLI + bouy integration → Tasks 9–10 ✓
- Surfaces (Datasette + HAARRRvest) → Tasks 9 (smoke) + 13 (operational verification) ✓
- Error handling (retries, failed-zips file, >5% exit nonzero, no silent loss) → Task 5 (retries), Task 8 (failed-zips, prune), Task 9 (threshold) ✓
- Testing (multi-org, single-org, empty, malformed, retry, exhaustion, state, end-to-end) → Tasks 3–8 ✓
- Logging via structlog with the three named events → Task 8 ✓
- Docs (CLAUDE.md) → Task 11 ✓

**Type/name consistency:** `CoverageRow`, `FetchError`, `RunResult`, `parse_response`, `fetch_zip`, `upsert_rows`, `prune_stale_rows`, `load_state`, `save_state`, `run_crosswalk`, `cli_main` — used consistently across tasks 4–9.

**No placeholders found.** All steps contain real code, real commands, real expected output.
