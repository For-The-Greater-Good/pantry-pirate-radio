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

## Getting Started

### Start the API Service

```bash
# Start all services including the API
./bouy up

# The API will be available at:
# - http://localhost:8000/api/v1  (REST API)
# - http://localhost:8000/docs    (Interactive Swagger UI)
# - http://localhost:8000/redoc   (ReDoc documentation)
# - http://localhost:8000/openapi.json (OpenAPI schema)

# Check API health
curl http://localhost:8000/api/v1/health
```

## Base URLs

### Local Development
- API Base: `http://localhost:8000/api/v1`
- Documentation: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/v1/health`
- Metrics: `http://localhost:8000/api/v1/metrics`

### Production (when deployed)
- API Base: `https://api.yourdomain.com/api/v1`
- Use HTTPS for all production requests

## Core Endpoints

### Search Locations by Geographic Coordinates

`GET /api/v1/locations`

Search for food service locations using geographic coordinates and radius.

**Note**: The current implementation uses the `/locations` endpoint for geographic searches.

#### Query Parameters

Geographic search parameters:
- `latitude`: number (25.0 to 49.0) - Search center latitude
- `longitude`: number (-125.0 to -67.0) - Search center longitude  
- `radius`: number - Search radius in miles (max 80)
- `limit`: number - Maximum results to return (default 20, max 100)
- `offset`: number - Pagination offset

**Example**:
```
GET /api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5&limit=20
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

### Health Check Endpoints

#### Main Health Check
`GET /api/v1/health`

Returns the overall health status of the API:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "correlation_id": "req-12345678-abcd-efgh-ijkl-123456789012"
}
```

#### LLM Health Check  
`GET /api/v1/health/llm`

Checks the LLM provider connection:

```json
{
  "status": "healthy",
  "provider": "openai",
  "model": "gpt-4",
  "correlation_id": "req-12345678-abcd-efgh-ijkl-123456789012"
}
```

### Prometheus Metrics

`GET /api/v1/metrics`

Returns Prometheus-formatted metrics for monitoring:

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/api/v1/locations",status="200"} 1234

# HELP http_request_duration_seconds HTTP request latency
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.1"} 950
http_request_duration_seconds_bucket{le="0.5"} 1200
```

Key metrics tracked:
- Request counts by endpoint and status
- Request latency histograms
- Active request count
- Error rates by type
- Database query performance

### CORS Configuration

The API supports Cross-Origin Resource Sharing (CORS) with:
- Allowed methods: `GET`, `HEAD`, `OPTIONS`
- Allowed headers: All headers plus `Content-Type`, `X-Request-ID`
- Exposed headers: `X-Request-ID`
- Max age: 600 seconds

Configure allowed origins in `.env`:
```bash
CORS_ORIGINS=["http://localhost:3000", "https://yourdomain.com"]
```

### Request Correlation

All requests are assigned a correlation ID for tracing:

- Header: `X-Request-ID`  
- If not provided, one is generated automatically
- Returned in all responses for tracking

```bash
curl -H "X-Request-ID: my-request-123" \
  http://localhost:8000/api/v1/health

# Response includes:
# X-Request-ID: my-request-123
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

The API is currently read-only and does not require authentication. All endpoints are publicly accessible.

Future versions may include:
- API key authentication for rate limiting
- JWT tokens for user sessions
- OAuth2 for third-party integrations

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

### Basic Location Search

Search for food service locations within 5 miles of downtown Seattle:

```bash
curl -X GET "http://localhost:8000/api/v1/locations?latitude=47.6062&longitude=-122.3321&radius=5" \
  -H "Accept: application/json"
```

**Expected Response**:
```json
{
  "locations": [
    {
      "id": "loc-123",
      "name": "Seattle Food Bank",
      "latitude": 47.6062,
      "longitude": -122.3321,
      "address_1": "123 Main St",
      "city": "Seattle",
      "state_province": "WA",
      "postal_code": "98101"
    }
  ],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

### Search with Pagination

Use limit and offset for pagination:

```bash
# Get first 10 results
curl -X GET "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=10&limit=10&offset=0"

# Get next 10 results
curl -X GET "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=10&limit=10&offset=10"
```

### Get All Organizations

List all organizations in the database:

```bash
curl -X GET "http://localhost:8000/api/v1/organizations?limit=20&offset=0" \
  -H "Accept: application/json"
```

### Python Example

```python
import requests
import json

# Search for food service locations
response = requests.get(
    "http://localhost:8000/api/v1/locations",
    params={
        "latitude": 47.6062,
        "longitude": -122.3321,
        "radius": 5,
        "limit": 20
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"Found {data['total']} locations")

    for location in data['locations']:
        print(f"- {location['name']} at {location['address_1']}")
        print(f"  {location['city']}, {location['state_province']} {location['postal_code']}")
else:
    error = response.json()
    print(f"Error: {error.get('detail', 'Unknown error')}")
```

### JavaScript Example

```javascript
// Search for food service locations using fetch
async function searchLocations(latitude, longitude, radius) {
  try {
    const params = new URLSearchParams({
      latitude,
      longitude,
      radius,
      limit: 20
    });
    
    const response = await fetch(
      `http://localhost:8000/api/v1/locations?${params}`
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data.locations;
  } catch (error) {
    console.error('Error searching for locations:', error);
    return [];
  }
}

// Usage
searchLocations(47.6062, -122.3321, 5)
  .then(locations => {
    console.log(`Found ${locations.length} locations`);
    locations.forEach(location => {
      console.log(`- ${location.name} at ${location.address_1}`);
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

### Health Checks

```bash
# Basic health check
curl -X GET "http://localhost:8000/api/v1/health" \
  -H "Accept: application/json"

# Response:
# {
#   "status": "healthy",
#   "version": "1.0.0",
#   "correlation_id": "req-abc123"
# }

# LLM provider health check
curl -X GET "http://localhost:8000/api/v1/health/llm" \
  -H "Accept: application/json"

# Response:
# {
#   "status": "healthy",
#   "provider": "openai",
#   "model": "gpt-4",
#   "correlation_id": "req-def456"
# }
```

### Monitoring with Bouy

```bash
# Check API service status
./bouy ps

# View API logs
./bouy logs app

# Test API endpoints
./bouy exec app curl http://localhost:8000/api/v1/health

# Run API tests
./bouy test --pytest tests/test_api_integration_simple.py
```

## Interactive Documentation

The API provides interactive documentation using FastAPI's built-in tools:

### Swagger UI
Access at: `http://localhost:8000/docs`
- Interactive API explorer
- Try out endpoints directly
- View request/response schemas
- Download OpenAPI specification

### ReDoc
Access at: `http://localhost:8000/redoc`
- Clean, readable API documentation
- Detailed schema definitions
- Code generation support

### OpenAPI Schema
Access at: `http://localhost:8000/openapi.json`
- Machine-readable API specification
- Use for client code generation
- Import into Postman or similar tools

## Environment Configuration

Key environment variables for API configuration:

```bash
# API Settings
API_PREFIX=/api/v1
CORS_ORIGINS=["*"]  # Configure for production
CORS_ALLOW_CREDENTIALS=false

# Database
DATABASE_URL=postgresql+psycopg2://user:pass@db:5432/pantry_pirate_radio

# Redis Cache
REDIS_URL=redis://cache:6379/0

# LLM Provider
LLM_PROVIDER=openai
OPENROUTER_API_KEY=your_key_here
```
