# Vivery API Scraper

This document explains the functionality and implementation details of the Vivery API Scraper, which extracts food pantry information from the Vivery API.

## Overview

The `Vivery_ApiScraper` is designed to:

1. Generate a grid of coordinates covering the continental US
2. Search for food pantry locations at each coordinate point
3. Fetch additional data for each location (schedules, services, special hours)
4. Process and enrich the data
5. Submit each location as a separate job to the processing queue

## Data Source

The scraper targets the Vivery API at:
```
https://api.accessfood.org/api
```

It uses several API endpoints:
- `/MapInformation/LocationSearch`: To search for locations at specific coordinates
- `/MapInformation/LocationServiceSchedules`: To fetch schedule information
- `/MapInformation/LocationServices`: To fetch service information
- `/MapInformation/MultipleLocations_LocationSpecialHoursByFirstPage`: To fetch special hours information

## Extracted Data

For each location, the scraper extracts comprehensive information:

- **Basic Information**: Name, address, contact details, etc.
- **Geographic Information**: Latitude, longitude, service areas
- **Operational Information**: Schedules, special hours
- **Service Information**: Food programs, service types, dietary restrictions
- **Additional Information**: Languages, features, network affiliations, etc.

## Implementation Details

### Dependencies

- **httpx**: For asynchronous HTTP requests
- **asyncio**: For asynchronous processing and parallel requests
- **json**: For parsing API responses
- **re**: For cleaning HTML tags from text fields

### Key Methods

1. **search_locations()**: Searches for locations at specific coordinates
2. **fetch_additional_data()**: Fetches additional data for locations
3. **format_schedule()**: Formats schedule data into a readable string
4. **format_service()**: Formats service data into a structured dictionary
5. **process_batch()**: Processes a batch of coordinates
6. **scrape()**: Orchestrates the entire scraping process

### Processing Flow

1. The scraper generates a grid of coordinates covering the continental US
2. It processes these coordinates in batches to avoid overwhelming the API
3. For each coordinate:
   - It searches for locations within a radius
   - It fetches additional data for each location
   - It processes and enriches the data
   - It stores the data for later submission
4. After processing all coordinates, it submits each unique location to the queue

## Optimization Techniques

The scraper includes several optimization techniques:

1. **Batch Processing**: Processes coordinates in batches to manage memory usage
2. **Parallel Requests**: Fetches additional data in parallel using asyncio.gather
3. **Rate Limiting**: Includes a delay between requests to avoid overwhelming the API
4. **Deduplication**: Tracks unique locations to avoid submitting duplicates
5. **Progress Reporting**: Reports progress during the scraping process

## Usage

To run the scraper:

```bash
python -m app.scraper vivery_api
```

## Output

The scraper outputs:

1. **Queue Jobs**: Each unique location is submitted to the processing queue
2. **Summary**: Printed to the console with statistics about the scraping process
3. **Logs**: Detailed logs of the scraping process, including progress updates
