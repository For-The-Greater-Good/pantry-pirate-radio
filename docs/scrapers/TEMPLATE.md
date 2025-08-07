# [Scraper Name] Scraper

## Overview

Brief description of what this scraper does and what organization/platform it scrapes data from.

## Data Source

- **Organization**: [Name of the organization or platform]
- **Website**: [Main website URL]
- **API Type**: [REST API / GraphQL / HTML Scraping / ArcGIS / etc.]
- **API Endpoint(s)**: 
  - Primary: `[endpoint URL]`
  - Additional: `[if any]`
- **Documentation**: [Link to API documentation if available]

## Coverage Area

Geographic regions covered by this scraper:
- **States**: [List of states]
- **Counties/Regions**: [Specific counties or regions if applicable]
- **Search Method**: [Grid-based / Zip code-based / County-based / etc.]
- **Search Parameters**: [Radius, grid spacing, etc.]

## Technical Implementation

### Scraper Class
- **Class Name**: `[ExactClassName]`
- **Base Class**: `ScraperJob`
- **Module Path**: `app.scraper.[module_name]`

### Key Configuration
```python
# Configuration parameters
batch_size = [value]  # Number of items processed per batch
request_delay = [value]  # Delay between requests in seconds
timeout = [value]  # Request timeout in seconds
```

### Dependencies
- **Required Libraries**: [httpx, BeautifulSoup, etc.]
- **External Services**: [Geocoding services, etc.]
- **Rate Limiting**: [Details about rate limits]

## Data Structure

### Input Parameters
Description of any search parameters or inputs the scraper uses.

### Output Format
Description of the data structure returned by the scraper:

```json
{
  "field_name": "description and type",
  "nested_object": {
    "sub_field": "description"
  }
}
```

### Key Fields Extracted
- **name**: Organization/pantry name
- **address**: Full street address
- **city**: City name
- **state**: State abbreviation
- **zip_code**: ZIP/postal code
- **latitude**: Geographic latitude
- **longitude**: Geographic longitude
- **phone**: Contact phone number
- **hours**: Operating hours
- **services**: Types of services offered
- [Additional fields specific to this scraper]

## Usage

### Running the Scraper

```bash
# Run the scraper using bouy
./bouy scraper [scraper_name]

# Test mode (limited data)
./bouy scraper-test [scraper_name]

# Run with verbose output
./bouy --verbose scraper [scraper_name]
```

### Testing

```bash
# Run specific tests for this scraper
./bouy test --pytest tests/test_scraper/test_[scraper_name].py

# Run with coverage
./bouy test --coverage -- tests/test_scraper/test_[scraper_name].py
```

## Error Handling

- **Network Errors**: [How the scraper handles connection issues]
- **Rate Limiting**: [Behavior when rate limited]
- **Invalid Data**: [How malformed data is handled]
- **Retry Logic**: [If and how retries are implemented]

## Performance Considerations

- **Average Runtime**: [Typical execution time]
- **Data Volume**: [Approximate number of locations returned]
- **Memory Usage**: [Any memory considerations]
- **Optimization**: [Batch processing, parallel requests, etc.]

## Troubleshooting

### Common Issues

1. **Issue Name**
   - **Symptoms**: Description of the problem
   - **Cause**: Root cause
   - **Solution**: How to fix it

2. **API Changes**
   - **Symptoms**: Scraper returns no data or errors
   - **Cause**: API endpoint or structure changed
   - **Solution**: Check API documentation and update scraper

### Debug Commands

```bash
# Run with debug logging
./bouy --verbose scraper [scraper_name]

# Check scraper logs
./bouy logs app | grep [scraper_name]

# Test specific functionality
./bouy exec app python -c "from app.scraper.[module_name] import [ClassName]; print([ClassName]().test_connection())"
```

## Maintenance Notes

- **Last Updated**: [Date]
- **Update Frequency**: [How often the scraper needs maintenance]
- **Known Limitations**: [Any known issues or limitations]
- **Future Improvements**: [Planned enhancements]

## Related Documentation

- [Link to related scrapers or documentation]
- [API documentation links]
- [Organization documentation]