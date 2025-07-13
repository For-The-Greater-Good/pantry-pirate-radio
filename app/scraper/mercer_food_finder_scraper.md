# Mercer Food Finder Scraper

This document explains the functionality and implementation details of the Mercer Food Finder scraper, which extracts food pantry information from the Mercer County Free Food Finder website.

## Overview

The `Mercer_Food_FinderScraper` is designed to:

1. Download HTML content from the Mercer County Free Food Finder website
2. Parse the HTML to extract food pantry information
3. Geocode addresses using multiple geocoding services to obtain latitude/longitude coordinates
4. Submit each food pantry as a separate job to the processing queue
5. Track and report geocoding statistics and failures

## Data Source

The scraper targets the following URL:
```
https://mercerfoodfinder.herokuapp.com/api/pdf
```

Despite the "pdf" in the URL, this endpoint returns HTML content containing a table of food pantry information.

## Extracted Data

For each food pantry, the scraper extracts:

- **Name**: The name of the food pantry or organization
- **Address**: The physical address of the pantry
- **Phone**: Contact phone number
- **Description**: Information about hours, services, and other details
- **Coordinates**: Latitude and longitude (obtained through geocoding)
- **Geocoder**: Which geocoding service was used (nominatim, arcgis, or default)

## Geocoding Strategy

The scraper uses the `GeocoderUtils` class from `utils.py` to implement a robust multi-geocoder approach:

1. **Shared Geocoding Utilities**: Uses the centralized `GeocoderUtils` class that can be reused by other scrapers
2. **Multiple Geocoders**: Leverages both Nominatim (OpenStreetMap) and ArcGIS geocoding services in sequence
3. **Address Variations**: Tries multiple variations of each address:
   - Full address with county and state
   - Address with just state
   - Original address as provided
   - For addresses with landmarks (e.g., "parking lot" or "across from"), attempts to extract and geocode just the street address

4. **Fallback Mechanism**: If all geocoding attempts fail, uses default coordinates for Mercer County with a small random offset to avoid stacking all failed geocodes at the same point

## Error Handling

The scraper includes comprehensive error handling:

1. **Geocoding Failures**: Logs detailed error information and saves failed pantries to a JSON file for later review
2. **Rate Limiting**: Uses RateLimiter to avoid being blocked by geocoding services
3. **Timeout Handling**: Sets appropriate timeouts for geocoding requests
4. **Retry Logic**: Includes retry logic for temporary failures

## Statistics Tracking

The scraper tracks and reports:

1. **Total pantries found**: Number of pantries extracted from the HTML
2. **Successfully geocoded**: Number of pantries successfully processed and queued
3. **Geocoder usage**: Breakdown of which geocoder was used for each address
4. **Failed geocoding**: Number of pantries that couldn't be geocoded

## Implementation Details

### Dependencies

- **BeautifulSoup4**: For HTML parsing
- **Geopy**: For geocoding (Nominatim and ArcGIS)
- **Requests**: For HTTP requests

### Key Methods

1. **download_html()**: Downloads the HTML content from the website
2. **parse_html()**: Extracts food pantry information from the HTML
3. **scrape()**: Orchestrates the entire scraping process, using the `GeocoderUtils` class for geocoding

### Geocoding Services

1. **Nominatim**: Primary geocoder (OpenStreetMap-based)
   - Pros: Free, open-source
   - Cons: Stricter rate limits, sometimes less accurate for unusual addresses

2. **ArcGIS**: Secondary geocoder
   - Pros: Often better at handling unusual addresses
   - Cons: May have usage limitations

## Usage

To run the scraper:

```bash
python -m app.scraper mercer_food_finder
```

## Output

The scraper outputs:

1. **Queue Jobs**: Each food pantry is submitted to the processing queue
2. **Summary**: Printed to the console with statistics about the scraping process
3. **Failed Pantries**: Saved to a JSON file in the outputs directory for later review

## Future Improvements

Potential enhancements for the scraper:

1. **Additional Geocoders**: Add support for more geocoding services like Google Maps (requires API key)
2. **Address Preprocessing**: Implement more sophisticated address parsing and normalization
3. **Caching**: Add geocoding result caching to avoid redundant lookups
4. **Parallel Processing**: Implement parallel geocoding to improve performance
5. **Manual Coordinates**: Support for manually specifying coordinates for known problematic addresses
