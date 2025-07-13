# Pantry Pirate Radio API Documentation

## Overview

The Pantry Pirate Radio API is built using FastAPI and fully implements the OpenReferral Human Services Data Specification (HSDS). As part of the FTGG initiative, it provides a flexible system for accessing food security data through both integrated and standalone searcher services, focusing on making public resources truly accessible while respecting privacy and ethical data practices.

### Core Principles
- No collection of personal data
- Aggregation of only publicly available information
- Focus on accessibility and ease of use
- Open source and transparent operations

## HSDS Compliance

The API adheres to HSDS v3.0.0, providing:
- Standard HSDS objects (Organization, Service, Location, etc.)
- Standardized taxonomy mapping
- Geographic search capabilities
- Rich metadata and provenance tracking
- Complete data validation

## Deployment Modes

The API supports three operational modes:

1. Centralized Hub: All searchers integrated through a single FastAPI endpoint
2. Distributed Searchers: Independent Python services with direct API access
3. Hybrid Approach: Core services centralized with standalone performance-critical searchers

## Base URLs

- Centralized Mode: `/api/v1`
- Distributed Searchers:
  - Default port range: 8001-8099
  - Example: `http://localhost:8001` (Plentiful searcher)
  - Health check: `http://<host>:<port>/health`
  - Metrics: `http://<host>:<port>/metrics`
  - OpenAPI docs: `http://<host>:<port>/docs`

## Core Endpoints

### Search Food Services

`GET /api/v1/search`

Search for food services using either point-based or bounding box coordinates.

#### Query Parameters

Point-based search:
```json
{
  "lat": "number (25.0 to 49.0)",
  "lng": "number (-125.0 to -67.0)",
  "radius": "number (miles)",
  "filters": {
    "services": ["string"],
    "languages": ["string"],
    "days_open": ["string"]
  }
}
```

Bounding box search:
```json
{
  "bounds": {
    "north": "number (max 49.0)",
    "south": "number (min 25.0)",
    "east": "number (max -67.0)",
    "west": "number (min -125.0)"
  },
  "filters": {
    "services": ["string"],
    "languages": ["string"],
    "days_open": ["string"]
  }
}
```

#### Response Format

```json
{
  "services": [
    {
      "id": "uuid",
      "organization": {
        "id": "uuid",
        "name": "string",
        "description": "string",
        "email": "string",
        "url": "string",
        "tax_status": "string",
        "tax_id": "string",
        "year_incorporated": "number",
        "legal_status": "string"
      },
      "service": {
        "id": "uuid",
        "name": "string",
        "description": "string",
        "url": "string",
        "email": "string",
        "status": "active | inactive | defunct | temporarily closed",
        "interpretation_services": "string",
        "application_process": "string",
        "fees_description": "string",
        "eligibility_description": "string"
      },
      "location": {
        "id": "uuid",
        "name": "string",
        "description": "string",
        "transportation": "string",
        "latitude": "number",
        "longitude": "number",
        "location_type": "physical | postal | virtual",
        "address": {
          "address_1": "string",
          "address_2": "string",
          "city": "string",
          "region": "string",
          "state_province": "string",
          "postal_code": "string",
          "country": "string",
          "address_type": "physical | postal | virtual"
        }
      },
      "schedules": [
        {
          "id": "uuid",
          "valid_from": "date",
          "valid_to": "date",
          "opens_at": "time",
          "closes_at": "time",
          "byday": "string",
          "description": "string",
          "attending_type": "string"
        }
      ],
      "phones": [
        {
          "id": "uuid",
          "number": "string",
          "extension": "string",
          "type": "voice | fax | text | cell | video | pager | textphone",
          "description": "string"
        }
      ],
      "languages": [
        {
          "id": "uuid",
          "name": "string",
          "code": "string",
          "note": "string"
        }
      ]
    }
  ],
  "metadata": {
    "timestamp": "ISO8601",
    "coverage": {
      "bounds": {
        "north": "number",
        "south": "number",
        "east": "number",
        "west": "number"
      },
      "radius": "number"
    },
    "sources": {
      "successful": ["string"],
      "failed": ["string"],
      "skipped": ["string"]
    },
    "query_time": "number",
    "total_results": "number"
  }
}
```

