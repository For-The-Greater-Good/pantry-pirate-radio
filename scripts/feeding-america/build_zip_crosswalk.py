#!/usr/bin/env python3
"""Build the Feeding America ZIP -> food bank crosswalk CSV.

One-shot: iterates every US ZIP listed in data/zcta_us.txt against
Feeding America's GetOrganizationsByZip API and appends rows to
data/feeding_america_zip_coverage.csv. Many-to-many — a single ZIP can
return multiple food banks (e.g. NYC has both Food Bank For NYC and
City Harvest).

Resumable: rerunning skips ZIPs already present in the CSV. Failed ZIPs
are appended to data/.crosswalk_failed_zips.txt for follow-up.

Usage (run inside the app container):
    ./bouy exec app python scripts/feeding-america/build_zip_crosswalk.py
    ./bouy exec app python scripts/feeding-america/build_zip_crosswalk.py --concurrency 30

The ZCTA input list comes from the US Census Gazetteer; if it's missing
the script prints instructions on how to source it.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import time
from pathlib import Path

import httpx

API_URL = "https://www.feedingamerica.org/ws-api/GetOrganizationsByZip"
DATA_DIR = Path(__file__).parent / "data"
ZCTA_PATH = DATA_DIR / "zcta_us.txt"
CSV_PATH = DATA_DIR / "feeding_america_zip_coverage.csv"
FAILED_PATH = DATA_DIR / ".crosswalk_failed_zips.txt"
HEADER = ["zip", "fa_org_id", "fa_org_name"]
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2.0
PROGRESS_EVERY = 500


ZCTA_INSTRUCTIONS = f"""\
ERROR: {ZCTA_PATH} not found.

Source the Census ZCTA list (one-time):
    curl -sSLO https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip
    unzip -o 2024_Gaz_zcta_national.zip
    tail -n +2 2024_Gaz_zcta_national.txt | awk -F'\\t' '{{print $1}}' | sort -u > {ZCTA_PATH}
"""


def load_completed_zips(csv_path: Path) -> set[str]:
    """Return the set of ZIPs already present in the CSV (for resume)."""
    if not csv_path.exists():
        return set()
    completed: set[str] = set()
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            completed.add(row["zip"])
    return completed


def ensure_csv_header(csv_path: Path) -> None:
    """Create the CSV with a header row if it doesn't already exist."""
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)


def parse_organizations(zip_code: str, payload: dict) -> list[tuple[str, int, str]]:
    """Extract (zip, fa_org_id, fa_org_name) rows from an API payload.

    FA's API returns "Organization" as a single dict when there is exactly
    one food bank, a list when there are multiple, and None/missing when
    no food bank serves the ZIP. Normalize all three shapes.
    """
    org_data = payload.get("Organization")
    if isinstance(org_data, dict):
        org_list: list[dict] = [org_data]
    elif isinstance(org_data, list):
        org_list = [o for o in org_data if isinstance(o, dict)]
    else:
        return []

    rows: list[tuple[str, int, str]] = []
    for org in org_list:
        org_id = org.get("OrganizationID")
        name = org.get("FullName") or ""
        if isinstance(org_id, int):
            rows.append((zip_code, org_id, name))
    return rows


async def fetch_zip_async(
    client: httpx.AsyncClient, zip_code: str
) -> list[tuple[str, int, str]]:
    """Fetch one ZIP with bounded retries on network/5xx errors."""
    last_exc: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.get(API_URL, params={"zip": zip_code})
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return parse_organizations(zip_code, response.json())
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            last_exc = exc
            if attempt + 1 < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
    raise RuntimeError(f"failed to fetch zip {zip_code}: {last_exc}")


async def run(todo: list[str], total_zips: int, concurrency: int) -> tuple[int, int]:
    """Drive the fetch loop concurrently. Returns (rows_written, failures)."""
    sem = asyncio.Semaphore(concurrency)
    csv_lock = asyncio.Lock()
    rows_written = 0
    failures = 0
    completed = 0
    start = time.monotonic()

    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )
    async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:

        async def process(zip_code: str) -> None:
            nonlocal rows_written, failures, completed
            async with sem:
                try:
                    rows = await fetch_zip_async(client, zip_code)
                except RuntimeError as exc:
                    async with csv_lock:
                        with FAILED_PATH.open("a") as failed_f:
                            failed_f.write(f"{zip_code}\n")
                        failures += 1
                        completed += 1
                        _maybe_log_progress(
                            completed,
                            total_zips,
                            rows_written,
                            failures,
                            start,
                            exc=exc,
                            zip_code=zip_code,
                        )
                    return

                async with csv_lock:
                    if rows:
                        with CSV_PATH.open("a", newline="") as csv_f:
                            writer = csv.writer(csv_f)
                            for row in rows:
                                writer.writerow(row)
                        rows_written += len(rows)
                    completed += 1
                    _maybe_log_progress(
                        completed, total_zips, rows_written, failures, start
                    )

        await asyncio.gather(*(process(z) for z in todo))

    return rows_written, failures


def _maybe_log_progress(
    completed: int,
    total: int,
    rows_written: int,
    failures: int,
    start: float,
    *,
    exc: Exception | None = None,
    zip_code: str | None = None,
) -> None:
    """Print progress on a cadence; always print failures."""
    if exc is not None and zip_code is not None:
        print(f"[{completed}/{total}] {zip_code} FAILED: {exc}", file=sys.stderr)
        return
    if completed % PROGRESS_EVERY != 0:
        return
    elapsed = time.monotonic() - start
    rate = completed / elapsed if elapsed > 0 else 0
    eta_min = ((total - completed) / rate / 60) if rate > 0 else 0
    print(
        f"[{completed}/{total}] rows: {rows_written}, failed: {failures}, "
        f"rate: {rate:.1f}/s, ETA: {eta_min:.1f}min",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build FA ZIP crosswalk CSV.")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="number of concurrent in-flight requests (default 20)",
    )
    args = parser.parse_args(argv)

    if not ZCTA_PATH.exists():
        print(ZCTA_INSTRUCTIONS, file=sys.stderr)
        return 1

    ensure_csv_header(CSV_PATH)
    completed_set = load_completed_zips(CSV_PATH)

    zips = [z.strip() for z in ZCTA_PATH.read_text().splitlines() if z.strip()]
    todo = [z for z in zips if z not in completed_set]
    print(
        f"resuming with {len(completed_set)} ZIPs already in CSV; "
        f"{len(todo)} of {len(zips)} remaining; concurrency={args.concurrency}",
        file=sys.stderr,
    )

    rows_written, failures = asyncio.run(run(todo, len(todo), args.concurrency))

    print(
        f"DONE. processed: {len(todo) - failures}, failed: {failures}, "
        f"rows written this run: {rows_written}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
