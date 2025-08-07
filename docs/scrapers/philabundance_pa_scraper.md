# Philabundance PA Scraper

## Overview

This scraper extracts food pantry and distribution site information from Philabundance's website using their WordPress Store Locator API. Philabundance is the largest hunger relief organization in the Philadelphia region.

## Data Source

- **Organization**: Philabundance
- **Website**: https://www.philabundance.org/find-food/
- **API Type**: WordPress Store Locator (WPSL) AJAX API
- **API Endpoint(s)**: 
  - Primary: `https://www.philabundance.org/wp-admin/admin-ajax.php`
  - Action: `store_search`
- **Documentation**: WordPress Store Locator plugin (standard implementation)

## Coverage Area

Geographic regions covered by this scraper:
- **States**: Pennsylvania (PA), New Jersey (NJ), Delaware (DE)
- **Counties/Regions**: 
  - Philadelphia County and surrounding areas
  - Bucks County, PA
  - Chester County, PA
  - Delaware County, PA
  - Montgomery County, PA
  - Parts of South Jersey
- **Search Method**: Coordinate-based search with radius
- **Search Parameters**: 50-mile radius searches from multiple center points

## Technical Implementation

### Scraper Class
- **Class Name**: `PhilabundancePaScraper`
- **Base Class**: `ScraperJob`
- **Module Path**: `app.scraper.philabundance_pa_scraper`

### Key Configuration
```python
# Configuration parameters
batch_size = 10  # Number of items processed per batch (3 in test mode)
request_delay = 1.0  # Delay between requests in seconds (0.1 in test mode)
timeout = 30.0  # Request timeout in seconds
search_radius = 50  # Default search radius in miles
```

### Dependencies
- **Required Libraries**: httpx, asyncio, json
- **External Services**: GeocoderUtils for address geocoding
- **Rate Limiting**: 1 second delay between API requests

## Data Structure

### Input Parameters
The WPSL API accepts:
- `action`: "store_search" (required)
- `lat`: Latitude of search center
- `lng`: Longitude of search center
- `max_results`: Maximum results to return (default: 50)
- `search_radius`: Radius in miles (default: 50)
- `filter`: Category filter for locations

### Output Format
Each location record includes:

```json
{
  "id": "Unique location ID",
  "store": "Location name",
  "address": "Street address",
  "address2": "Address line 2",
  "city": "City name",
  "state": "State abbreviation",
  "zip": "ZIP code",
  "country": "Country code",
  "lat": "Latitude",
  "lng": "Longitude",
  "phone": "Contact phone",
  "fax": "Fax number",
  "email": "Contact email",
  "hours": "Operating hours",
  "url": "Website URL",
  "description": "Location description",
  "terms": ["Category terms"],
  "distance": "Distance from search center"
}
```

### Key Fields Extracted
- **id**: Unique location identifier
- **store**: Organization/pantry name
- **address**: Street address
- **city**: City name
- **state**: State abbreviation
- **zip**: ZIP/postal code
- **lat**: Geographic latitude
- **lng**: Geographic longitude
- **phone**: Contact phone number
- **hours**: Operating hours (may be HTML formatted)
- **url**: Location website or details page
- **description**: Additional information about services
- **terms**: Categories/types of services

## Usage

### Running the Scraper

```bash
# Run the scraper using bouy
./bouy scraper philabundance_pa

# Test mode (limited data)
./bouy scraper-test philabundance_pa

# Run with verbose output
./bouy --verbose scraper philabundance_pa
```

### Testing

```bash
# Run specific tests for this scraper
./bouy test --pytest tests/test_scraper/test_philabundance_pa_scraper.py

# Run with coverage
./bouy test --coverage -- tests/test_scraper/test_philabundance_pa_scraper.py
```

## Error Handling

- **Network Errors**: Catches httpx.HTTPError and logs details
- **Rate Limiting**: 1 second delay between requests to respect server
- **Invalid Data**: Handles missing fields with defaults
- **Retry Logic**: No automatic retry; fails gracefully and continues
- **Geocoding Fallback**: Uses provided coordinates; falls back to GeocoderUtils if needed

## Performance Considerations

- **Average Runtime**: 2-5 minutes for full region coverage
- **Data Volume**: 200-400 locations typically
- **Memory Usage**: Minimal - processes results in batches
- **Optimization**: 
  - Multiple search centers for comprehensive coverage
  - Deduplication based on location ID
  - Batch processing for queue submission

## Troubleshooting

### Common Issues

1. **Empty Results**
   - **Symptoms**: API returns no locations
   - **Cause**: Invalid coordinates or API changes
   - **Solution**: Verify search coordinates are within service area

2. **AJAX Errors**
   - **Symptoms**: 400/403 errors from admin-ajax.php
   - **Cause**: Missing required parameters or security changes
   - **Solution**: Check that 'action' parameter is correct

3. **Incomplete Data**
   - **Symptoms**: Missing hours or contact information
   - **Cause**: Data not populated in WordPress backend
   - **Solution**: Normal - handle gracefully with defaults

### Debug Commands

```bash
# Run with debug logging
./bouy --verbose scraper philabundance_pa

# Check scraper logs
./bouy logs app | grep philabundance_pa

# Test API connection
./bouy exec app python -c "import httpx; params={'action':'store_search','lat':'39.9526','lng':'-75.1652'}; resp = httpx.get('https://www.philabundance.org/wp-admin/admin-ajax.php', params=params); print(resp.status_code)"
```

## Maintenance Notes

- **Last Updated**: 2025-08-07
- **Update Frequency**: Check quarterly for API changes
- **Known Limitations**: 
  - WordPress Store Locator may change without notice
  - Hours field may contain HTML formatting
  - Limited to locations within search radius
- **Future Improvements**: 
  - Add support for category filtering
  - Parse HTML in hours field for cleaner data
  - Implement dynamic search center generation based on coverage gaps

## Related Documentation

- [Philabundance Website](https://www.philabundance.org/)
- [WordPress Store Locator Plugin](https://wpstorelocator.co/)
- [ScraperJob Base Class](../utilities/scraper_job.md)
- [GeocoderUtils Documentation](../utilities/geocoder_utils.md)