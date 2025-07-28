# HCCC Food Pantry Scraper

This document explains the functionality and implementation details of the HCCC Food Pantry scraper, which extracts food pantry information from the Hudson County Community College (HCCC) Food Pantry List PDF.

## Overview

The `Hccc_Food_PantryScraper` is designed to:

1. Download the PDF file from the HCCC website
2. Extract text and table data from the PDF
3. Process the extracted data to identify food pantries
4. Geocode addresses to get latitude and longitude coordinates
5. Transform the data into HSDS format
6. Submit each pantry to the processing queue

## Source

The data is sourced from the Hudson County Community College website:
- URL: https://www.hccc.edu/student-success/resources/documents/food-pantry-list-2021.pdf
- Format: PDF file with tabular data
- Update Frequency: Unknown (check periodically for updates)

## Data Structure

The PDF contains information about food pantries in Hudson County, NJ. For each pantry, the scraper attempts to extract:

- Organization Name
- Address
- Phone Number
- Hours of Operation
- Additional Notes

## Implementation Details

The scraper performs the following steps:

1. **PDF Download**: Downloads the PDF file from the HCCC website
2. **Text Extraction**: Uses pdfplumber to extract tables and text from the PDF
3. **Data Parsing**: Parses the extracted data using two approaches:
   - Table parsing: Extracts data from tables in the PDF
   - Text parsing: Falls back to text-based extraction if tables aren't available
4. **Geocoding**: Uses GeocoderUtils to geocode addresses to get latitude and longitude
5. **Data Transformation**: Transforms the extracted data to HSDS format
6. **Job Submission**: Submits each pantry to the processing queue

## Extraction Strategies

The scraper uses multiple strategies to handle different PDF formats:

1. **Table Extraction**: Primary approach that looks for tables in the PDF
   - Attempts to identify header rows
   - Falls back to default headers if none are found
   - Processes each row to extract pantry information

2. **Text Extraction**: Fallback approach when tables aren't available
   - Splits text into sections based on blank lines
   - Uses regular expressions to identify pantry names, addresses, phone numbers, and hours
   - Applies heuristics to determine which sections represent pantries

## Geocoding

Addresses are geocoded using the GeocoderUtils class from utils.py:

1. Attempts to geocode the full address
2. If geocoding fails, uses default coordinates for Hudson County with a random offset
3. Tracks geocoding success/failure statistics

## HSDS Mapping

The data is mapped to the HSDS schema as follows:

| PDF Field       | HSDS Field                   |
|-----------------|------------------------------|
| Name            | name                         |
| Address         | address.address_1            |
| Phone           | phones[0].number             |
| Hours           | hours_notes or regular_schedule |
| Notes           | description (appended)       |

Additional fields:
- `status`: Set to "active"
- `address.city`: Extracted from address or defaults to "Jersey City"
- `address.state_province`: Set to "NJ"
- `address.country`: Set to "US"
- `service_attributes`: Includes PROGRAM_TYPE = "Food Pantry" and COUNTY = "Hudson"

## Error Handling

The scraper includes comprehensive error handling:

1. **PDF Download Failures**: Logs errors and raises exceptions
2. **Text Extraction Issues**: Falls back to alternative extraction methods
3. **Geocoding Failures**: Uses default coordinates with random offsets
4. **Data Transformation Problems**: Logs errors and continues with next pantry
5. **Failed Pantries**: Saves details of failed pantries to a JSON file for later review

## Usage

To run the scraper:

```bash
python -m app.scraper hccc_food_pantry
```

To test the scraper without submitting jobs:

```bash
python -m app.scraper.test_scrapers hccc_food_pantry
```

## Dependencies

- pdfplumber: For extracting text and tables from PDF files
- requests: For downloading the PDF file
- GeocoderUtils: For geocoding addresses
