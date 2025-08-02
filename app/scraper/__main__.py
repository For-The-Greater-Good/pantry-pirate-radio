"""Main entry point for running scrapers as a module."""

import argparse
import asyncio
import importlib
import logging
import sys
import time
from pathlib import Path

from app.scraper.utils import ScraperJob

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


def load_scraper_class(scraper_name: str) -> type[ScraperJob]:
    """Dynamically load scraper class by name.

    Args:
        scraper_name: Name of the scraper to load (e.g. 'sample' for SampleScraper)

    Returns:
        Scraper class that inherits from ScraperJob

    Raises:
        ImportError: If scraper module/class cannot be imported
        ValueError: If loaded class is not a ScraperJob
    """
    # Special handling for scrapers with state abbreviations
    # Convert snake_case to CamelCase for all scrapers
    # Split by underscore and capitalize each part
    parts = scraper_name.split("_")
    camel_parts = [part.capitalize() for part in parts]
    class_name = f"{''.join(camel_parts)}Scraper"

    try:
        module = importlib.import_module(f"app.scraper.{scraper_name}_scraper")
        scraper_class: type[ScraperJob] = getattr(module, class_name)
        return scraper_class

    except ImportError as e:
        logger.error(f"Failed to import scraper '{scraper_name}': {e}")
        raise
    except AttributeError as e:
        logger.error(f"Scraper class '{class_name}' not found: {e}")
        raise ImportError(f"Scraper class '{class_name}' not found") from e


def list_available_scrapers() -> list[str]:
    """List all available scrapers in the app/scraper directory.

    Returns:
        List of scraper names (without '_scraper.py' suffix)
    """
    scraper_dir = Path(__file__).parent
    scrapers: list[str] = []

    for file in scraper_dir.glob("*_scraper.py"):
        name = file.stem.replace("_scraper", "")
        if name != "__init__":  # Skip __init__.py
            scrapers.append(name)

    return sorted(scrapers)


async def run_scraper_parallel(scraper_name: str) -> tuple[str, bool, float, str]:
    """Run a scraper in parallel.

    Args:
        scraper_name: Name of the scraper to run

    Returns:
        Tuple of (scraper_name, success, duration, error_message)
    """
    start_time = time.time()
    success = False
    error_message = ""

    try:
        logger.info(f"Running scraper: {scraper_name}")

        # Load and run the scraper
        scraper_class = load_scraper_class(scraper_name)
        scraper = scraper_class(scraper_id=scraper_name)
        await scraper.run()

        success = True
        logger.info(f"Scraper {scraper_name} completed successfully")
    except Exception as e:
        error_message = str(e)
        logger.error(f"Scraper {scraper_name} failed: {error_message}")

    duration = time.time() - start_time
    return scraper_name, success, duration, error_message


async def run_all_scrapers_parallel(max_workers: int = 4) -> dict[str, dict]:
    """Run all available scrapers in parallel.

    Args:
        max_workers: Maximum number of workers to use for parallel execution

    Returns:
        Dictionary of results by scraper name
    """
    # Get list of available scrapers
    scrapers = list_available_scrapers()
    logger.info(f"Found {len(scrapers)} scrapers to run")

    # Create tasks for each scraper
    tasks = [run_scraper_parallel(scraper) for scraper in scrapers]

    # Use semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_workers)

    async def run_with_semaphore(task):
        async with semaphore:
            return await task

    # Run tasks with semaphore
    results = {}
    completed_tasks = await asyncio.gather(
        *[run_with_semaphore(task) for task in tasks]
    )

    # Process results
    for scraper_name, success, duration, error_message in completed_tasks:
        results[scraper_name] = {
            "success": success,
            "duration": duration,
            "error": error_message if not success else None,
        }

    return results


async def main() -> None:
    """Run the specified scraper(s)."""
    parser = argparse.ArgumentParser(description="Run a scraper")
    parser.add_argument(
        "scraper", nargs="?", help="Name of the scraper to run (e.g. 'sample')"
    )
    parser.add_argument("--list", action="store_true", help="List available scrapers")
    parser.add_argument("--all", action="store_true", help="Run all available scrapers")
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run scrapers in parallel (only with --all)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of workers for parallel execution",
    )

    args = parser.parse_args()

    # List available scrapers if requested
    if args.list:
        scrapers = list_available_scrapers()
        print("\nAvailable scrapers:")
        for name in scrapers:
            print(f"  - {name}")
        print()
        return

    # Require either a scraper name or --all
    if not args.scraper and not args.all:
        parser.error("Please specify a scraper name or use --all to run all scrapers")

    try:
        if args.all:
            # Run all scrapers
            if args.parallel:
                logger.info(
                    f"Running all scrapers in parallel with max {args.max_workers} workers"
                )
                results = await run_all_scrapers_parallel(args.max_workers)

                # Print summary
                print("\nScraper Run Results:")
                print("====================")

                success_count = 0
                fail_count = 0

                for name, result in results.items():
                    status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
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
                print(f"  Successful: {success_count}")
                print(f"  Failed: {fail_count}")

                # Exit with error if any scraper failed
                if fail_count > 0:
                    sys.exit(1)
            else:
                # Run all scrapers sequentially
                logger.info("Running all scrapers sequentially")
                scrapers = list_available_scrapers()
                for scraper_name in scrapers:
                    try:
                        logger.info(f"Running scraper: {scraper_name}")
                        scraper_class = load_scraper_class(scraper_name)
                        scraper = scraper_class(scraper_id=scraper_name)
                        await scraper.run()
                        logger.info(f"Scraper {scraper_name} completed successfully")
                    except Exception as e:
                        logger.error(f"Scraper {scraper_name} failed: {e}")
                        # Continue with next scraper
        else:
            # Run a single scraper
            logger.info(f"Running scraper: {args.scraper}")
            scraper_class = load_scraper_class(args.scraper)
            scraper = scraper_class(scraper_id=args.scraper)
            await scraper.run()
            logger.info(f"Scraper {args.scraper} completed successfully")

    except (ImportError, ValueError) as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Scraper failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
