# GetFull.app Browser Scraper

This document provides an overview of the GetFull.app browser scraper implementation for the Pantry Pirate Radio system.

## Overview

The GetFull.app browser scraper extracts food pantry information from the [GetFull.app](https://getfull.app/food-finder) website. This website provides a map-based interface for finding food pantries across the United States.

## Implementation Details

### Authentication

The GetFull.app website requires authentication to access its API. The browser scraper uses multiple approaches to obtain an authentication token:
1. Capturing network requests during page navigation
2. Extracting tokens from localStorage or sessionStorage
3. Using CDP (Chrome DevTools Protocol) to monitor network traffic
4. Falling back to an anonymous token if necessary

### Data Collection Process (Updated)

The browser scraper now uses a more efficient geo search API approach:

1. Initialize a headless browser using Playwright
2. Navigate to the GetFull.app food finder map page
3. Extract an authentication token using multiple approaches
4. Use the Elasticsearch geo search API endpoint (`/es/search/geo/pantries`) to search for pantries
5. Make targeted API calls to major metropolitan areas and rural regions across the US
6. For each search result:
   - Extract pantry information from the API response
   - Get additional details using the pantry details API if needed
   - Handle different data formats for hours and services
7. Transform the pantry data to HSDS format
8. Submit the data to the processing queue in batches

### Geo Search API Approach

The improved scraper uses the geo search API with the following strategy:

1. **Comprehensive Coverage**: 60+ search centers covering all major US metropolitan areas
2. **Variable Search Radius**: 30-100 mile radius depending on population density
3. **Overlapping Circles**: Ensures no pantries are missed between search areas
4. **Efficient API Usage**: Single API call per search center instead of thousands of grid points
5. **Better Results**: Can retrieve up to 1000 pantries per search location

### Grid Prioritization and Density

The browser scraper uses a sophisticated grid prioritization system to focus on populated areas first:

1. **Regional Prioritization**:
   - East Coast US (highest priority)
   - West Coast US (second priority)
   - Colorado (third priority)
   - Rest of the US (lowest priority)

2. **City Categorization**:
   - Major metropolitan areas (e.g., New York City, Los Angeles)
   - Secondary cities (e.g., Miami, San Diego)
   - Smaller cities & regional centers (e.g., Raleigh, Fresno)

3. **Variable Grid Density**:
   - High-density regions (major metropolitan areas): 0.01° grid spacing (≈1.1km) with zoom level 14
   - Standard regions: 0.1° grid spacing (≈7-11km) with zoom level 12
   - Each region uses a circular coverage pattern with configurable radius

This approach ensures comprehensive coverage while prioritizing areas with higher population density where food pantries are more likely to be located. The finer grid spacing in high-density regions allows for more thorough scanning in urban areas where food pantries are concentrated.

### Parallel Processing and Worker Distribution

The scraper uses multiple browser instances in parallel to speed up the data collection process:

1. **Geographic Distribution Strategy**:
   - Entire regions are assigned to individual workers when possible
   - Larger regions are split geographically to minimize overlap between workers
   - Workers process geographically contiguous areas to reduce duplicate pantry discoveries
   - Load balancing ensures each worker gets a roughly equal number of coordinates

2. **Shared State Management**:
   - Thread-safe tracking of processed pantry IDs across all workers
   - Global set of unique pantries for accurate progress reporting
   - Periodic progress updates showing coordinates processed and unique pantries found

3. **Batch Processing**:
   - Coordinates are processed in small batches
   - Pantries are submitted to the queue in batches
   - Duplicate detection prevents reprocessing the same pantry

This parallel approach significantly improves performance while minimizing redundant work and network traffic.

### Slug Extraction and API Requests

The browser scraper extracts the pantry slug from the "more info" button or links in the pantry card. It then tries multiple slug formats when making API requests:

1. Extracted slug from the pantry card (if available)
2. Generated slug from the pantry name (full, truncated, truncated at hyphen)
3. Special case handling for specific pantry types (e.g., "community-fridge")
4. Pantry ID as a fallback

This multi-pronged approach significantly improves the success rate of API requests for pantries with complex names or special cases.

### Data Structure and Handling

The browser scraper handles various data formats for hours and services:

1. **Hours/Schedule Data**:
   - List format (most common)
   - String format
   - Object format
   - Schedule field extraction
   - Special handling for closed pantries

2. **Services Data**:
   - List format (most common)
   - String format (with comma splitting)
   - Dictionary format
   - Additional service fields (e.g., serviceTypes)

This robust handling ensures that all pantries are processed correctly, regardless of their data format or status.

## HSDS Transformation

The scraper transforms the GetFull.app data into the Human Services Data Specification (HSDS) format, mapping fields as follows:

- `id` → `id`
- `name` → `name`
- `description` → `description`
- `email` → `email`
- `website` → `url`
- Address components → `address` object
- `phone` → `phones` array
- `latitude`/`longitude` → `location` object
- `hours` → `regular_schedule` array
- `services` → `service_attributes` array

## Technical Considerations

### Rate Limiting

To avoid overwhelming the GetFull.app API and potentially being rate-limited, the scraper:

1. Processes coordinates in small batches
2. Adds a delay between requests
3. Handles HTTP errors gracefully, including 401 (Unauthorized) errors that may indicate an expired token

### Browser Automation

The scraper uses Playwright for browser automation, which allows it to:

1. Navigate to the website
2. Interact with the search interface
3. Extract authentication tokens
4. Monitor network requests

### Error Handling

The scraper includes robust error handling to deal with:

1. Authentication failures
2. API request failures
3. Unexpected response formats
4. Network issues
5. Different data formats for hours and services

## Dependencies

- `playwright`: For browser automation
- `httpx`: For making HTTP requests
- `asyncio`: For asynchronous operations
- Standard libraries: `json`, `logging`, `random`, etc.

## Usage

To run the GetFull.app browser scraper:

```bash
python -m app.scraper getfull_app_browser
```

## Limitations

1. The authentication mechanism may change if the website is updated
2. The API response format may change without notice
3. The scraper may need to be updated if the website's structure changes
4. Processing all coordinates for the continental US may take a significant amount of time
5. Some pantries may not have detailed information available via the API
6. Closed pantries may have different data formats for hours and services
