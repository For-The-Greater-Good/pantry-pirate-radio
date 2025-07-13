# Plentiful Scraper

## Overview

The Plentiful scraper collects food pantry and resource data from the Plentiful platform API. Plentiful is a comprehensive food security platform that connects people with food pantries, soup kitchens, and other food assistance programs across the United States.

## Data Source

- **Base URL**: `https://pantry.plentifulapp.com/api/3.0`
- **Primary Endpoint**: `/map/locations` - Returns locations within a bounding box
- **Details Endpoint**: `/map/location/{id}` - Returns detailed information for a specific location
- **Coverage**: Continental United States
- **Data Type**: JSON API responses

## API Endpoints

### Locations Endpoint
```
GET /map/locations?lat1={lat1}&lng1={lng1}&lat2={lat2}&lng2={lng2}&program_type={types}&status={status}&pantry_type={pantry_types}&service_type={service_types}
```

**Parameters:**
- `lat1`, `lng1`: Northwest corner of bounding box
- `lat2`, `lng2`: Southeast corner of bounding box
- `program_type`: `non-food,foodpantry,soupkitchen`
- `status`: `opennow,opentoday,openthisweek,other`
- `pantry_type`: `plentifulpantry,verifiedpartnerpantry,unverifiedpartnerpantry`
- `service_type`: `line,reservation,pre-registration,qr-code`

### Location Details Endpoint
```
GET /map/location/{id}
```

Returns detailed information for a specific location including:
- Comprehensive appointment schedules
- Service conditions and restrictions
- Amenities and special features
- Kosher designation
- Detailed operational constraints

## Data Structure

### Basic Location Data
```json
{
  "id": 1081,
  "name": "Food Bank Location",
  "address": "123 Main St",
  "city": "New York",
  "state": "NY",
  "zip_code": "10001",
  "latitude": 40.7128,
  "longitude": -74.0060,
  "phone": "555-123-4567",
  "website": "https://example.com",
  "organization_id": 123,
  "pantry_id": 456,
  "service_type": "line",
  "has_appointments": true,
  "week_days": [...]
}
```

### Detailed Location Data
```json
{
  "amenities": ["Distributes food based on household size"],
  "conditions": ["1 Visit per Calendar Week", "Registrations accepted 1 Hour in advance"],
  "service_hours": [...],
  "description": "Food pantry description",
  "kosher": true
}
```

## Scraping Strategy

### Grid-Based Approach
The scraper uses a grid-based approach to ensure comprehensive coverage:

1. **Grid Points**: Uses `ScraperUtils.get_us_grid_points()` to generate overlapping grid points across the continental US
2. **Bounding Boxes**: Creates 25-mile radius bounding boxes around each grid point
3. **Deduplication**: Tracks seen location IDs across all queries to prevent duplicates
4. **Rate Limiting**: Implements delays between requests to respect API limits

### API Limits Handling
- **1k Result Limit**: The API has a ~1000 result limit per query
- **Small Search Areas**: Uses 25-mile radius searches to stay under the limit
- **Limit Detection**: Warns when queries return ≥1000 results (potential limit hit)
- **Comprehensive Coverage**: Overlapping grid ensures no locations are missed

### Two-Phase Data Collection
1. **Phase 1**: Bulk location collection using the locations endpoint
2. **Phase 2**: Detailed information fetching for each location using the details endpoint

## Data Processing

### Location Data Enhancement
- Combines basic location data with detailed information
- Adds source tracking and metadata
- Handles cases where detailed data fetch fails gracefully
- Preserves all original fields for HSDS alignment

### Geocoding
- Uses existing latitude/longitude from API (no additional geocoding needed)
- All locations come with precise coordinates from Plentiful's system

## Error Handling

### Network Errors
- Handles HTTP timeouts and connection errors
- Continues processing other locations if individual requests fail
- Logs detailed error information for debugging

### Data Validation
- Validates location IDs before processing
- Handles missing or malformed data gracefully
- Tracks failed detail fetches separately from successful processing

### Rate Limiting
- Implements configurable delays between requests
- Adds pauses between grid point batches
- Respects API rate limits to avoid blocking

## Output Format

The scraper produces structured JSON output suitable for HSDS alignment:

```json
{
  "id": 1081,
  "name": "Food Bank Location",
  "address": "123 Main St",
  "city": "New York",
  "state": "NY",
  "zip_code": "10001",
  "latitude": 40.7128,
  "longitude": -74.0060,
  "phone": "555-123-4567",
  "website": "https://example.com",
  "organization_id": 123,
  "pantry_id": 456,
  "service_type": "line",
  "has_appointments": true,
  "week_days": [...],
  "amenities": [...],
  "conditions": [...],
  "service_hours": [...],
  "source": "plentiful",
  "source_id": "1081",
  "details_fetched": true
}
```

## Configuration

### Scraper Settings
- **Batch Size**: 10 grid points per batch (5 in test mode)
- **Request Delay**: 500ms between requests (100ms in test mode)
- **Detail Request Delay**: 200ms between location detail fetches
- **Batch Delay**: 2 seconds between grid point batches
- **Timeout**: 30 seconds for HTTP requests
- **Search Radius**: 25 miles (0.36 degrees lat/lng)

### Rate Limiting
- **Request rate limit**: 60 requests per minute maximum
- **Individual request delay**: 500ms (100ms in test mode)
- **Detail request delay**: 200ms between location detail fetches
- **Batch processing delay**: 2 seconds between grid point batches
- **Automatic throttling**: Tracks request timestamps and enforces rate limits
- **Smaller batch sizes**: 10 grid points per batch (5 in test mode)
- Respects API rate limits and fair use policies

## Usage

### Run the Scraper
```bash
# Run Plentiful scraper
python -m app.scraper plentiful

# Run with other scrapers
python -m app.scraper --all

# Test the scraper
python -m app.scraper.test_scrapers plentiful
```

### Example Output
```
Plentiful Scraper Summary:
Source: https://pantry.plentifulapp.com/api/3.0
Grid points processed: 1247
Total locations found: 3456
Successfully processed: 3456
Failed detail fetches: 23
⚠️  Queries that may have hit 1k limit: 2
Status: Complete
```

## Data Quality

### Strengths
- **High Accuracy**: Professional platform with verified data
- **Comprehensive Details**: Rich information including schedules and conditions
- **Real-time Status**: Current operational status and hours
- **Geographic Precision**: Accurate coordinates for all locations
- **Service Details**: Specific information about appointment requirements

### Limitations
- **API Limits**: 1k result limit per query may miss some locations in dense areas
- **Coverage Gaps**: May not include all independent food pantries
- **Platform Dependence**: Limited to organizations using Plentiful platform

## Monitoring

### Key Metrics
- Total locations found vs. expected coverage
- Queries hitting the 1k result limit
- Failed detail fetches ratio
- Processing time per grid point
- Network error rates

### Alerts
- High failure rate for detail fetches
- Multiple queries hitting 1k limit (indicates dense areas needing smaller searches)
- Significant changes in total location count

## Maintenance

### Regular Tasks
- Monitor API changes and endpoint updates
- Verify grid coverage remains comprehensive
- Adjust search radius if 1k limit is frequently hit
- Update parameter values if API adds new options

### Troubleshooting
- Check API endpoint availability
- Verify bounding box calculations
- Review rate limiting configuration
- Validate deduplication logic