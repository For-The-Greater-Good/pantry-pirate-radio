"""Content store CLI interface."""

import argparse
import sys
from pathlib import Path

from app.content_store.config import get_content_store
from app.content_store.monitor import ContentStoreMonitor


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Content Store Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show content store status
  python -m app.content_store status

  # Generate detailed report
  python -m app.content_store report --output report.json

  # Find duplicate content
  python -m app.content_store duplicates

  # Show storage efficiency
  python -m app.content_store efficiency
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show content store status")
    status_parser.add_argument(
        "--detailed", action="store_true", help="Show detailed breakdown"
    )

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate monitoring report")
    report_parser.add_argument(
        "--output", "-o", help="Output file path", default="content_store_report.json"
    )

    # Duplicates command
    dup_parser = subparsers.add_parser("duplicates", help="Find duplicate content")
    dup_parser.add_argument(
        "--limit", type=int, default=10, help="Limit number of results"
    )

    # Efficiency command
    eff_parser = subparsers.add_parser(
        "efficiency", help="Show storage efficiency metrics"
    )

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show detailed statistics")
    stats_parser.add_argument(
        "--days", type=int, default=7, help="Number of days for timeline"
    )

    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Run web dashboard")
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    dashboard_parser.add_argument(
        "--port", type=int, default=5050, help="Port to bind to"
    )

    args = parser.parse_args()

    # Get content store
    store = get_content_store()
    if not store:
        print("Error: Content store not configured", file=sys.stderr)
        print("Set CONTENT_STORE_PATH environment variable", file=sys.stderr)
        sys.exit(1)

    monitor = ContentStoreMonitor(store)

    # Execute command
    if args.command == "status":
        monitor.print_summary()

        if args.detailed:
            print("\n=== Recent Activity (24h) ===")
            activity = monitor.get_recent_activity()
            print(f"Submissions: {activity['submissions_24h']}")
            print(f"Processed: {activity['processed_24h']}")

    elif args.command == "report":
        output_path = Path(args.output)
        monitor.export_report(output_path)
        print(f"Report saved to: {output_path}")

        # Also print summary
        monitor.print_summary()

    elif args.command == "duplicates":
        duplicates = monitor.find_duplicates()

        if not duplicates:
            print("No duplicate content found")
        else:
            print(f"\n=== Duplicate Content ({len(duplicates)} found) ===")

            # Sort by count
            sorted_dups = sorted(
                duplicates.items(), key=lambda x: x[1]["count"], reverse=True
            )[: args.limit]

            for content_hash, info in sorted_dups:
                print(f"\nHash: {content_hash[:16]}...")
                print(f"  Count: {info['count']}")
                print(f"  Sources: {', '.join(info['sources'])}")
                print(f"  First seen: {info['first_seen']}")

    elif args.command == "efficiency":
        efficiency = monitor.get_storage_efficiency()

        print("\n=== Storage Efficiency ===")
        print(f"Total Submissions: {efficiency['total_submissions']:,}")
        print(f"Unique Content: {efficiency['unique_content']:,}")
        print(f"Duplicates Avoided: {efficiency['duplicates_avoided']:,}")
        print(f"Deduplication Rate: {efficiency['deduplication_rate']:.1%}")
        print(f"Space Saved: {efficiency['space_saved_percentage']:.1f}%")

    elif args.command == "stats":
        stats = monitor.get_statistics()

        print("\n=== Detailed Statistics ===")
        print(f"Total Content: {stats['total_content']:,}")
        print(f"Processed: {stats['processed_content']:,}")
        print(f"Pending: {stats['pending_content']:,}")
        print(f"Processing Rate: {stats['processing_rate']:.1%}")
        print(f"Store Size: {stats['store_size_mb']:.2f} MB")

        # Timeline
        print(f"\n=== Processing Timeline (Last {args.days} days) ===")
        timeline = monitor.get_processing_timeline(days=args.days)

        for day in timeline:
            print(
                f"{day['date']}: {day['total']} total, "
                f"{day['processed']} processed, "
                f"{day['pending']} pending"
            )

    elif args.command == "dashboard":
        from app.content_store.dashboard import app

        print(f"Starting Content Store Dashboard on http://{args.host}:{args.port}")
        print("Access the dashboard at http://localhost:5050 from your host machine")
        app.run(host=args.host, port=args.port, debug=False)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
