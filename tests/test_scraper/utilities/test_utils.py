"""Utilities for testing scrapers without submitting jobs."""

import importlib
import logging
import time
from pathlib import Path

from app.scraper.utils import ScraperJob

logger = logging.getLogger(__name__)


class TestScraperJob(ScraperJob):
    """Wrapper for testing scrapers without submitting jobs."""

    def __init__(self, scraper: ScraperJob) -> None:
        """Initialize test wrapper around a scraper.

        Args:
            scraper: The scraper instance to test
        """
        self.scraper = scraper
        self.scraper_id = scraper.scraper_id
        self.test_results = {
            "success": False,
            "error": None,
            "duration": 0,
            "timestamp": time.time(),
        }

    def submit_to_queue(self, content: str) -> str:
        """Override queue submission to prevent actual job creation.

        Args:
            content: Content that would be submitted

        Returns:
            Fake job ID
        """
        logger.info(f"[TEST MODE] Would submit job for {self.scraper_id}")
        return f"test-{self.scraper_id}-{time.time()}"

    async def run_test(self) -> dict:
        """Run the scraper in test mode.

        Returns:
            Test results dictionary
        """
        start_time = time.time()
        try:
            # Replace the scraper's submit_to_queue with our version
            original_submit = self.scraper.submit_to_queue
            self.scraper.submit_to_queue = self.submit_to_queue

            # Run the scraper
            content = await self.scraper.scrape()

            # Restore original method
            self.scraper.submit_to_queue = original_submit

            # Record success
            self.test_results["success"] = True

        except Exception as e:
            logger.error(f"Scraper {self.scraper_id} test failed: {e}")
            self.test_results["success"] = False
            self.test_results["error"] = str(e)
        finally:
            # Record duration
            self.test_results["duration"] = time.time() - start_time

        return self.test_results


async def run_scraper_test(scraper_name: str) -> dict:
    """Run a test for a specific scraper.

    Args:
        scraper_name: Name of the scraper to test

    Returns:
        Test results dictionary
    """
    try:
        # Convert name to proper class name (e.g. 'sample' -> 'SampleScraper')
        class_name = f"{scraper_name.title()}Scraper"

        # Import the scraper module
        module = importlib.import_module(f"app.scraper.{scraper_name}_scraper")
        scraper_class = getattr(module, class_name)

        # Create scraper instance
        scraper = scraper_class(scraper_id=scraper_name)

        # Create test wrapper
        test_wrapper = TestScraperJob(scraper)

        # Run test
        return await test_wrapper.run_test()

    except Exception as e:
        logger.error(f"Failed to test scraper {scraper_name}: {e}")
        return {
            "scraper": scraper_name,
            "success": False,
            "error": str(e),
            "duration": 0,
            "timestamp": time.time(),
        }


async def run_all_scraper_tests() -> dict[str, dict]:
    """Run tests for all available scrapers.

    Returns:
        Dictionary of test results by scraper name
    """
    results = {}

    # Get list of available scrapers
    scraper_dir = Path(__file__).parent
    scrapers = []

    for file in scraper_dir.glob("*_scraper.py"):
        name = file.stem.replace("_scraper", "")
        if name != "__init__":  # Skip __init__.py
            scrapers.append(name)

    # Test each scraper
    for scraper_name in scrapers:
        logger.info(f"Testing scraper: {scraper_name}")
        results[scraper_name] = await run_scraper_test(scraper_name)

    return results
