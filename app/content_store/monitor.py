"""Monitoring and reporting tools for content store."""

import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from app.content_store.store import ContentStore


logger = logging.getLogger(__name__)


class ContentStoreMonitor:
    """Monitor and report on content store usage and efficiency."""

    def __init__(self, content_store: ContentStore):
        """Initialize monitor with content store instance.

        Args:
            content_store: ContentStore instance to monitor
        """
        self.content_store = content_store

    def get_statistics(self) -> Dict[str, Any]:
        """Get enhanced statistics from content store.

        Returns:
            Dictionary with detailed statistics
        """
        # Get basic stats
        basic_stats = self.content_store.get_statistics()

        # Calculate additional metrics
        total = basic_stats["total_content"]
        processed = basic_stats["processed_content"]

        stats = {
            **basic_stats,
            "processing_rate": processed / total if total > 0 else 0,
            "store_size_mb": basic_stats["store_size_bytes"] / (1024 * 1024),
        }

        return stats

    def get_scraper_breakdown(self) -> Dict[str, Dict[str, int]]:
        """Get content breakdown by scraper.

        Returns:
            Dictionary mapping scraper_id to content counts
        """
        breakdown: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "processed": 0, "pending": 0}
        )

        # Query SQLite index for scraper information
        db_path = self.content_store.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            # Get all content files and parse metadata
            cursor = conn.execute("SELECT content_path, status FROM content_index")

            for content_path, status in cursor.fetchall():
                # Read content file to get metadata
                path = Path(content_path)
                if path.exists():
                    try:
                        data = json.loads(path.read_text())
                        scraper_id = data.get("metadata", {}).get(
                            "scraper_id", "unknown"
                        )

                        breakdown[scraper_id]["total"] += 1
                        if status == "completed":
                            breakdown[scraper_id]["processed"] += 1
                        else:
                            breakdown[scraper_id]["pending"] += 1
                    except Exception as e:
                        logger.debug(f"Failed to parse content file {path}: {e}")
                        continue

        return dict(breakdown)

    def get_processing_timeline(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get processing timeline for the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of daily statistics
        """
        timeline = []
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        db_path = self.content_store.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            # Get daily counts
            cursor = conn.execute(
                """
                SELECT DATE(created_at) as date,
                       COUNT(*) as total,
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as processed
                FROM content_index
                WHERE created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date
                """,
                (start_date.isoformat(),),
            )

            for date_str, total, processed in cursor.fetchall():
                timeline.append(
                    {
                        "date": date_str,
                        "total": total,
                        "processed": processed,
                        "pending": total - processed,
                    }
                )

        return timeline

    def find_duplicates(self) -> Dict[str, Dict[str, Any]]:
        """Find duplicate content submissions.

        Returns:
            Dictionary mapping content hash to duplicate information
        """
        duplicates = {}

        # Read all content files to find duplicates
        content_dir = self.content_store.content_store_path / "content"

        content_map = defaultdict(list)

        for content_file in content_dir.rglob("*.json"):
            try:
                data = json.loads(content_file.read_text())
                content_hash = content_file.stem
                metadata = data.get("metadata", {})

                content_map[content_hash].append(
                    {
                        "scraper_id": metadata.get("scraper_id", "unknown"),
                        "timestamp": data.get("timestamp"),
                        "metadata": metadata,
                    }
                )
            except Exception as e:
                logger.debug(f"Failed to read content file {content_file}: {e}")
                continue

        # Filter to only duplicates
        for content_hash, entries in content_map.items():
            if len(entries) > 1:
                duplicates[content_hash] = {
                    "count": len(entries),
                    "sources": [e["scraper_id"] for e in entries],
                    "first_seen": min(
                        e["timestamp"] for e in entries if e["timestamp"]
                    ),
                    "last_seen": max(e["timestamp"] for e in entries if e["timestamp"]),
                }

        return duplicates

    def get_storage_efficiency(self) -> Dict[str, Any]:
        """Calculate storage efficiency metrics.

        Returns:
            Dictionary with efficiency metrics
        """
        # Count total submissions vs unique content
        db_path = self.content_store.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            # Count unique content
            unique_count = conn.execute(
                "SELECT COUNT(DISTINCT hash) FROM content_index"
            ).fetchone()[0]

        # Count total submissions (including duplicates)
        total_submissions = 0
        content_dir = self.content_store.content_store_path / "content"

        # In our implementation, each hash only has one file
        # So we need to check metadata for duplicate submissions
        duplicates = self.find_duplicates()

        total_submissions = unique_count + sum(
            d["count"] - 1 for d in duplicates.values()
        )

        if total_submissions == 0:
            total_submissions = unique_count

        # Calculate metrics
        dedup_rate = (
            (total_submissions - unique_count) / total_submissions
            if total_submissions > 0
            else 0
        )

        return {
            "total_submissions": total_submissions,
            "unique_content": unique_count,
            "duplicates_avoided": total_submissions - unique_count,
            "deduplication_rate": dedup_rate,
            "space_saved_percentage": dedup_rate * 100,
        }

    def get_recent_activity(self, hours: int = 24) -> Dict[str, Any]:
        """Get recent processing activity.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary with recent activity metrics
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        db_path = self.content_store.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            # Get recent submissions
            submissions = conn.execute(
                """
                SELECT COUNT(*) FROM content_index
                WHERE created_at >= ?
                """,
                (cutoff_time.isoformat(),),
            ).fetchone()[0]

            # Get recent processed
            processed = conn.execute(
                """
                SELECT COUNT(*) FROM content_index
                WHERE processed_at >= ?
                """,
                (cutoff_time.isoformat(),),
            ).fetchone()[0]

            # Get hourly breakdown
            hourly = conn.execute(
                """
                SELECT strftime('%H', created_at) as hour,
                       COUNT(*) as count
                FROM content_index
                WHERE created_at >= ?
                GROUP BY hour
                ORDER BY hour
                """,
                (cutoff_time.isoformat(),),
            ).fetchall()

        return {
            f"submissions_{hours}h": submissions,
            f"processed_{hours}h": processed,
            "hourly_breakdown": [{"hour": h, "count": c} for h, c in hourly],
        }

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report.

        Returns:
            Dictionary with full report data
        """
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "statistics": self.get_statistics(),
            "scraper_breakdown": self.get_scraper_breakdown(),
            "processing_timeline": self.get_processing_timeline(),
            "storage_efficiency": self.get_storage_efficiency(),
            "recent_activity": self.get_recent_activity(),
        }

        # Add summary
        scrapers = cast(Dict[str, Any], report["scraper_breakdown"])
        stats = cast(Dict[str, Any], report["statistics"])
        efficiency = cast(Dict[str, Any], report["storage_efficiency"])
        activity = cast(Dict[str, Any], report["recent_activity"])

        summary_dict = {
            "total_content": stats.get("total_content", 0),
            "total_scrapers": len(scrapers),
            "processing_rate": stats.get("processing_rate", 0),
            "deduplication_rate": efficiency.get("deduplication_rate", 0),
            "active_last_24h": activity.get("submissions_24h", 0) > 0,
        }
        report["summary"] = summary_dict

        return report

    def export_report(self, output_path: Path) -> None:
        """Export monitoring report to file.

        Args:
            output_path: Path where to save the report
        """
        report = self.generate_report()

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write report
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    def print_summary(self) -> None:
        """Print a human-readable summary to console."""
        stats = self.get_statistics()
        efficiency = self.get_storage_efficiency()

        print("\n=== Content Store Summary ===")
        print(f"Total Content: {stats['total_content']:,}")
        print(
            f"Processed: {stats['processed_content']:,} ({stats['processing_rate']:.1%})"
        )
        print(f"Pending: {stats['pending_content']:,}")
        print(f"Store Size: {stats['store_size_mb']:.2f} MB")
        print(f"\nDeduplication Rate: {efficiency['deduplication_rate']:.1%}")
        print(f"Space Saved: {efficiency['space_saved_percentage']:.1f}%")

        # Scraper breakdown
        breakdown = self.get_scraper_breakdown()
        if breakdown:
            print("\n=== Scraper Breakdown ===")
            for scraper, counts in sorted(breakdown.items()):
                print(
                    f"{scraper}: {counts['total']} total, "
                    f"{counts['processed']} processed, "
                    f"{counts['pending']} pending"
                )


def main():
    """CLI entry point for content store monitoring."""
    import argparse
    from app.content_store.config import get_content_store

    parser = argparse.ArgumentParser(description="Monitor content store")
    parser.add_argument("--report", help="Export report to file")
    parser.add_argument("--summary", action="store_true", help="Print summary")

    args = parser.parse_args()

    # Get content store
    store = get_content_store()
    if not store:
        print("Content store not configured")
        return

    monitor = ContentStoreMonitor(store)

    if args.report:
        monitor.export_report(Path(args.report))
        print(f"Report exported to {args.report}")

    if args.summary or not args.report:
        monitor.print_summary()


if __name__ == "__main__":
    main()
