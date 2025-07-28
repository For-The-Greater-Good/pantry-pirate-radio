# The Food Pantries Org Scraper

This document explains the functionality and implementation details of The Food Pantries Org Scraper, which extracts food pantry information from map.thefoodpantries.org.

## Overview

The `The_Food_Pantries_OrgScraper` is designed to:

1. Download HTML content from map.thefoodpantries.org
2. Extract GeoJSON data embedded in the HTML
3. Process features from the GeoJSON collection
4. Submit each feature (food pantry location) as a separate job to the processing queue

## Data Source

The scraper targets the following URL:
```
https://map.thefoodpantries.org
```

This website contains embedded GeoJSON data in HTML container elements with a `resource-data` attribute.

## Extracted Data

For each feature in the GeoJSON collection, the scraper extracts:

- **Properties**: The properties of the feature, which typically include information about the food pantry
- **Collection Metadata**: The name and category of the collection, which are added to the properties

## Implementation Details

### Dependencies

- **httpx**: For asynchronous HTTP requests
- **json**: For parsing GeoJSON data
- **re**: For regular expression matching to extract GeoJSON data

### Key Methods

1. **download_html()**: Downloads the HTML content from the website
2. **extract_json()**: Extracts GeoJSON data from the HTML content
3. **scrape()**: Orchestrates the entire scraping process

### Processing Flow

1. The scraper downloads the HTML content from the website
2. It extracts GeoJSON data from the HTML using regular expressions
3. It combines all features from multiple GeoJSON collections into a single collection
4. For each feature in the combined collection:
   - It extracts the properties
   - It enriches the properties with collection metadata
   - It submits the properties to the queue for processing

## Error Handling

The scraper includes error handling for:

1. **Download Failures**: Handles HTTP errors when downloading HTML
2. **Extraction Failures**: Handles errors when extracting GeoJSON data
3. **JSON Parsing Errors**: Handles invalid JSON data
4. **Validation Errors**: Ensures the extracted data matches the expected format

## Usage

To run the scraper:

```bash
python -m app.scraper the_food_pantries_org
```

## Output

The scraper outputs:

1. **Queue Jobs**: Each feature is submitted to the processing queue
2. **Summary**: Printed to the console with statistics about the scraping process
3. **Raw Content**: The original GeoJSON data is returned for archiving
