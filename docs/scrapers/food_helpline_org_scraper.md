# FoodHelpline.org Scraper

## Overview

This scraper collects food resource data from the FoodHelpline.org API. FoodHelpline.org is a platform that provides information about food assistance resources across the United States. The scraper fetches data about regions, locations, and resources, transforms it into HSDS format, and submits it to the processing queue.

## API Endpoints

The scraper interacts with the following API endpoints:

- **Regions API**: `https://platform.foodhelpline.org/api/regions`
  - Provides hierarchical data about geographic regions
  - Contains zipcode coverage information
  - Includes parent/child relationships between regions

- **Locations API**: `https://platform.foodhelpline.org/api/locations`
  - Lists locations with food resources
  - Supports filtering by resources availability
  - Supports pagination via cursor-based pagination

- **Resources API**: `https://platform.foodhelpline.org/api/resources`
  - Provides detailed information about food resources
  - Includes contact information, hours, requirements, and offerings
  - Links resources to specific locations

- **Tag Categories API**: `https://platform.foodhelpline.org/api/tagCategories`
  - Provides categories for resource tags (INFO, OFFERING, REQUIREMENT, etc.)

## Data Structure

The API returns data in a structured JSON format with the following key components:

### Regions

Regions represent geographic areas with hierarchical relationships:

```json
{
  "id": "REGION_ID",
  "name": "Region Name",
  "zipCodes": ["12345", "67890"],
  "parentId": "PARENT_REGION_ID",
  "children": [...],
  "latitude": 12.3456,
  "longitude": -78.9012,
  "resources": [...]
}
```

### Locations

Locations represent specific places where resources are available:

```json
{
  "id": "LOCATION_ID",
  "name": "Location Name",
  "addressStreet1": "123 Main St",
  "city": "Cityville",
  "state": "ST",
  "zipCode": "12345",
  "latitude": 12.3456,
  "longitude": -78.9012
}
```

### Resources

Resources represent food assistance services with detailed information:

```json
{
  "id": "RESOURCE_ID",
  "name": "Resource Name",
  "description": "Description of the resource",
  "addressStreet1": "123 Main St",
  "addressStreet2": "Suite 100",
  "city": "Cityville",
  "state": "ST",
  "zipCode": "12345",
  "latitude": 12.3456,
  "longitude": -78.9012,
  "website": "https://example.com",
  "contacts": [
    {
      "phone": "(123) 456-7890",
      "public": true
    }
  ],
  "shifts": [
    {
      "startTime": "2023-07-05T13:00:00.000Z",
      "endTime": "2023-07-05T17:00:00.000Z",
      "recurrencePattern": "DTSTART;TZID=America/New_York:20230705T130000\nRRULE:FREQ=WEEKLY;INTERVAL=1;WKST=MO;BYDAY=MO,TH,FR"
    }
  ],
  "tags": [
    {
      "id": "TAG_ID",
      "name": "Tag Name",
      "name_es": "Tag Name in Spanish",
      "tagCategoryId": "OFFERING"
    }
  ]
}
```

## Implementation Details

The scraper follows these steps:

1. **Fetch Regions**: Retrieves region data to understand geographic coverage
2. **Fetch Locations**: Retrieves location data in batches using cursor-based pagination
3. **Fetch Resources**: For each location, retrieves detailed resource information
4. **Transform Data**: Converts the API data to HSDS format
5. **Submit to Queue**: Submits each transformed resource to the processing queue

### HSDS Transformation

The scraper transforms the API data into HSDS format with the following mappings:

| FoodHelpline.org Field | HSDS Field |
|------------------------|------------|
| name | name |
| description | description |
| website | url |
| addressStreet1 | address.address_1 |
| addressStreet2 | address.address_2 |
| city | address.city |
| state | address.state_province |
| zipCode | address.postal_code |
| latitude | location.latitude |
| longitude | location.longitude |
| contacts[].phone | phones[].number |
| shifts[] | regular_schedule[] |
| tags[] | service_attributes[] |

### Hours Parsing

The scraper parses the recurrence pattern from shifts to extract operating hours:

1. Extracts the BYDAY parameter to determine which days the resource is open
2. Maps day codes (MO, TU, etc.) to full day names (Monday, Tuesday, etc.)
3. Extracts start and end times from the shift data
4. Creates regular_schedule entries for each day

### Tag Processing

Tags are processed as service attributes:

1. The tag category (INFO, OFFERING, REQUIREMENT) becomes the attribute_key
2. The tag name becomes the attribute_value

## Usage

To run the scraper:

```bash
python -m app.scraper food_helpline_org
```

## Error Handling

The scraper includes error handling for:

- API request failures
- JSON parsing errors
- Missing or malformed data

Errors are logged for debugging and monitoring purposes.

## Rate Limiting

The scraper implements batch processing to avoid overwhelming the API:

- Locations are fetched in batches (default: 50 per request)
- Resources are fetched for each location separately
- Async HTTP requests are used for efficiency
