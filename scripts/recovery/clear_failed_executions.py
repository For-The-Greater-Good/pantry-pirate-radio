#!/usr/bin/env python3
"""Delete pending content-store entries (status=pending, no result_path)
created on/after a given date so the next scrape re-enqueues them.

Targets the S3+DynamoDB backend. For local filesystem, use
scripts/cleanup_content_store_since_date.py.

Usage:
    python -m scripts.recovery.clear_failed_executions --since 2026-04-26 [--dry-run]
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

# Refuse a single run that would hit more than this many entries unless --force.
# The recovery flow is operator-driven; an unbounded delete is almost always a typo.
_DEFAULT_MAX_ENTRIES = 50_000

# Refuse --since older than this many days unless --force.
_DEFAULT_MAX_AGE_DAYS = 90

# Stop after this many consecutive per-record failures — likely a systemic
# problem (IAM, throttling) that won't resolve by retrying every record.
_CIRCUIT_BREAKER_FAILURES = 100


def _build_backend():
    """Construct the S3 content-store backend from environment variables."""
    from app.content_store.backend_s3 import S3ContentStoreBackend

    bucket = os.environ.get("CONTENT_STORE_S3_BUCKET", "")
    table = os.environ.get("CONTENT_STORE_DYNAMODB_TABLE", "")
    prefix = os.environ.get("CONTENT_STORE_S3_PREFIX", "")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    if not bucket or not table:
        print(
            "ERROR: CONTENT_STORE_S3_BUCKET and CONTENT_STORE_DYNAMODB_TABLE must be set",
            file=sys.stderr,
        )
        sys.exit(2)

    backend = S3ContentStoreBackend(
        s3_bucket=bucket,
        dynamodb_table=table,
        s3_prefix=prefix,
        region_name=region,
    )
    backend.initialize()
    return backend


def _parse_since(raw: str) -> datetime:
    """Parse the --since value as ISO date or datetime; default tz=UTC."""
    if "T" in raw:
        dt = datetime.fromisoformat(raw)
    else:
        dt = datetime.fromisoformat(raw).replace(tzinfo=UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        required=True,
        help="ISO date or datetime. Entries with created_at >= this value will be considered.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the entries that would be deleted but do not delete them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt (for automated runs).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Override safety caps (max entries, max age). Required for runs "
            "with > 50,000 matches or --since older than 90 days."
        ),
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=_DEFAULT_MAX_ENTRIES,
        help=f"Max entries deletable without --force (default: {_DEFAULT_MAX_ENTRIES})",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=_DEFAULT_MAX_AGE_DAYS,
        help=f"Max age of --since without --force, in days (default: {_DEFAULT_MAX_AGE_DAYS})",
    )
    args = parser.parse_args()

    try:
        since_dt = _parse_since(args.since)
    except ValueError as e:
        print(f"ERROR: invalid --since value: {e}", file=sys.stderr)
        return 2
    since_iso = since_dt.isoformat()

    # Safety cap: refuse old --since unless --force
    age = datetime.now(UTC) - since_dt
    if age > timedelta(days=args.max_age_days) and not args.force:
        print(
            f"ERROR: --since is {age.days} days ago (> {args.max_age_days}). "
            f"Re-run with --force to override.",
            file=sys.stderr,
        )
        return 2

    backend = _build_backend()

    print(f"Scanning content store for pending entries since {since_iso} ...")
    entries = backend.index_scan_pending_since(since_iso)
    if not entries:
        print("No matching entries found.")
        return 0

    # Safety cap: refuse large batches unless --force
    if len(entries) > args.max_entries and not args.force:
        print(
            f"ERROR: {len(entries)} matches exceeds the safety cap of "
            f"{args.max_entries}. Re-run with --force to override.",
            file=sys.stderr,
        )
        return 2

    by_status: dict[str, int] = {}
    has_job_id = 0
    for entry in entries:
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1
        if entry.get("job_id"):
            has_job_id += 1

    print(f"\nFound {len(entries)} pending entries.")
    print("Breakdown by status:")
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")
    print(f"  with job_id assigned: {has_job_id}")

    print("\nFirst 10 (content_hash[:12], created_at, job_id):")
    for entry in entries[:10]:
        job_id = entry.get("job_id") or "-"
        print(f"  {entry['content_hash'][:12]}  {entry['created_at']}  {job_id}")

    if args.dry_run:
        print("\n[--dry-run] No deletes performed.")
        return 0

    if not args.yes:
        confirm = input(f"\nDelete all {len(entries)} entries? type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return 1

    deleted = 0
    failed = 0
    consecutive_failed = 0
    failures: list[tuple[str, str]] = []

    for entry in entries:
        try:
            backend.index_delete_entry(entry["content_hash"])
            deleted += 1
            consecutive_failed = 0
        except Exception as exc:
            failed += 1
            consecutive_failed += 1
            failures.append((entry["content_hash"], str(exc)))
            if consecutive_failed >= _CIRCUIT_BREAKER_FAILURES:
                print(
                    f"\nERROR: {consecutive_failed} consecutive failures — "
                    f"aborting to prevent error storm. Investigate before retrying.",
                    file=sys.stderr,
                )
                break
        if (deleted + failed) % 1000 == 0 and (deleted + failed) > 0:
            print(f"  progress: {deleted} deleted, {failed} failed")

    print(f"\nDeleted {deleted}, failed {failed}.")
    if failures:
        print("First 20 failures:")
        for content_hash, err in failures[:20]:
            print(f"  {content_hash[:12]}  {err}")
        return 1

    print("Re-run scrapers to repopulate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
