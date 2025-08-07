# FreshTrak/PantryTrak API Scraper

## Overview

This scraper pulls food pantry and agency data from the FreshTrak/PantryTrak public API using comprehensive search methods including both zip code and coordinate-based searches.

## Data Source

- **Organization**: FreshTrak/PantryTrak (Mid-Ohio Food Collective)
- **Website**: https://freshtrak.com/
- **API Type**: REST API (Ruby on Jets)
- **API Endpoint(s)**: 
  - Primary: `https://pantry-finder-api.freshtrak.com/api/agencies`
- **Documentation**: No official documentation (public API)

## Coverage Area

Geographic regions covered by this scraper:
- **States**: Ohio (OH) - primary focus
- **Counties/Regions**: All Ohio counties with emphasis on:
  - Columbus Metropolitan Area (32+ zip codes)
  - Cleveland Metropolitan Area (49+ zip codes)
  - Cincinnati Metropolitan Area (100+ zip codes)
  - Dayton Area (52+ zip codes)
  - Toledo Area (40+ zip codes)
  - Akron Area (25+ zip codes)
  - Youngstown Area (16+ zip codes)
  - Canton Area (20+ zip codes)
- **Search Method**: Dual approach - Zip code search (280+ codes) and Grid coordinate search
- **Search Parameters**: 50-mile radius for coordinate searches

## Technical Implementation

### Scraper Class
- **Class Name**: `FreshtrakScraper`
- **Base Class**: `ScraperJob`
- **Module Path**: `app.scraper.freshtrak_scraper`

### Key Configuration
```python
# Configuration parameters
search_radius = 50  # Search radius in miles for coordinate searches
zip_codes = 280+  # Ohio zip codes for comprehensive coverage
```

### Dependencies
- **Required Libraries**: httpx, asyncio, json
- **External Services**: FreshTrak API
- **Rate Limiting**: Sequential processing with error handling


## Data Structure

### Input Parameters
The API accepts two types of searches:

**Zip Code Search:**
- `zip_code`: Zip code to search for agencies

**Coordinate Search:**
- `lat`: Latitude coordinate
- `long`: Longitude coordinate
- `distance`: Search radius in miles (set to 50)

### Output Format
Each agency record includes:

```json
{
  "id": "Unique agency identifier",
  "name": "Full agency name",
  "nickname": "Display name",
  "address": "Street address",
  "city": "City name",
  "state": "State abbreviation",
  "zip": "ZIP code",
  "phone": "Contact phone number",
  "latitude": "Geographic latitude",
  "longitude": "Geographic longitude",
  "estimated_distance": "Distance from search center",
  "events": [
    {
      "id": "Event identifier",
      "name": "Event name (e.g., Pantry)",
      "address": "Event location",
      "city": "Event city",
      "state": "Event state",
      "zip": "Event ZIP",
      "latitude": "Event latitude",
      "longitude": "Event longitude",
      "event_details": "Description",
      "event_dates": "Array of scheduled dates",
      "service_category": "Service type"
    }
  ]
}
```

### Key Fields Extracted
- **id**: Unique agency identifier
- **name**: Full agency name
- **nickname**: Display/short name
- **address**: Street address
- **city**: City name
- **state**: State abbreviation
- **zip**: ZIP code
- **phone**: Contact phone number
- **latitude**: Geographic latitude
- **longitude**: Geographic longitude
- **events**: Array of distribution events with schedules

## Usage

### Running the Scraper

```bash
# Run the scraper using bouy
./bouy scraper freshtrak

# Test mode (limited data)
./bouy scraper-test freshtrak

# Run with verbose output
./bouy --verbose scraper freshtrak
```

### Testing

```bash
# Run specific tests for this scraper
./bouy test --pytest tests/test_scraper/test_freshtrak_scraper.py

# Run with coverage
./bouy test --coverage -- tests/test_scraper/test_freshtrak_scraper.py
```


## Error Handling

- **Network Errors**: Continues processing other zip codes if one fails
- **Rate Limiting**: Sequential processing to avoid overwhelming API
- **Invalid Data**: Returns empty results gracefully for zip codes with no data
- **Retry Logic**: No automatic retry; logs errors and continues

## Performance Considerations

- **Average Runtime**: 5-10 minutes for full Ohio coverage
- **Data Volume**: 500-1000 agencies with events
- **Memory Usage**: Minimal - processes results sequentially
- **Optimization**: 
  - Dual search methods for comprehensive coverage
  - Efficient deduplication based on agency ID
  - Grid search fills gaps from zip code coverage

## Troubleshooting

### Common Issues

1. **No Results for Zip Code**
   - **Symptoms**: Empty results for valid zip codes
   - **Cause**: No agencies within search radius
   - **Solution**: Grid search provides overlapping coverage

2. **API Connection Errors**
   - **Symptoms**: HTTP errors or timeouts
   - **Cause**: API server issues or network problems
   - **Solution**: Check API status; scraper continues with remaining searches

3. **Duplicate Agencies**
   - **Symptoms**: Same agency appearing multiple times
   - **Cause**: Agency found in multiple search areas
   - **Solution**: Built-in deduplication by agency ID

### Debug Commands

```bash
# Run with debug logging
./bouy --verbose scraper freshtrak

# Check scraper logs
./bouy logs app | grep freshtrak

# Test API connection
./bouy exec app python -c "import httpx; resp = httpx.get('https://pantry-finder-api.freshtrak.com/api/agencies?zip_code=43215'); print(resp.status_code)"
```

## Maintenance Notes

- **Last Updated**: 2025-08-07
- **Update Frequency**: Verify API availability quarterly
- **Known Limitations**: 
  - API primarily focused on Ohio agencies
  - Event dates may include past dates
  - Some agencies may not have events
- **Future Improvements**: 
  - Add support for other states if API expands
  - Implement parallel processing for zip codes
  - Cache results to avoid duplicate API calls

## Related Documentation

- [FreshTrak Website](https://freshtrak.com/)
- [Mid-Ohio Food Collective](https://mofc.org/)
- [ScraperJob Base Class](../utilities/scraper_job.md)
- [Grid Generation Utilities](../utilities/grid_utils.md)