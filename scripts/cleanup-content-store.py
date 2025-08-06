#!/usr/bin/env python3
"""Cleanup orphaned pending entries from content store.

This script identifies and removes content store entries that:
1. Have status='pending'
2. Have a job_id that is no longer active in Redis
3. Are older than a specified age threshold
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import redis
from rq.job import Job


def get_orphaned_entries(db_path: Path, redis_conn, age_hours: int = 24):
    """Find orphaned pending entries in content store.

    Args:
        db_path: Path to index.db
        redis_conn: Redis connection
        age_hours: Minimum age in hours for entries to be considered

    Returns:
        List of (hash, job_id, content_path, created_at) tuples
    """
    orphaned = []

    # Calculate age threshold
    threshold = datetime.utcnow() - timedelta(hours=age_hours)

    with sqlite3.connect(db_path) as conn:
        # Find all pending entries older than threshold
        cursor = conn.execute("""
            SELECT hash, job_id, content_path, created_at
            FROM content_index
            WHERE status = 'pending'
            AND created_at < ?
        """, (threshold,))

        for row in cursor:
            hash_val, job_id, content_path, created_at = row

            # Check if job is still active
            is_active = False
            if job_id:
                try:
                    job = Job.fetch(job_id, connection=redis_conn)
                    status = job.get_status()
                    is_active = status in ["queued", "started", "deferred", "scheduled"]
                except Exception:
                    # Job doesn't exist or can't be fetched
                    is_active = False

            if not is_active:
                orphaned.append((hash_val, job_id, content_path, created_at))

    return orphaned


def cleanup_entries(db_path: Path, content_store_path: Path, entries, dry_run: bool = True):
    """Remove orphaned entries from content store.

    Args:
        db_path: Path to index.db
        content_store_path: Path to content store directory
        entries: List of entries to remove
        dry_run: If True, only show what would be done

    Returns:
        Number of entries cleaned up
    """
    if dry_run:
        print(f"\nDRY RUN: Would remove {len(entries)} orphaned entries")
    else:
        print(f"\nRemoving {len(entries)} orphaned entries...")

    cleaned = 0

    for hash_val, job_id, content_path, created_at in entries:
        if dry_run:
            print(f"  Would remove: {hash_val[:8]}... (job_id={job_id}, created={created_at})")
        else:
            try:
                # Remove content file
                if content_path and Path(content_path).exists():
                    Path(content_path).unlink()

                # Remove from index
                with sqlite3.connect(db_path) as conn:
                    conn.execute("DELETE FROM content_index WHERE hash = ?", (hash_val,))
                    conn.commit()

                cleaned += 1
                print(f"  Removed: {hash_val[:8]}... (job_id={job_id})")

            except Exception as e:
                print(f"  ERROR removing {hash_val[:8]}...: {e}")

    return cleaned


def main():
    parser = argparse.ArgumentParser(description="Cleanup orphaned content store entries")
    parser.add_argument(
        "--content-store-path",
        type=Path,
        default=Path("/data-repo/content_store"),
        help="Path to content store directory"
    )
    parser.add_argument(
        "--redis-url",
        default="redis://cache:6379",
        help="Redis connection URL"
    )
    parser.add_argument(
        "--age-hours",
        type=int,
        default=24,
        help="Minimum age in hours for entries to be considered orphaned (default: 24)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    # Validate paths
    db_path = args.content_store_path / "index.db"
    if not db_path.exists():
        print(f"ERROR: Content store index not found at {db_path}")
        sys.exit(1)

    # Connect to Redis
    try:
        redis_conn = redis.from_url(args.redis_url)
        redis_conn.ping()
    except Exception as e:
        print(f"ERROR: Failed to connect to Redis: {e}")
        sys.exit(1)

    print(f"Content Store Cleanup")
    print(f"====================")
    print(f"Index DB: {db_path}")
    print(f"Redis URL: {args.redis_url}")
    print(f"Age threshold: {args.age_hours} hours")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")

    # Get current statistics
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM content_index").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM content_index WHERE status = 'pending'"
        ).fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM content_index WHERE status = 'completed'"
        ).fetchone()[0]

    print(f"\nCurrent statistics:")
    print(f"  Total entries: {total}")
    print(f"  Pending: {pending}")
    print(f"  Completed: {completed}")

    # Find orphaned entries
    print(f"\nSearching for orphaned entries older than {args.age_hours} hours...")
    orphaned = get_orphaned_entries(db_path, redis_conn, args.age_hours)

    if not orphaned:
        print("No orphaned entries found.")
        return

    print(f"Found {len(orphaned)} orphaned entries")

    # Show sample of what will be cleaned
    if len(orphaned) > 10:
        print("\nShowing first 10 entries:")
        sample = orphaned[:10]
    else:
        print("\nEntries to clean:")
        sample = orphaned

    for hash_val, job_id, content_path, created_at in sample:
        print(f"  {hash_val[:8]}... job_id={job_id or 'None'}, created={created_at}")

    if len(orphaned) > 10:
        print(f"  ... and {len(orphaned) - 10} more")

    # Cleanup
    if not args.dry_run:
        response = input("\nProceed with cleanup? [y/N] ")
        if response.lower() != 'y':
            print("Cleanup cancelled.")
            return

    cleaned = cleanup_entries(db_path, args.content_store_path, orphaned, args.dry_run)

    if not args.dry_run:
        print(f"\nCleanup complete. Removed {cleaned} entries.")

        # Show updated statistics
        with sqlite3.connect(db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM content_index").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM content_index WHERE status = 'pending'"
            ).fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM content_index WHERE status = 'completed'"
            ).fetchone()[0]

        print(f"\nUpdated statistics:")
        print(f"  Total entries: {total}")
        print(f"  Pending: {pending}")
        print(f"  Completed: {completed}")


if __name__ == "__main__":
    main()