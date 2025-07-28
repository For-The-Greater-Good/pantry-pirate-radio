# FreshTrak/PantryTrak API Scraper

This scraper pulls food pantry and agency data from the FreshTrak/PantryTrak public API using comprehensive search methods.

## Data Source

- **Source**: FreshTrak/PantryTrak API
- **URL**: https://pantry-finder-api.freshtrak.com
- **API Endpoint**: `/api/agencies`
- **Documentation**: Ruby on Jets API serving food pantry locations

## Coverage

The scraper provides comprehensive coverage of Ohio using two search methods:

### Method 1: Zip Code Search
- **280+ Ohio zip codes** covering all major metropolitan areas:
  - Columbus Metropolitan Area (32+ zip codes)
  - Cleveland Metropolitan Area (49+ zip codes)
  - Cincinnati Metropolitan Area (100+ zip codes)
  - Dayton Area (52+ zip codes)
  - Toledo Area (40+ zip codes)
  - Akron Area (25+ zip codes)
  - Youngstown Area (16+ zip codes)
  - Canton Area (20+ zip codes)

### Method 2: Grid Coordinate Search
- **Systematic grid search** across Ohio state boundaries
- Uses the same grid generation system as other comprehensive scrapers
- 50-mile search radius for each coordinate point
- Overlapping coverage ensures no areas are missed

## API Parameters

The scraper uses the following API parameters:

### Zip Code Search
- `zip_code`: Zip code to search for agencies

### Coordinate Search
- `lat`: Latitude coordinate
- `long`: Longitude coordinate
- `distance`: Search radius in miles (set to 50)

## Data Structure

Each agency record includes:

### Agency Information
- `id`: Unique agency identifier
- `name`: Full agency name
- `nickname`: Display name
- `address`: Street address
- `city`: City name
- `state`: State abbreviation
- `zip`: ZIP code
- `phone`: Contact phone number
- `latitude`/`longitude`: Geographic coordinates
- `estimated_distance`: Distance from search center

### Event Information
Each agency can have multiple events (food distribution events):
- `id`: Event identifier
- `name`: Event name (e.g., "Pantry")
- `address`: Event location (may differ from agency)
- `city`/`state`/`zip`: Event location
- `latitude`/`longitude`: Event coordinates
- `event_details`: Description of the event
- `event_dates`: Array of scheduled dates with times
- `service_category`: Type of service provided

## Usage

```bash
# Run the FreshTrak scraper
python -m app.scraper freshtrak

# Test the scraper
python -m app.scraper.test_scrapers freshtrak
```

## Rate Limiting

The scraper respects API rate limits by:
- Processing zip codes sequentially
- Using standard scraper headers
- Implementing error handling for failed requests

## Error Handling

- Continues processing other zip codes if one fails
- Logs errors for debugging
- Returns empty results gracefully for zip codes with no data

## Data Quality

- Strips whitespace from text fields
- Converts coordinates to float values
- Handles missing or null values gracefully
- Preserves original API structure while cleaning data

## Notes

- The API appears to be primarily focused on Ohio food pantries
- Each agency can have multiple events with different locations
- Event dates include capacity, times, and registration options
- The API supports distance-based searches but the scraper uses zip code searches for comprehensive coverage