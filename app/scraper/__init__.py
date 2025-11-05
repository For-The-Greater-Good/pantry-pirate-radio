"""Food scraper framework.

This module provides the base classes and utilities for creating web scrapers
that collect food assistance location data.

Public API:
- ScraperJob: Base class for all scrapers
- ScraperUtils: Utilities for queuing jobs and generating grid points
- GeocoderUtils: Utilities for geocoding addresses
- get_scraper_headers: Get standard HTTP headers for scraping
"""

from app.scraper.utils import (
    ScraperJob,
    ScraperUtils,
    GeocoderUtils,
    get_scraper_headers,
    SCRAPER_JOBS,
    JobMetadata,
)

from app.scraper.__main__ import (
    load_scraper_class,
    list_available_scrapers,
    run_scraper_parallel,
    run_all_scrapers_parallel,
)

__all__ = [
    # Base classes and utilities
    "ScraperJob",
    "ScraperUtils",
    "GeocoderUtils",
    "get_scraper_headers",
    "SCRAPER_JOBS",
    "JobMetadata",
    # Scraper discovery and execution
    "load_scraper_class",
    "list_available_scrapers",
    "run_scraper_parallel",
    "run_all_scrapers_parallel",
]
