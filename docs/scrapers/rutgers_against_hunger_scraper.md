# Rutgers Against Hunger (RAH) Scraper

This document explains the functionality and implementation details of the Rutgers Against Hunger (RAH) scraper, which extracts food pantry information from the RAH local pantries webpage.

## Overview

The `Rutgers_Against_HungerScraper` is designed to:

1. Download HTML content from the RAH local pantries webpage
2. Parse the HTML to extract food pantry information organized by county
3. Geocode addresses to get latitude and longitude coordinates
4. Transform the data into HSDS format
5. Submit each pantry to the processing queue

## Source

The data is sourced from the Rutgers Against Hunger website:
- URL: https://rah.rutgers.edu/resources/local-pantries/
- Format: HTML webpage with pantry listings organized by county in accordion elements
- Update Frequency: Unknown (check periodically for updates)

## Data Structure

The webpage contains information about food pantries in New Jersey organized by county. For each pantry, the scraper extracts:

- Organization Name
- Services Provided (Food Pantry, Soup Kitchen, etc.)
- City
- Phone Number
- Website URL (if available)
- County

## Implementation Details

The scraper performs the following steps:

1. **HTML Download**: Downloads the HTML content from the RAH website
2. **HTML Parsing**: Uses BeautifulSoup to extract pantry information from the HTML
3. **Data Extraction**: Extracts pantry details from the HTML tables within accordion elements
4. **Geocoding**: Uses GeocoderUtils to geocode addresses to get latitude and longitude
5. **Data Transformation**: Transforms the extracted data to HSDS format
6. **Job Submission**: Submits each pantry to the processing queue

## Extraction Strategy

The scraper uses the following approach to extract pantry information:

1. Find all accordion elements which contain county data
2. For each accordion:
   - Extract the county name from the summary element
   - Find the table within the accordion
   - Process each row in the table (skipping the header row)
   - Extract name, services, city, and phone number from the table cells
   - Create an address by combining city and county
   - Store the extracted data in a structured format

## Geocoding

Addresses are geocoded using the GeocoderUtils class from utils.py:

1. The scraper creates addresses in the format: "{City}, {County} County, NJ"
2. It attempts to geocode these addresses using multiple geocoding services
3. If geocoding fails, it uses default coordinates for the specific county or for New Jersey with a random offset

## HSDS Mapping

The data is mapped to the HSDS schema as follows:

| RAH Field       | HSDS Field                   |
|-----------------|------------------------------|
| Name            | name                         |
| Services        | description (appended)       |
| City            | address.city                 |
| County          | service_attributes (COUNTY)  |
| Phone           | phones[0].number             |
| URL             | url                          |
| Services        | service_attributes (PROGRAM_TYPE) |

Additional fields:
- `status`: Set to "active"
- `address.state_province`: Set to "NJ"
- `address.country`: Set to "US"

## Error Handling

The scraper includes comprehensive error handling:

1. **HTML Download Failures**: Logs errors and raises exceptions
2. **Parsing Issues**: Checks for missing elements and handles them gracefully
3. **Geocoding Failures**: Uses default coordinates with random offsets
4. **Data Transformation Problems**: Logs errors and continues with next pantry
5. **Failed Pantries**: Saves details of failed pantries to a JSON file for later review

## Usage

To run the scraper:

```bash
python -m app.scraper rutgers_against_hunger
```

To test the scraper without submitting jobs:

```bash
python -m app.scraper.test_scrapers rutgers_against_hunger
```

## Output

The scraper outputs:

1. **Queue Jobs**: Each food pantry is submitted to the processing queue
2. **Summary**: Printed to the console with statistics about the scraping process
3. **Failed Pantries**: Saved to a JSON file in the outputs directory for later review

## Future Improvements

Potential enhancements for the scraper:

1. **Street Address Extraction**: Implement a way to extract or infer street addresses
2. **Hours Information**: Add support for extracting hours of operation if available
3. **Additional Metadata**: Extract and include additional metadata about services offered
4. **County-Specific Coordinates**: Add default coordinates for all NJ counties
5. **Incremental Updates**: Implement a mechanism to only process new or changed pantries
