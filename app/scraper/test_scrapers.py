"""Command-line utility for testing scrapers."""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from app.scraper.test_utils import run_all_scraper_tests, run_scraper_test

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


async def run_scraper_test_parallel(scraper_name: str) -> tuple[str, dict]:
    """Run a test for a specific scraper in parallel.

    Args:
        scraper_name: Name of the scraper to test

    Returns:
        Tuple of (scraper_name, result_dict)
    """
    logger.info(f"Testing scraper: {scraper_name}")
    result = await run_scraper_test(scraper_name)
    return scraper_name, result


async def run_all_scraper_tests_parallel(max_workers: int = 4) -> dict[str, dict]:
    """Run tests for all available scrapers in parallel.

    Args:
        max_workers: Maximum number of workers to use for parallel execution

    Returns:
        Dictionary of test results by scraper name
    """

    # Get list of available scrapers
    scraper_dir = Path(__file__).parent
    scrapers = []

    for file in scraper_dir.glob("*_scraper.py"):
        name = file.stem.replace("_scraper", "")
        if name != "__init__" and not name.startswith(
            "test_"
        ):  # Skip __init__.py and test files
            scrapers.append(name)

    # Create tasks for each scraper
    tasks = [run_scraper_test_parallel(scraper) for scraper in scrapers]

    # Run tasks in parallel with a limit on concurrency
    results = {}

    # Use semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_workers)

    async def run_with_semaphore(task):
        async with semaphore:
            return await task

    # Run tasks with semaphore
    completed_tasks = await asyncio.gather(
        *[run_with_semaphore(task) for task in tasks]
    )

    # Process results
    for scraper_name, result in completed_tasks:
        results[scraper_name] = result

    return results


async def main() -> None:
    """Run scraper tests based on command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test scrapers without submitting jobs"
    )
    parser.add_argument(
        "scraper", nargs="?", help="Name of the scraper to test (e.g. 'sample')"
    )
    parser.add_argument(
        "--all", action="store_true", help="Test all available scrapers"
    )
    parser.add_argument("--output", help="Path to save test results JSON")
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel (only with --all)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of workers for parallel execution",
    )

    args = parser.parse_args()

    # Require either a scraper name or --all
    if not args.scraper and not args.all:
        parser.error("Please specify a scraper name or use --all to test all scrapers")

    # Run tests
    if args.all:
        logger.info("Testing all scrapers")
        if args.parallel:
            logger.info(f"Running in parallel with max {args.max_workers} workers")
            results = await run_all_scraper_tests_parallel(args.max_workers)
        else:
            results = await run_all_scraper_tests()
    else:
        logger.info(f"Testing scraper: {args.scraper}")
        results = {args.scraper: await run_scraper_test(args.scraper)}

    # Print summary
    print("\nScraper Test Results:")
    print("=====================")

    success_count = 0
    fail_count = 0

    for name, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        duration = f"{result['duration']:.2f}s"

        if result["success"]:
            success_count += 1
        else:
            fail_count += 1

        print(f"{name}: {status} ({duration})")
        if not result["success"] and result.get("error"):
            print(f"  Error: {result['error']}")

    print("\nSummary:")
    print(f"  Total: {len(results)}")
    print(f"  Passed: {success_count}")
    print(f"  Failed: {fail_count}")

    # Save results if requested
    if args.output:
        output_path = Path(args.output)

        # Create directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Add timestamp to results
        output_data = {"timestamp": datetime.now().isoformat(), "results": results}

        # Write to file
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info(f"Test results saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
