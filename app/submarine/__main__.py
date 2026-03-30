"""CLI entry point for the submarine module.

Usage:
    python -m app.submarine scan [--limit N] [--location-id UUID] [--scraper NAME]
    python -m app.submarine status
"""

import argparse
import json
import os
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
    scan_parser.add_argument(
        "--scraper",
        type=str,
        default=None,
        help="Filter to locations from a specific scraper (e.g. capital_area_food_bank_dc)",
    )

    # status command
    subparsers.add_parser("status", help="Show submarine job counts")

    args = parser.parse_args()

    if args.command == "scan":
        from app.submarine.scanner import scan_and_enqueue

        # CLI args take priority, env vars as fallback (for Step Functions)
        env_limit = os.environ.get("SUBMARINE_LIMIT")
        if args.limit:
            limit = args.limit
        elif env_limit:
            try:
                limit = int(env_limit)
            except ValueError:
                print(
                    f"Error: SUBMARINE_LIMIT must be an integer, got '{env_limit}'",
                    file=sys.stderr,
                )
                return 1
        else:
            limit = None
        scraper_id = args.scraper or os.environ.get("SUBMARINE_SCRAPER_FILTER") or None

        summary = scan_and_enqueue(
            limit=limit,
            location_id=args.location_id,
            scraper_id=scraper_id,
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
