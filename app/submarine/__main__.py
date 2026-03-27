"""CLI entry point for the submarine module.

Usage:
    python -m app.submarine scan [--limit N] [--location-id UUID]
    python -m app.submarine status
"""

import argparse
import json
import sys

import structlog

logger = structlog.get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scraper Submarine — crawl food bank websites for missing data"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan command
    scan_parser = subparsers.add_parser(
        "scan", help="Scan DB for locations with gaps and enqueue submarine jobs"
    )
    scan_parser.add_argument(
        "--limit", type=int, default=None, help="Maximum number of jobs to enqueue"
    )
    scan_parser.add_argument(
        "--location-id", type=str, default=None, help="Target a specific location ID"
    )

    # status command
    subparsers.add_parser("status", help="Show submarine job counts")

    args = parser.parse_args()

    if args.command == "scan":
        from app.submarine.scanner import scan_and_enqueue

        summary = scan_and_enqueue(
            limit=args.limit,
            location_id=args.location_id,
        )
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "status":
        from app.submarine.status import get_status

        status = get_status()
        print(json.dumps(status, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
