# Sample Scraper

This document explains the functionality and implementation details of the Sample Scraper, which processes GeoJSON data from thefoodpantries.org.

## Overview

The `SampleScraper` is designed to:

1. Read GeoJSON data from a file
2. Process features from the GeoJSON collection
3. Submit each feature (food pantry location) as a separate job to the processing queue

This scraper serves as a simple example of how to implement a scraper in the Pantry Pirate Radio system.

## Data Source

The scraper reads GeoJSON data from a file, which by default is located at:
```
tests/test_data.json
```

Alternatively, a test file can be specified using the `set_test_file()` method.

## Extracted Data

For each feature in the GeoJSON collection, the scraper extracts:

- **Properties**: The properties of the feature, which typically include information about the food pantry
- **Collection Metadata**: The name and category of the collection, which are added to the properties

## Implementation Details

### Dependencies

- **json**: For parsing GeoJSON data
- **pathlib**: For file path handling

### Key Methods

1. **set_test_file()**: Sets a custom test file path for testing
2. **run()**: Orchestrates the scraping process, overriding the base class method
3. **scrape()**: Implements the required scrape method but defers processing to run()

### Processing Flow

1. The scraper reads the GeoJSON file
2. It extracts the first collection from the data
3. For each feature in the collection:
   - It extracts the properties
   - It enriches the properties with collection metadata
   - It submits the properties to the queue for processing

## Usage

To run the scraper:

```bash
python -m app.scraper sample
```

## Output

The scraper outputs:

1. **Queue Jobs**: Each feature is submitted to the processing queue
2. **Logs**: Information about each queued job is logged

