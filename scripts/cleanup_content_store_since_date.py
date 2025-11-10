#!/usr/bin/env python3
"""Delete content store entries since a specific date.

This script removes all content store entries created on or after a specified date.
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def delete_entries_since_date(
    content_store_path: Path, since_date: str, dry_run: bool = True
):
    """Delete all content store entries since a specific date.

    Args:
        content_store_path: Path to content store directory
        since_date: ISO date string (YYYY-MM-DD)
        dry_run: If True, only show what would be done
    """
    db_path = content_store_path / "index.db"

    if not db_path.exists():
        print(f"ERROR: Content store index not found at {db_path}")
        sys.exit(1)

    with sqlite3.connect(db_path) as conn:
        # Get entries to delete
        entries = conn.execute(
            """
            SELECT hash, status, content_path, created_at
            FROM content_index
            WHERE created_at >= ?
            ORDER BY created_at DESC
        """,
            (since_date,),
        ).fetchall()

        if not entries:
            print(f"No entries found since {since_date}")
            return

        # Get statistics
        stats_by_status = {}
        for _, status, _, _ in entries:
            stats_by_status[status] = stats_by_status.get(status, 0) + 1

        print(f"\n{'DRY RUN: Would delete' if dry_run else 'Deleting'} {len(entries)} entries since {since_date}:")
        for status, count in sorted(stats_by_status.items()):
            print(f"  {status}: {count}")

        if dry_run:
            print(f"\nShowing first 10 entries that would be deleted:")
            for i, (hash_val, status, content_path, created_at) in enumerate(
                entries[:10]
            ):
                print(f"  {hash_val[:8]}... ({status}, {created_at})")
            if len(entries) > 10:
                print(f"  ... and {len(entries) - 10} more")
            return

        # Actually delete entries
        deleted_files = 0
        deleted_db = 0
        errors = []

        print(f"\nDeleting {len(entries)} entries...")

        for hash_val, status, content_path, created_at in entries:
            try:
                # Delete content file if it exists
                if content_path:
                    file_path = Path(content_path)
                    if file_path.exists():
                        file_path.unlink()
                        deleted_files += 1

                # Delete from database
                conn.execute("DELETE FROM content_index WHERE hash = ?", (hash_val,))
                deleted_db += 1

            except Exception as e:
                errors.append(f"  {hash_val[:8]}...: {e}")

        conn.commit()

        print(f"\nDeleted:")
        print(f"  Database entries: {deleted_db}")
        print(f"  Content files: {deleted_files}")

        if errors:
            print(f"\nErrors ({len(errors)}):")
            for error in errors[:10]:
                print(error)
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors")

        # Show remaining statistics
        remaining = conn.execute("SELECT COUNT(*) FROM content_index").fetchone()[0]
        by_status = conn.execute(
            """
            SELECT status, COUNT(*)
            FROM content_index
            GROUP BY status
        """
        ).fetchall()

        print(f"\nRemaining entries: {remaining}")
        for status, count in by_status:
            print(f"  {status}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Delete content store entries since a specific date"
    )
    parser.add_argument(
        "--content-store-path",
        type=Path,
        default=Path("/data-repo/content_store"),
        help="Path to content store directory",
    )
    parser.add_argument(
        "--since-date",
        required=True,
        help="Delete entries since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Validate date format
    try:
        datetime.strptime(args.since_date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Invalid date format. Use YYYY-MM-DD")
        sys.exit(1)

    print(f"Content Store Cleanup Since Date")
    print(f"=================================")
    print(f"Content store: {args.content_store_path}")
    print(f"Since date: {args.since_date}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")

    if not args.dry_run and not args.yes:
        response = input(
            f"\nAre you sure you want to delete all entries since {args.since_date}? [y/N] "
        )
        if response.lower() != "y":
            print("Cleanup cancelled.")
            return

    delete_entries_since_date(args.content_store_path, args.since_date, args.dry_run)


if __name__ == "__main__":
    main()
