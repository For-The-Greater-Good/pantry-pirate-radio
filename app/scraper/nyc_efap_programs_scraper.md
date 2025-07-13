# NYC Emergency Food Assistance Program (EFAP) Scraper

This scraper extracts food program information from the NYC Emergency Food Assistance Program (EFAP) PDF file.

## Source

The data is sourced from the NYC Human Resources Administration (HRA) website:
- URL: https://www.nyc.gov/assets/hra/downloads/pdf/services/efap/CFC_ACTIVE.pdf
- Format: PDF file with tabular data
- Update Frequency: Unknown (check periodically for updates)

## Data Structure

The PDF contains a table with information about food assistance programs in New York City. Each row represents a single program with the following information:

- Program Name
- Address
- Borough
- ZIP Code
- Phone Number
- Hours of Operation (if available)

## Implementation Details

The scraper performs the following steps:

1. Downloads the PDF file from the NYC HRA website
2. Extracts tables from the PDF using pdfplumber
3. Parses each row to extract program information
4. Geocodes addresses to get latitude and longitude
5. Transforms data to HSDS format
6. Submits each program to the processing queue

## HSDS Mapping

The data is mapped to the HSDS schema as follows:

| PDF Field       | HSDS Field                   |
|-----------------|------------------------------|
| Program Name    | name                         |
| Address         | address.address_1            |
| Borough         | service_attributes (BOROUGH) |
| ZIP Code        | address.postal_code          |
| Phone Number    | phones[0].number             |
| Hours           | regular_schedule             |

Additional fields:
- `description`: Generated based on program name and borough
- `status`: Set to "active"
- `address.city`: Set to "New York"
- `address.state_province`: Set to "NY"
- `address.country`: Set to "US"
- `service_attributes`: Includes PROGRAM_TYPE = "Emergency Food Assistance Program (EFAP)"

## Geocoding

Addresses are geocoded using the GeocoderUtils class from utils.py. If geocoding fails, default coordinates for NYC are used with a random offset to avoid stacking.

## Error Handling

- Failed geocoding attempts are logged and default coordinates are used
- Failed program processing is logged and saved to a JSON file in the outputs directory
- A summary of the scraping operation is returned, including success and failure counts

## Usage

```bash
# Run the scraper
python -m app.scraper nyc_efap_programs
```

## Dependencies

- pdfplumber: For extracting text and tables from PDF files
- requests: For downloading the PDF file
- GeocoderUtils: For geocoding addresses
