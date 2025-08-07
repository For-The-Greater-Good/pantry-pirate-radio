# Capital Area Food Bank DC Scraper

## Overview

This scraper extracts food pantry and distribution site information from the Capital Area Food Bank's ArcGIS Feature Service, covering the Washington DC metropolitan area and surrounding regions.

## Data Source

- **Organization**: Capital Area Food Bank
- **Website**: https://www.capitalareafoodbank.org/find-food-assistance/
- **API Type**: ArcGIS Feature Service (REST API)
- **API Endpoint(s)**: 
  - Primary: `https://services.arcgis.com/oCjyzxNy34f0pJCV/arcgis/rest/services/Active_Agencies_Last_45_Days/FeatureServer/0`
- **Documentation**: ArcGIS REST API standard documentation

## Coverage Area

Geographic regions covered by this scraper:
- **States**: DC, Maryland (MD), Virginia (VA)
- **Counties/Regions**: 
  - Washington DC
  - Montgomery County, MD
  - Prince George's County, MD
  - Arlington County, VA
  - Alexandria City, VA
  - Fairfax County, VA
  - Prince William County, VA
- **Search Method**: Full dataset retrieval with pagination
- **Search Parameters**: Queries all active agencies from last 45 days

## Technical Implementation

### Scraper Class
- **Class Name**: `CapitalAreaFoodBankDcScraper`
- **Base Class**: `ScraperJob`
- **Module Path**: `app.scraper.capital_area_food_bank_dc_scraper`

### Key Configuration
```python
# Configuration parameters
batch_size = 10  # Number of items processed per batch (3 in test mode)
request_delay = 0.5  # Delay between requests in seconds (0.05 in test mode)
timeout = 30.0  # Request timeout in seconds
```

### Dependencies
- **Required Libraries**: httpx, asyncio, json, BeautifulSoup
- **External Services**: GeocoderUtils for address geocoding fallback
- **Rate Limiting**: 0.5 second delay between paginated requests

## Data Structure

### Input Parameters
The scraper queries the ArcGIS Feature Service with:
- `where`: "1=1" (retrieves all records)
- `outFields`: "*" (all fields)
- `f`: "json" (JSON format)
- `returnGeometry`: true (includes coordinates)
- `resultOffset`: Pagination offset
- `resultRecordCount`: Records per page (1000)
- `orderByFields`: "name" (sorted by name)

### Output Format
Each location is structured as:

```json
{
  "id": "OBJECTID from ArcGIS",
  "name": "Organization name",
  "address": "Street address line 1",
  "address2": "Street address line 2",
  "city": "City name",
  "state": "State abbreviation (default: DC)",
  "zip": "ZIP code",
  "county": "County name",
  "phone": "Contact phone number",
  "latitude": "Geographic latitude from ArcGIS geometry",
  "longitude": "Geographic longitude from ArcGIS geometry",
  "website": "Organization website URL",
  "email": "Contact email address",
  "tefap": "TEFAP program status",
  "hours": "Operating hours by day",
  "services": ["TEFAP Only", "TEFAP Available"],
  "notes": "Additional notes",
  "source": "capital_area_food_bank_dc",
  "food_bank": "Capital Area Food Bank",
  "full_address": "Complete formatted address"
}
```

### Key Fields Extracted
- **name**: Organization/pantry name
- **address**: Full street address (combines address1 and address2)
- **city**: City name
- **state**: State abbreviation (defaults to DC)
- **zip**: ZIP/postal code
- **latitude**: Geographic latitude from ArcGIS geometry.y
- **longitude**: Geographic longitude from ArcGIS geometry.x
- **phone**: Contact phone number
- **hours**: Complex multi-slot daily schedule (up to 3 time slots per day)
- **services**: TEFAP program participation status
- **website**: Organization website
- **email**: Contact email
- **county**: County name for location
- **notes**: Additional information

## Usage

### Running the Scraper

```bash
# Run the scraper using bouy
./bouy scraper capital_area_food_bank_dc

# Test mode (limited data - 10 locations max)
./bouy scraper-test capital_area_food_bank_dc

# Run with verbose output
./bouy --verbose scraper capital_area_food_bank_dc
```

### Testing

```bash
# Run specific tests for this scraper
./bouy test --pytest tests/test_scraper/test_capital_area_food_bank_dc_scraper.py

# Run with coverage
./bouy test --coverage -- tests/test_scraper/test_capital_area_food_bank_dc_scraper.py
```

## Error Handling

- **Network Errors**: Catches httpx.HTTPError and logs error details
- **Rate Limiting**: Implements 0.5 second delay between pagination requests
- **Invalid Data**: Handles missing fields with empty strings or defaults
- **Retry Logic**: No automatic retry; fails gracefully and logs errors
- **Geocoding Fallback**: Uses GeocoderUtils with pre-configured regional defaults when ArcGIS doesn't provide coordinates

## Performance Considerations

- **Average Runtime**: 30-60 seconds for full dataset
- **Data Volume**: Typically 200-400 active locations
- **Memory Usage**: Minimal - processes in batches with pagination
- **Optimization**: 
  - Paginated queries (1000 records per request)
  - Deduplication based on name and address
  - Test mode limits to 10 locations

## Troubleshooting

### Common Issues

1. **No Data Returned**
   - **Symptoms**: Scraper completes but returns 0 locations
   - **Cause**: ArcGIS service may be down or URL changed
   - **Solution**: Verify feature service URL is accessible and check for API changes

2. **Timeout Errors**
   - **Symptoms**: httpx.Timeout exceptions in logs
   - **Cause**: Slow network or ArcGIS service response
   - **Solution**: Increase timeout value or check network connectivity

3. **Missing Coordinates**
   - **Symptoms**: Locations using default coordinates
   - **Cause**: ArcGIS geometry data missing
   - **Solution**: Check if ArcGIS service configuration changed; geocoding fallback should handle this

### Debug Commands

```bash
# Run with debug logging
./bouy --verbose scraper capital_area_food_bank_dc

# Check scraper logs
./bouy logs app | grep capital_area_food_bank_dc

# Test ArcGIS connection directly
./bouy exec app python -c "import httpx; resp = httpx.get('https://services.arcgis.com/oCjyzxNy34f0pJCV/arcgis/rest/services/Active_Agencies_Last_45_Days/FeatureServer/0?f=json'); print(resp.status_code)"
```

## Maintenance Notes

- **Last Updated**: 2025-08-07
- **Update Frequency**: Check quarterly for ArcGIS service changes
- **Known Limitations**: 
  - Only retrieves agencies active in last 45 days
  - Complex hours format requires parsing multiple time slot fields
- **Future Improvements**: 
  - Add support for additional service types beyond TEFAP
  - Implement retry logic for failed requests

## Related Documentation

- [ArcGIS REST API Documentation](https://developers.arcgis.com/rest/)
- [Capital Area Food Bank Website](https://www.capitalareafoodbank.org/)
- [GeocoderUtils Documentation](../utilities/geocoder_utils.md)