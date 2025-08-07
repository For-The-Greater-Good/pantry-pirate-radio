# Maryland Food Bank MD Scraper

## Overview

This scraper extracts food pantry and distribution site information from the Maryland Food Bank website using Playwright for JavaScript rendering and HTML parsing.

## Data Source

- **Organization**: Maryland Food Bank
- **Website**: https://mdfoodbank.org/find-food/
- **API Type**: HTML Scraping with JavaScript rendering (Playwright)
- **API Endpoint(s)**: N/A - Direct HTML scraping
- **Documentation**: No API documentation (web scraping)

## Coverage Area

Geographic regions covered by this scraper:
- **States**: Maryland (MD)
- **Counties/Regions**: All Maryland counties served by Maryland Food Bank
- **Search Method**: Single page scrape with List view
- **Search Parameters**: Downloads all locations from the interactive map

## Technical Implementation

### Scraper Class
- **Class Name**: `MarylandFoodBankMdScraper`
- **Base Class**: `ScraperJob`
- **Module Path**: `app.scraper.maryland_food_bank_md_scraper`

### Key Configuration
```python
# Configuration parameters
batch_size = 10  # Number of items processed per batch (3 in test mode)
request_delay = 0.5  # Delay between requests in seconds (0.05 in test mode)
timeout = 30.0  # Request timeout in seconds
```

### Dependencies
- **Required Libraries**: httpx, asyncio, json, BeautifulSoup, playwright
- **External Services**: GeocoderUtils for address geocoding
- **Rate Limiting**: 0.5 second delay between batch processing

## Data Structure

### Input Parameters
The scraper navigates to the main find-food page and:
- Clicks the "List" view button to display all locations
- Waits for JavaScript to render the full list
- Scrolls to load all locations if needed

### Output Format
Each location is structured as:

```json
{
  "name": "Organization name",
  "address": "Full street address",
  "city": "City name",
  "state": "MD",
  "zip": "ZIP code",
  "phone": "Contact phone number",
  "hours": "Operating hours",
  "services": ["List of services"],
  "latitude": "Geographic latitude",
  "longitude": "Geographic longitude",
  "source": "maryland_food_bank_md",
  "food_bank": "Maryland Food Bank"
}
```

### Key Fields Extracted
- **name**: Organization/pantry name
- **address**: Full street address
- **city**: City name
- **state**: State (MD)
- **zip**: ZIP/postal code
- **latitude**: Geographic latitude (via geocoding)
- **longitude**: Geographic longitude (via geocoding)
- **phone**: Contact phone number
- **hours**: Operating hours and schedule
- **services**: Types of services offered

## Usage

### Running the Scraper

```bash
# Run the scraper using bouy
./bouy scraper maryland_food_bank_md

# Test mode (limited data)
./bouy scraper-test maryland_food_bank_md

# Run with verbose output
./bouy --verbose scraper maryland_food_bank_md
```

### Testing

```bash
# Run specific tests for this scraper
./bouy test --pytest tests/test_scraper/test_maryland_food_bank_md_scraper.py

# Run with coverage
./bouy test --coverage -- tests/test_scraper/test_maryland_food_bank_md_scraper.py
```

## Error Handling

- **Network Errors**: Catches exceptions and logs error details
- **JavaScript Rendering**: Uses Playwright to handle dynamic content
- **List View Loading**: Multiple selectors attempted to find List button
- **Invalid Data**: Handles missing fields with defaults
- **Retry Logic**: No automatic retry; fails gracefully

## Performance Considerations

- **Average Runtime**: 30-60 seconds including JavaScript rendering
- **Data Volume**: Typically 25-50 locations
- **Memory Usage**: Moderate due to Playwright browser instance
- **Optimization**: 
  - Single page load with List view
  - Batch processing of extracted locations
  - Test mode limits processing

## Troubleshooting

### Common Issues

1. **List View Button Not Found**
   - **Symptoms**: Cannot switch to list view
   - **Cause**: Website structure changed
   - **Solution**: Update button selectors in the code

2. **Locations Not Loading**
   - **Symptoms**: No locations extracted from HTML
   - **Cause**: JavaScript not fully rendered or selectors changed
   - **Solution**: Increase wait times or update CSS selectors

3. **Playwright Errors**
   - **Symptoms**: Browser launch or navigation failures
   - **Cause**: Playwright dependencies or headless browser issues
   - **Solution**: Ensure Playwright is properly installed with browsers

### Debug Commands

```bash
# Run with debug logging
./bouy --verbose scraper maryland_food_bank_md

# Check scraper logs
./bouy logs app | grep maryland_food_bank_md

# Test Playwright installation
./bouy exec app python -c "from playwright.async_api import async_playwright; print('Playwright OK')"
```

## Maintenance Notes

- **Last Updated**: 2025-08-07
- **Update Frequency**: Check quarterly for website changes
- **Known Limitations**: 
  - Requires JavaScript rendering (slower than API)
  - Limited to locations shown in List view
  - Dependent on website structure
- **Future Improvements**: 
  - Implement pagination if more locations added
  - Add retry logic for failed page loads
  - Extract additional details from location cards

## Related Documentation

- [Playwright Documentation](https://playwright.dev/python/)
- [Maryland Food Bank Website](https://mdfoodbank.org/)
- [GeocoderUtils Documentation](../utilities/geocoder_utils.md)