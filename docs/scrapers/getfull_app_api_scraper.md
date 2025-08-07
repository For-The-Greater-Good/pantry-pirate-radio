# GetFull.app API Scraper

## Overview

The GetFull.app API scraper extracts food pantry information from the GetFull.app platform, which provides a comprehensive database of food pantries across the United States. This pure API-based implementation is much faster and more efficient than browser automation.

## Data Source

- **Organization**: GetFull.app
- **Website**: https://getfull.app/food-finder
- **API Type**: REST API with Elasticsearch backend
- **API Endpoint(s)**: 
  - Primary: `https://api.getfull.app/es/search/geo/pantries`
  - Session: `https://api.getfull.app/auth-api/session`
  - Anonymous Auth: `https://api.getfull.app/auth-api/anonymous`
- **Documentation**: No official documentation (reverse-engineered)

## Coverage Area

Geographic regions covered by this scraper:
- **States**: All 50 US states
- **Coverage**: Continental United States
- **Search Method**: Grid-based geographic search with overlapping circles
- **Search Parameters**: 
  - Default radius: 50 miles per search point
  - Overlap factor: 30% for comprehensive coverage
  - Grid spacing: Calculated based on radius and overlap

## Technical Implementation

### Scraper Class
- **Class Name**: `Getfull_App_ApiScraper`
- **Base Class**: `ScraperJob`
- **Module Path**: `app.scraper.getfull_app_api_scraper`

### Key Configuration
```python
# Configuration parameters
DEFAULT_SEARCH_RADIUS_MILES = 50.0  # Search radius per point
DEFAULT_OVERLAP_FACTOR = 0.30  # 30% overlap between search circles
DEFAULT_REQUEST_DELAY = 0.05  # 50ms between requests
REQUEST_TIMEOUT = 30  # Request timeout in seconds
EARTH_RADIUS_MILES = 69.0  # Approximate miles per degree latitude
```

### Dependencies
- **Required Libraries**: httpx, asyncio, json, math
- **External Services**: GetFull.app API
- **Rate Limiting**: 50ms delay between requests

## Implementation Details

### Authentication

The GetFull.app API uses anonymous authentication for public access:
1. Creates a session via `/auth-api/session`
2. Authenticates anonymously via `/auth-api/anonymous`
3. Uses the returned bearer token for subsequent API calls
4. Token provides read-only access to pantry data

## Data Structure

### Input Parameters
The geo search API accepts:
- `lat`: Latitude coordinate
- `lng`: Longitude coordinate  
- `distance`: Search radius in miles
- `limit`: Maximum results (up to 1000)

### Output Format
Each pantry record includes:

```json
{
  "id": "Unique pantry identifier",
  "name": "Pantry name",
  "slug": "URL-friendly name",
  "address": "Street address",
  "city": "City name",
  "state": "State abbreviation",
  "zip": "ZIP code",
  "latitude": "Geographic latitude",
  "longitude": "Geographic longitude",
  "phone": "Contact phone",
  "email": "Contact email",
  "website": "Pantry website",
  "hours": "Operating hours",
  "services": ["List of services"],
  "description": "Pantry description",
  "lastUpdated": "Last update timestamp"
}
```

### Key Fields Extracted
- **id**: Unique pantry identifier
- **name**: Organization/pantry name
- **address**: Full street address
- **city**: City name
- **state**: State abbreviation
- **zip**: ZIP/postal code
- **latitude**: Geographic latitude
- **longitude**: Geographic longitude
- **phone**: Contact phone number
- **hours**: Operating hours (various formats)
- **services**: Array of services offered
- **website**: Pantry website URL
- **email**: Contact email
- **description**: Detailed description

### Data Collection Process

The API scraper uses an efficient geo search approach:

1. **Grid Generation**: Creates a systematic grid of search points across the continental US
2. **Overlapping Coverage**: 30% overlap between search circles ensures no gaps
3. **Batch Processing**: Processes coordinates in batches for efficiency
4. **Deduplication**: Tracks unique pantry IDs to avoid duplicates
5. **Progressive Results**: Can retrieve up to 1000 pantries per search location





## Usage

### Running the Scraper

```bash
# Run the scraper using bouy
./bouy scraper getfull_app_api

# Test mode (limited data)
./bouy scraper-test getfull_app_api

# Run with verbose output
./bouy --verbose scraper getfull_app_api
```

### Testing

```bash
# Run specific tests for this scraper
./bouy test --pytest tests/test_scraper/test_getfull_app_api_scraper.py

# Run with coverage
./bouy test --coverage -- tests/test_scraper/test_getfull_app_api_scraper.py
```

## Error Handling

- **Network Errors**: Catches httpx exceptions and logs errors
- **Authentication Failures**: Attempts anonymous auth, fails gracefully if unable
- **Rate Limiting**: 50ms delay between requests to avoid rate limits
- **Invalid Data**: Handles various data formats for hours and services
- **Retry Logic**: No automatic retry; processes available data and continues

## Performance Considerations

- **Average Runtime**: 5-10 minutes for continental US coverage
- **Data Volume**: Typically 5,000-10,000 unique pantries
- **Memory Usage**: Tracks unique pantry IDs in memory
- **Optimization**: 
  - Grid-based search with calculated overlap
  - Batch processing of coordinates
  - Deduplication to avoid reprocessing

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - **Symptoms**: 401 Unauthorized errors
   - **Cause**: API authentication mechanism changed
   - **Solution**: Check if anonymous auth endpoint still works; may need to update auth flow

2. **No Results Returned**
   - **Symptoms**: Search returns empty results
   - **Cause**: API endpoint or parameters changed
   - **Solution**: Verify API endpoints are still accessible; check for API changes

3. **Incomplete Data**
   - **Symptoms**: Missing hours or services information
   - **Cause**: Data format variations in API responses
   - **Solution**: Already handled by robust parsing; check for new formats

### Debug Commands

```bash
# Run with debug logging
./bouy --verbose scraper getfull_app_api

# Check scraper logs
./bouy logs app | grep getfull_app_api

# Test API authentication
./bouy exec app python -c "import httpx; resp = httpx.get('https://api.getfull.app/auth-api/session'); print(resp.status_code)"
```

## Maintenance Notes

- **Last Updated**: 2025-08-07
- **Update Frequency**: Check monthly for API changes
- **Known Limitations**: 
  - Authentication mechanism may change without notice
  - API response format not documented
  - Limited to 1000 results per search location
  - Some pantries may have incomplete data
- **Future Improvements**: 
  - Implement retry logic for failed requests
  - Add support for pantry details endpoint
  - Optimize grid generation for population density

## Related Documentation

- [GetFull.app Website](https://getfull.app/)
- [ScraperJob Base Class](../utilities/scraper_job.md)
- [Grid Generation Utilities](../utilities/grid_utils.md)