### Direct HSDS Endpoints

#### Organizations

`GET /api/v1/organizations`
`GET /api/v1/organizations/{id}`

Return organization data in HSDS format.

#### Services

`GET /api/v1/services`
`GET /api/v1/services/{id}`

Return service data in HSDS format.

#### Locations

`GET /api/v1/locations`
`GET /api/v1/locations/{id}`

Return location data in HSDS format.

#### Service at Location

`GET /api/v1/service-at-location`
`GET /api/v1/service-at-location/{id}`

Return service-at-location relationships in HSDS format.

### Common Headers

#### Request Headers

```http
Accept: application/json
Accept-Language: en-US
Accept-Encoding: gzip, deflate, br
```

#### Response Headers

```http
Content-Type: application/json
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1640995200
Content-Encoding: gzip
```

### Pagination

All list endpoints support pagination:

Query Parameters:
- `page`: Page number (default: 1)
- `per_page`: Results per page (default: 20, max: 100)
- `offset`: Skip N results
- `limit`: Return N results

Response Headers:
```http
X-Total-Count: 1234
X-Page-Count: 62
Link: <https://api.example.com?page=2>; rel="next",
      <https://api.example.com?page=62>; rel="last"
```

### Error Handling

All errors follow HSDS standard format:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {
      "type": "string",
      "field": "string",
      "value": "any",
      "constraint": "string"
    },
    "timestamp": "ISO8601",
    "request_id": "uuid"
  }
}
```

Common error codes:
- `VALIDATION_ERROR`: Invalid input parameters
- `NOT_FOUND`: Requested resource not found
- `SEARCH_ERROR`: Search operation failed
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `SERVICE_UNAVAILABLE`: Temporary system issue

### Service Discovery

`GET /api/v1/searchers`

List all available searcher services and their status.

```json
{
  "searchers": [
    {
      "id": "string",
      "name": "string",
      "status": "healthy | degraded | unhealthy",
      "mode": "integrated | standalone",
      "endpoint": "string",
      "capabilities": {
        "supports_point_search": "boolean",
        "supports_bounds_search": "boolean",
        "max_radius": "number",
        "supported_filters": ["string"]
      },
      "metrics": {
        "requests_total": "number",
        "success_rate": "number",
        "average_latency": "number"
      }
    }
  ]
}
```

### Health Checks

`GET /health`

```json
{
  "status": "healthy | degraded | unhealthy",
  "version": "string",
  "uptime": "number",
  "searchers": {
    "total": "number",
    "healthy": "number",
    "degraded": "number",
    "unhealthy": "number"
  },
  "database": {
    "status": "up | down",
    "latency": "number"
  },
  "cache": {
    "status": "up | down",
    "hit_rate": "number"
  }
}
```

### Metrics

`GET /metrics`

Prometheus-formatted metrics including:
- Request counts and latencies
- Search result counts
- Cache hit rates
- Error rates
- Resource utilization

### Data Export

`GET /api/v1/export`

Export data in various formats:

Query Parameters:
```json
{
  "format": "json | sqlite | csv",
  "filters": {
    "date_range": {
      "start": "ISO8601",
      "end": "ISO8601"
    },
    "region": {
      "bounds": {
        "north": "number",
        "south": "number",
        "east": "number",
        "west": "number"
      }
    },
    "sources": ["string"]
  },
  "options": {
    "compression": "boolean",
    "include_metadata": "boolean",
    "split_by_region": "boolean",
    "max_file_size": "number"
  }
}
```

## Implementation Notes

### Rate Limiting

- Default: 100 requests per minute per IP
- Configurable per searcher and deployment mode
- Rate limit headers included in all responses
- Exponential backoff recommended for retries

### Caching

- Results cached for 5 minutes by default
- Cache-Control headers indicate TTL
- ETag support for conditional requests
- Geographic region-based cache partitioning

### Authentication

- API key required for write operations
- JWT support for authenticated sessions
- Role-based access control available
- CORS enabled for web clients

### Compression

Supported compression methods:
- gzip (preferred)
- deflate
- brotli

Set Accept-Encoding header to specify preference.

### Geographic Implementation

- Coordinates clamped to US bounds
- Sub-grid generation for large areas
- PostGIS integration for spatial queries
- Search radius limited to 80 miles
- Results deduplicated by location

### Monitoring

- Prometheus metrics exposition
- Health check endpoints
- Detailed error tracking
- Request tracing through correlation IDs
- Performance monitoring via OpenTelemetry

### Schema Validation

- Full HSDS schema validation
- Custom validators for business rules
- Error details in validation failures
- Strict mode available for testing

## API Versioning

- Major version in URL path (/v1/, /v2/)
- Minor versions via Accept header
- Deprecation schedule in headers
- Backwards compatibility maintained

Version lifecycle:
1. Active: Current supported version
2. Deprecated: 6-month notice period
3. Sunset: 3-month grace period
4. Retired: 410 Gone response

## API Usage Examples

### Basic Food Service Search

Search for food services within 5 miles of downtown Seattle:

```bash
curl -X GET "http://localhost:8000/api/v1/search?lat=47.6062&lng=-122.3321&radius=5" \
  -H "Accept: application/json"
