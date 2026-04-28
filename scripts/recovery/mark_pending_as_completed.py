#!/usr/bin/env python3
"""Mark all pending content-store entries as completed by pointing them at a
shared placeholder result object.

This is a STOP-GAP. It tells the scraper-side dedup logic to skip these
content_hashes on future runs so they don't keep getting re-enqueued.
The actual underlying records are not processed by this script — they remain
unprocessed in the wider system.

Use when the pending-entry backlog has grown unmanageable (e.g. months of
silently-failed weekly runs accumulated tens of thousands of pending entries
that the dedup logic keeps re-enqueueing because pending-without-job_id is
the re-enqueue condition).

Usage:
    python -m scripts.recovery.mark_pending_as_completed [--dry-run] [--yes]

Environment:
    CONTENT_STORE_S3_BUCKET, CONTENT_STORE_DYNAMODB_TABLE, AWS_DEFAULT_REGION
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import boto3

# Single shared marker — every pending entry's result_path will point here.
_MARKER_PAYLOAD = {
    "result": "marked-as-completed-by-recovery",
    "marker": True,
    "note": (
        "Placeholder result written by mark_pending_as_completed.py to stop "
        "scraper-side dedup from re-enqueueing this content. The original "
        "content was never successfully processed end-to-end."
    ),
}

_MARKER_KEY_SUFFIX = "content_store/results/_recovery_marker.json"

_PARALLEL_WORKERS = 50
_PROGRESS_EVERY = 1000


def _build_clients(bucket: str, table: str, region: str):
    s3 = boto3.client("s3", region_name=region)
    ddb = boto3.client("dynamodb", region_name=region)
    return s3, ddb


def _scan_pending(ddb, table: str):
    """Yield (content_hash, created_at) for all entries lacking result_path."""
    params = {
        "TableName": table,
        "FilterExpression": "attribute_not_exists(result_path)",
        "ProjectionExpression": "content_hash, created_at",
    }
    while True:
        resp = ddb.scan(**params)
        for item in resp.get("Items", []):
            ch = item.get("content_hash", {}).get("S")
            if ch:
                yield ch, item.get("created_at", {}).get("S", "")
        if "LastEvaluatedKey" not in resp:
            break
        params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _mark_one(ddb, table: str, content_hash: str, marker_uri: str, now_iso: str):
    """Update one DDB row to point at the marker."""
    ddb.update_item(
        TableName=table,
        Key={"content_hash": {"S": content_hash}},
        UpdateExpression=(
            "SET result_path = :rp, processed_at = :pa, #st = :status, "
            "job_id = if_not_exists(job_id, :jid)"
        ),
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={
            ":rp": {"S": marker_uri},
            ":pa": {"S": now_iso},
            ":status": {"S": "completed"},
            ":jid": {"S": "recovery-marker"},
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report counts; do not write the marker or update DDB.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=_PARALLEL_WORKERS,
        help=f"Parallel update workers (default: {_PARALLEL_WORKERS})",
    )
    args = parser.parse_args()

    bucket = os.environ.get("CONTENT_STORE_S3_BUCKET", "")
    table = os.environ.get("CONTENT_STORE_DYNAMODB_TABLE", "")
    prefix = os.environ.get("CONTENT_STORE_S3_PREFIX", "")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    if not bucket or not table:
        print(
            "ERROR: CONTENT_STORE_S3_BUCKET and CONTENT_STORE_DYNAMODB_TABLE must be set",
            file=sys.stderr,
        )
        return 2

    prefix_with_slash = prefix.rstrip("/") + "/" if prefix else ""
    marker_key = f"{prefix_with_slash}{_MARKER_KEY_SUFFIX}"
    marker_uri = f"s3://{bucket}/{marker_key}"

    s3, ddb = _build_clients(bucket, table, region)

    print(f"Scanning DynamoDB table: {table}")
    pending: list[tuple[str, str]] = list(_scan_pending(ddb, table))
    print(f"\nFound {len(pending):,} pending entries (no result_path).")

    if not pending:
        return 0

    # Show oldest + newest to give the operator a sense of range.
    by_date = sorted(pending, key=lambda x: x[1])
    print(f"Oldest created_at: {by_date[0][1]}")
    print(f"Newest created_at: {by_date[-1][1]}")
    print(f"\nMarker S3 URI: {marker_uri}")

    if args.dry_run:
        print("\n[--dry-run] No marker written, no DDB updates.")
        return 0

    if not args.yes:
        confirm = input(
            f"\nMark all {len(pending):,} pending entries as completed? "
            "type 'yes' to confirm: "
        )
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return 1

    # Step 1: write the shared marker once.
    print("Writing shared marker to S3 ...")
    s3.put_object(
        Bucket=bucket,
        Key=marker_key,
        Body=json.dumps(_MARKER_PAYLOAD).encode("utf-8"),
        ContentType="application/json",
    )

    # Step 2: parallel DDB updates.
    now_iso = datetime.now(UTC).isoformat()
    print(f"Updating {len(pending):,} DDB entries with {args.workers} workers ...")
    succeeded = 0
    failed = 0
    failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_hash = {
            pool.submit(_mark_one, ddb, table, ch, marker_uri, now_iso): ch
            for ch, _ in pending
        }
        for fut in as_completed(future_to_hash):
            ch = future_to_hash[fut]
            try:
                fut.result()
                succeeded += 1
            except Exception as exc:
                failed += 1
                failures.append((ch, str(exc)))
            if (succeeded + failed) % _PROGRESS_EVERY == 0:
                print(f"  progress: {succeeded:,} ok, {failed:,} failed")

    print(f"\nDone. Updated {succeeded:,}, failed {failed:,}.")
    if failures:
        print("First 10 failures:")
        for ch, err in failures[:10]:
            print(f"  {ch[:12]}  {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
