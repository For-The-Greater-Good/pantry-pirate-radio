# Care and Share Food Locator Scraper

This document explains the functionality and implementation details of the Care and Share Food Locator scraper, which extracts food pantry information from the Care and Share Food Locator website.

## Overview

The `Care_And_Share_Food_LocatorScraper` is designed to:

1. Fetch HTML content from the Care and Share Food Locator website
2. Extract food pantry information from the HTML content
3. Navigate through all pages of results using pagination
4. Deduplicate locations to ensure unique entries
5. Geocode addresses to get latitude and longitude coordinates
6. Transform the data into HSDS format
7. Submit each pantry to the processing queue

## Data Source

The scraper targets the following URL:
```
https://careandshare.org/findfood/food-locator/
```

The search is performed with the following parameters:
- Location: Denver, CO
- Distance: 500 miles
- Results per page: 100

## Extracted Data

For each food pantry, the scraper extracts:

- **Name**: The name of the food pantry or organization
- **URL**: The URL to the pantry's detail page
- **Address**: The physical address of the pantry
- **Distance**: Distance from the search location
- **Phone Number**: Contact phone number
- **Hours of Operation**: Days and hours when the pantry is open
- **Service Area**: Information about the service area

## Implementation Details

### HTML Parsing

The scraper uses BeautifulSoup to parse the HTML content and extract the food pantry information. It looks for elements with specific CSS classes:

- `.gmw-single-item`: Container for each food pantry
- `.post-title a`: Name and URL of the pantry
- `.address a`: Address of the pantry
- `.distance`: Distance from the search location
- `.field.phone .info a`: Phone number
- `.gmw-hours-of-operation li`: Hours of operation
- `.services-wrap p`: Service area information

### Pagination Handling

The scraper handles pagination by:

1. Extracting the "next page" link from the current page
2. Following the link to the next page
3. Repeating until there are no more pages

### Deduplication

To avoid duplicate entries, the scraper:

1. Generates a unique key for each location based on name and address
2. Keeps track of locations that have already been processed
3. Only processes unique locations

### Address Parsing

The scraper parses the address string into components:

1. Street address
2. City
3. State
4. ZIP code

It uses regular expressions to extract these components from the full address string.

### Hours Parsing

The scraper parses the hours of operation into HSDS format:

1. Extracts the day of the week
2. Extracts the opening and closing times
3. Handles complex patterns like "11 a.m. - 1 p.m. & 4 p.m. - 6 p.m."

### Geocoding

Addresses are geocoded using the GeocoderUtils class from utils.py:

1. Attempts to geocode the full address
2. If geocoding fails, uses default coordinates for Colorado with a random offset

## HSDS Mapping

The data is mapped to the HSDS schema as follows:

| Care and Share Field | HSDS Field                   |
|----------------------|------------------------------|
| Name                 | name                         |
| URL                  | url                          |
| Address (street)     | address.address_1            |
| Address (city)       | address.city                 |
| Address (state)      | address.state_province       |
| Address (zip)        | address.postal_code          |
| Phone                | phones[0].number             |
| Hours                | regular_schedule             |
| Service Area         | description (appended)       |

## Error Handling

The scraper includes comprehensive error handling:

1. **HTTP Request Failures**: Logs errors and continues with the next page
2. **HTML Parsing Errors**: Logs errors and continues with the next location
3. **Geocoding Failures**: Uses default coordinates with random offsets
4. **Address Parsing Errors**: Handles missing or malformed address components
5. **Hours Parsing Errors**: Handles various time formats and patterns

## Usage

To run the scraper:

```bash
python -m app.scraper care_and_share_food_locator
```

## Dependencies

- **httpx**: For asynchronous HTTP requests
- **BeautifulSoup**: For HTML parsing
- **GeocoderUtils**: For geocoding addresses
