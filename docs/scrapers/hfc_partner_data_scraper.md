# HFC Partner Data Scraper

This document explains the functionality and implementation details of the HFC Partner Data scraper, which processes the CSV file containing HFC Partner Data.

## Overview

The `Hfc_Partner_DataScraper` is designed to:

1. Read the CSV file at `docs/HFCData/HFC_Partner_Data.csv`
2. Process each row in the CSV file
3. Transform the data into HSDS format
4. Submit each entry to the processing queue

## Data Source

The data is sourced from a CSV file:
- Path: `docs/HFCData/HFC_Partner_Data.csv`
- Format: CSV file with header row
- Content: Information about food assistance partners

## Extracted Data

For each row in the CSV file, the scraper extracts:

- **Basic Information**: Name, email, phone, website
- **Location**: Latitude, longitude, address
- **Service Information**: Type code, food type, services provided
- **Hours of Operation**: Days and hours of food pantry operation
- **Requirements**: Documents required, access requirements, languages spoken
- **Service Area**: Areas served, zip codes served, counties served

## Implementation Details

The scraper performs the following steps:

1. **CSV Reading**: Opens and reads the CSV file row by row
2. **Filtering**: Checks the "Show on Map" field to determine if entries should be included
3. **Data Transformation**: Transforms each row to HSDS format
4. **Hour Parsing**: Parses hours information into structured schedule data
5. **Job Submission**: Submits each transformed entry to the processing queue

## HSDS Mapping

The data is mapped to the HSDS schema as follows:

| CSV Field                   | HSDS Field                   |
|-----------------------------|------------------------------|
| Account Name                | name                         |
| Account Email               | email                        |
| Phone                       | phones[0].number             |
| Program Phone Number        | phones[1].number             |
| Website                     | url                          |
| MALatitude                  | location.latitude            |
| MALongitude                 | location.longitude           |
| Billing Address Line 1      | address.address_1            |
| Billing Address Line 2      | address.address_2            |
| Billing City                | address.city                 |
| Billing State/Province      | address.state_province       |
| Billing Zip/Postal Code     | address.postal_code          |
| Type Code                   | service_attributes           |
| Is this a food pantry?      | service_attributes           |
| Food Type                   | service_attributes           |
| Services Provided           | description                  |
| Days of Food Pantry Operation | regular_schedule           |
| Hours of Operation          | regular_schedule             |
| Exact Hours of Operation    | regular_schedule             |
| Documents Required          | service_attributes           |
| Access Requirements         | service_attributes           |
| Languages Spoken            | service_attributes           |
| Areas Served                | description                  |
| Population Served           | service_attributes           |
| Zip Codes Served By Delivery | description                 |
| Counties Served By Deliver  | description                  |
| Miles from Org Served By Delivery | description            |

Additional fields:
- `status`: Set to "active"
- `address.country`: Set to "US"

## Hour Parsing

The scraper includes a sophisticated hour parsing function that:

1. Tries to use "Exact Hours of Operation" if available
2. Falls back to "Days of Food Pantry Operation" and "Hours of Operation" if needed
3. Handles various time formats and day specifications
4. Creates structured schedule data in HSDS format
5. Falls back to storing hours as a note if structured parsing fails

## Error Handling

The scraper includes error handling for:

1. **Missing CSV File**: Raises FileNotFoundError if the CSV file is not found
2. **Missing Required Fields**: Skips rows with missing required fields
3. **Invalid Latitude/Longitude**: Uses default coordinates if lat/long are invalid
4. **Processing Errors**: Logs errors and continues with the next row

## Usage

To run the scraper:

```bash
python -m app.scraper hfc_partner_data
```

## Output

The scraper outputs:

1. **Queue Jobs**: Each processed row is submitted to the processing queue
2. **Summary**: Printed to the console with statistics about the scraping process
3. **Logs**: Detailed logs of the scraping process, including any errors

The summary includes:
- Total rows in the CSV file
- Number of processed rows
- Number of skipped rows
- Number of jobs created
- Source file path