```

### Search with Filters

Search for food pantries that offer Spanish language services:

```bash
curl -X GET "http://localhost:8000/api/v1/search" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 47.6062,
    "lng": -122.3321,
    "radius": 10,
    "filters": {
      "services": ["food_pantry"],
      "languages": ["Spanish"]
    }
  }'
```

### Bounding Box Search

Search for all food services in a specific area:

```bash
curl -X GET "http://localhost:8000/api/v1/search" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "bounds": {
      "north": 47.7,
      "south": 47.5,
      "east": -122.2,
      "west": -122.4
    }
  }'
```

### Python Example

```python
import requests
import json

# Search for food services
response = requests.get(
    "http://localhost:8000/api/v1/search",
    params={
        "lat": 47.6062,
        "lng": -122.3321,
        "radius": 5
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"Found {len(data['services'])} food services")

    for service in data['services']:
        org = service['organization']
        location = service['location']
        print(f"- {org['name']} at {location['address']['address_1']}")
else:
    print(f"Error: {response.status_code}")
```

### JavaScript Example

```javascript
// Search for food services using fetch
async function searchFoodServices(lat, lng, radius) {
  try {
    const response = await fetch(
      `http://localhost:8000/api/v1/search?lat=${lat}&lng=${lng}&radius=${radius}`
    );

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data.services;
  } catch (error) {
    console.error('Error searching for food services:', error);
    return [];
  }
}

// Usage
searchFoodServices(47.6062, -122.3321, 5)
  .then(services => {
    console.log(`Found ${services.length} food services`);
    services.forEach(service => {
      console.log(`- ${service.organization.name}`);
    });
  });
```

### Get Specific Organization

```bash
curl -X GET "http://localhost:8000/api/v1/organizations/12345678-1234-1234-1234-123456789012" \
  -H "Accept: application/json"
```

### List All Services with Pagination

```bash
curl -X GET "http://localhost:8000/api/v1/services?page=1&per_page=20" \
  -H "Accept: application/json"
```

### Health Check

```bash
curl -X GET "http://localhost:8000/health" \
  -H "Accept: application/json"
```

### Export Data

```bash
curl -X GET "http://localhost:8000/api/v1/export?format=json" \
  -H "Accept: application/json" \
  -o food_services.json
```

## Documentation

- OpenAPI specification: `/docs`
- Swagger UI: `/docs/swagger`
- ReDoc: `/docs/redoc`
- JSON Schema: `/docs/schema`
