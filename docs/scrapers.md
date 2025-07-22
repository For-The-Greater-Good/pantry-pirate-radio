# Scraper Implementation Guide

This document provides a comprehensive guide to implementing scrapers for the Pantry Pirate Radio system. It covers the scraper lifecycle, available utilities, and best practices.

## Table of Contents

- [Scraper Implementation Guide](#scraper-implementation-guide)
  - [Table of Contents](#table-of-contents)
  - [Scraper Lifecycle](#scraper-lifecycle)
  - [Scraper Base Class](#scraper-base-class)
  - [Utility Classes and Functions](#utility-classes-and-functions)
    - [Helper Functions](#helper-functions)
    - [Metrics](#metrics)
    - [ScraperUtils](#scraperutils)
    - [GeocoderUtils](#geocoderutils)
  - [Implementing a New Scraper](#implementing-a-new-scraper)
  - [Running Scrapers](#running-scrapers)
  - [Best Practices](#best-practices)
    - [General](#general)
    - [Geocoding](#geocoding)
    - [Data Processing](#data-processing)
    - [Queue Management](#queue-management)
  - [Testing Scrapers](#testing-scrapers)
    - [Test Mode](#test-mode)
    - [Running Tests](#running-tests)
    - [Test Results](#test-results)

## Scraper Lifecycle

The scraper lifecycle consists of the following steps:

1. **Initialization**: The scraper is instantiated with a unique ID.
2. **Data Collection**: The scraper downloads and processes data from its source.
3. **Data Enrichment**: The scraper enriches the data with additional information (e.g., geocoding addresses).
4. **Job Submission**: The scraper submits each processed item to the queue for further processing.
5. **Summary**: The scraper generates a summary of its operation.

This lifecycle is managed by the `ScraperJob` base class, which provides the `run()` method that orchestrates the process. Subclasses only need to implement the `scrape()` method to define their specific data collection logic.

## Scraper Base Class

All scrapers should inherit from the `ScraperJob` base class, which provides common functionality:

```python
from app.scraper.utils import ScraperJob

class MyCustomScraper(ScraperJob):
    def __init__(self, scraper_id: str = "my_custom_scraper") -> None:
        super().__init__(scraper_id=scraper_id)
        self.url = "https://example.com/api/data"

    async def scrape(self) -> str:
        # Implement scraper-specific logic here
        # ...
        return json.dumps(result)
```

The `ScraperJob` base class provides:

- `self.utils`: An instance of `ScraperUtils` for queue management and grid generation
- `self.geocoder`: An instance of `GeocoderUtils` for geocoding addresses
- `self.submit_to_queue(content)`: Method to submit content to the processing queue
- `async def run()`: Method to orchestrate the scraping process

## Utility Classes and Functions

### Helper Functions

The `utils.py` file includes several helper functions:

```python
from app.scraper.utils import get_scraper_headers

# Get standard headers for scraper requests
headers = get_scraper_headers()
response = requests.get(url, headers=headers)
```

Key functions:

- `get_scraper_headers()`: Returns standard headers for scraper requests, including a browser-like User-Agent

### Metrics

The `utils.py` file also includes Prometheus metrics for monitoring:

- **SCRAPER_JOBS**: Counter for the total number of jobs submitted by each scraper

### ScraperUtils

The `ScraperUtils` class provides utilities for queue management and grid generation:

```python
from app.scraper.utils import ScraperUtils

# Create an instance
utils = ScraperUtils(scraper_id="my_scraper")

# Queue content for processing
job_id = utils.queue_for_processing(content, metadata={"source": "my_source"})

# Get grid points for the continental US
points = utils.get_us_grid_points()

# Get grid points for a specific state
points = utils.get_state_grid_points("nj")  # New Jersey
```

Key methods:

- `queue_for_processing(content, metadata)`: Queue content for processing
- `get_us_grid_points()`: Get grid points covering the continental US
- `get_grid_points(bounds)`: Get grid points for a specific bounding box
- `get_state_grid_points(state_code)`: Get grid points for a US state
- `get_grid_points_from_geojson(geojson_path)`: Generate grid points from a GeoJSON file

### GeocoderUtils

The `GeocoderUtils` class provides utilities for geocoding addresses:

```python
from app.scraper.utils import GeocoderUtils

# Create an instance with default settings
geocoder = GeocoderUtils()

# Create an instance with custom settings
geocoder = GeocoderUtils(
    timeout=15,  # 15 seconds timeout
    min_delay_seconds=3,  # 3 seconds between requests
    max_retries=5,  # 5 retries for failed requests
    default_coordinates={
        "US": (39.8283, -98.5795),  # Geographic center of the United States
        "NJ": (40.0583, -74.4057),  # Geographic center of New Jersey
        "Mercer": (40.2206, -74.7597),  # Trenton, NJ (Mercer County seat)
    }
)

# Geocode an address
try:
    latitude, longitude = geocoder.geocode_address(
        address="123 Main St",
        county="Mercer",
        state="NJ"
    )
except ValueError as e:
    # Handle geocoding failure
    print(f"Geocoding failed: {e}")

    # Use default coordinates with random offset
    latitude, longitude = geocoder.get_default_coordinates(
        location="Mercer",  # Use "US", state code, or county name
        with_offset=True    # Add random offset to avoid stacking
    )
```

Key methods:

- `geocode_address(address, county, state)`: Geocode an address to get latitude and longitude
- `get_default_coordinates(location, with_offset, offset_range)`: Get default coordinates for a location with optional random offset

## Implementing a New Scraper

To implement a new scraper:

1. Create a new file in the `app/scraper` directory named `your_scraper_name_scraper.py`
2. Define a class that inherits from `ScraperJob`
3. Implement the `scrape()` method to define your scraper's logic
4. Optionally override the `__init__()` method to customize initialization

Example:

```python
"""Scraper for Example Data Source."""

import json
import logging
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Example_ScraperScraper(ScraperJob):
    """Scraper for Example Data Source."""

    def __init__(self, scraper_id: str = "example_scraper") -> None:
        """Initialize scraper with ID 'example_scraper' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'example_scraper'
        """
        super().__init__(scraper_id=scraper_id)
        self.url = "https://example.com/api/data"

        # Initialize geocoder with custom default coordinates
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "ExampleRegion": (40.7128, -74.0060),  # New York City
            }
        )

    async def download_data(self) -> str:
        """Download data from the source.

        Returns:
            str: Raw data content

        Raises:
            requests.RequestException: If download fails
        """
        logger.info(f"Downloading data from {self.url}")
        response = requests.get(self.url, headers=get_scraper_headers())
        response.raise_for_status()
        return response.text

    def process_data(self, data: str) -> List[Dict[str, Any]]:
        """Process the raw data.

        Args:
            data: Raw data content

        Returns:
            List of dictionaries containing processed data
        """
        # Implement data processing logic here
        # ...
        return processed_items

    async def scrape(self) -> str:
        """Scrape data from the source.

        Returns:
            Raw scraped content as JSON string
        """
        # Download data
        data = await self.download_data()

        # Process data
        items = self.process_data(data)

        # Submit each item to the queue
        job_count = 0
        for item in items:
            # Enrich item with additional data if needed
            # ...

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(item))
            job_count += 1
            logger.info(f"Queued job {job_id} for item: {item['name']}")

        # Create summary
        summary = {
            "total_items_found": len(items),
            "total_jobs_created": job_count,
            "source": self.url
        }

        # Print summary to CLI
        print(f"\nScraper Summary:")
        print(f"Source: {self.url}")
        print(f"Total items found: {len(items)}")
        print(f"Total jobs created: {job_count}")
        print(f"Status: Complete\n")

        # Return original content for archiving
        return json.dumps(summary)
```

## Running Scrapers

Scrapers can be run using the `app.scraper` module:

```bash
# List available scrapers
python -m app.scraper --list

# Run a specific scraper
python -m app.scraper my_scraper

# Run all available scrapers
python -m app.scraper --all

# Run all scrapers in parallel (faster)
python -m app.scraper --all --parallel --max-workers 4
```

The module will:

1. Dynamically load the scraper class(es) based on the name(s)
2. Instantiate the scraper(s)
3. Call the `run()` method to execute the scraper(s)
4. Handle any exceptions that occur during execution
5. When running in parallel mode, provide a summary of results

Example output when running in parallel mode:

```
Scraper Run Results:
====================
nyc_efap_programs: ✅ SUCCESS (5.67s)
food_helpline_org: ✅ SUCCESS (3.21s)
sample: ❌ FAILED (0.45s)
  Error: Failed to connect to API: Connection refused

Summary:
  Total: 3
  Successful: 2
  Failed: 1
```

## Best Practices

### General

- Use descriptive variable names and add comments to explain complex logic
- Follow the single responsibility principle - each method should do one thing
- Add comprehensive error handling to ensure robustness
- Log important events and errors for debugging
- Include a summary of the scraper's operation for monitoring

### Geocoding

- Always provide custom default coordinates for your specific region
- Handle geocoding failures gracefully with appropriate fallbacks
- Use random offsets for default coordinates to avoid stacking
- Consider the rate limits of geocoding services and adjust delay accordingly
- Add retry logic for temporary failures

### Data Processing

- Validate data before processing to ensure it meets expectations
- Handle missing or malformed data gracefully
- Use appropriate data structures for efficient processing
- Consider memory usage for large datasets
- Add progress reporting for long-running operations

### Queue Management

- Submit items to the queue as they are processed, not all at once
- Include metadata with each submission for tracking
- Monitor queue size and adjust batch size accordingly
- Handle queue submission failures gracefully

## Testing Scrapers

The system includes a utility for testing scrapers without submitting jobs to the queue. This is useful for verifying that scrapers can still successfully scrape data from their sources, even as external websites and APIs change over time.

### Test Mode

When running scrapers in test mode:

1. The scraper makes live calls to external sources
2. It scrapes the minimal amount of data needed to verify functionality
3. It does not submit any jobs to the processing queue
4. It reports success or failure of the scraping operation

This allows for regular testing of scrapers to detect if external changes break our functionality, without generating unnecessary processing jobs.

```python
from tests.test_scraper.utilities.test_utils import test_scraper

# Test a specific scraper
results = await test_scraper("nyc_efap_programs")
print(f"Test {'passed' if results['success'] else 'failed'}")
```

### Running Tests

Tests can be run using the `tests.test_scraper.utilities.test_scrapers` module:

```bash
# Test a specific scraper
python -m tests.test_scraper.utilities.test_scrapers nyc_efap_programs

# Test all available scrapers
python -m tests.test_scraper.utilities.test_scrapers --all

# Test all scrapers in parallel (faster)
python -m tests.test_scraper.utilities.test_scrapers --all --parallel --max-workers 4

# Save test results to a file
python -m tests.test_scraper.utilities.test_scrapers --all --output outputs/scraper_tests.json
```

The module will:

1. Load the specified scraper(s)
2. Run them in test mode (making live calls but not submitting jobs)
3. Report success or failure for each scraper
4. Provide a summary of test results
5. Optionally save detailed results to a JSON file

### Test Results

Test results include:

- Success/failure status for each scraper
- Duration of each test
- Error messages for failed tests
- Summary statistics (total, passed, failed)

Example output:

```
Scraper Test Results:
=====================
nyc_efap_programs: ✅ PASS (2.34s)
food_helpline_org: ✅ PASS (1.87s)
sample: ❌ FAIL (0.45s)
  Error: Failed to connect to API: Connection refused

Summary:
  Total: 3
  Passed: 2
  Failed: 1
```

This testing utility can be integrated into CI/CD pipelines to regularly verify scraper functionality and detect issues early.
