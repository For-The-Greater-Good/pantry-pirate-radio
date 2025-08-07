# API Usage Examples

This document provides comprehensive examples of how to use the Pantry Pirate Radio API. The API follows the OpenReferral Human Services Data Specification (HSDS) and provides RESTful endpoints for accessing food security data.

## Getting Started

### Start the API Service

```bash
# Start all services with bouy
./bouy up

# Check API health
curl http://localhost:8000/api/v1/health
```

### Base URLs

**Local Development:**
- API: `http://localhost:8000/api/v1`
- Interactive Docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI Schema: `http://localhost:8000/openapi.json`

**Production (when deployed):**
- Replace `localhost:8000` with your production domain

## Authentication

Currently, the API is public and does not require authentication. All endpoints are read-only and provide access to publicly available food security data.

## Rate Limiting

- **Limit**: 100 requests per minute per IP address
- **Headers**: Rate limit information is included in response headers
- **Retry**: Use exponential backoff for rate limit errors

## Common Headers

### Request Headers
```http
Accept: application/json
Content-Type: application/json
User-Agent: YourApp/1.0
```

### Response Headers
```http
Content-Type: application/json
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1640995200
X-Request-ID: req-12345678-abcd-efgh-ijkl-123456789012
```

## Search Locations

### Geographic Search by Point and Radius

Search for food service locations within a specific radius of a point.

```http
GET /locations?latitude=40.7128&longitude=-74.0060&radius=5
```

**Note**: The current implementation uses the `/locations` endpoint for geographic searches.

**Example Response:**
```json
{
  "locations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "organization_id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Example Community Food Bank - Main Location",
      "description": "Main distribution center for emergency food assistance",
      "latitude": 40.7128,
      "longitude": -74.0060,
      "address_1": "123 Main Street",
      "address_2": null,
      "city": "New York",
      "state_province": "NY",
      "postal_code": "10001",
      "country": "US",
      "location_type": "physical",
      "transportation": "Near subway station, bus stops, street parking available",
      "created_at": "2024-01-15T10:00:00Z",
      "updated_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

### Search with Pagination

Use limit and offset parameters for pagination:

```http
GET /locations?latitude=40.7128&longitude=-74.0060&radius=10&limit=10&offset=0
```

```bash
# Get first page (10 results)
curl "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5&limit=10&offset=0"

# Get second page (next 10 results)
curl "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5&limit=10&offset=10"
```

**Query Parameters for Location Search:**
- `latitude` (required): Latitude coordinate (25.0 to 49.0)
- `longitude` (required): Longitude coordinate (-125.0 to -67.0)
- `radius` (required): Search radius in miles (max 80)
- `limit`: Maximum results to return (default: 20, max: 100)
- `offset`: Number of results to skip for pagination (default: 0)

### Example with cURL

```bash
# Basic location search
curl -X GET "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5" \
  -H "Accept: application/json"

# With pagination
curl -X GET "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5&limit=10&offset=0" \
  -H "Accept: application/json"

# Using request correlation ID for tracking
curl -X GET "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5" \
  -H "Accept: application/json" \
  -H "X-Request-ID: my-request-123"
```

## Individual Resource Endpoints

### Get Organization Details

```http
GET /organizations/{id}
```

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/organizations/550e8400-e29b-41d4-a716-446655440001" \
  -H "Accept: application/json"
```

**Response:**
```json
{
  "id": "org-example-001",
  "name": "Example Community Food Bank",
  "alternate_name": "ECFB",
  "description": "A full-service food bank serving the Example County area with emergency food assistance, nutrition education, and community outreach programs.",
  "email": "info@examplefoodbank.org",
  "url": "https://www.examplefoodbank.org",
  "tax_status": "501c3",
  "tax_id": "55-1234567",
  "year_incorporated": 1995,
  "legal_status": "Registered Charity",
  "last_modified": "2024-01-15T10:30:00Z"
}
```

### Get Service Details

```http
GET /services/{id}
```

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/services/550e8400-e29b-41d4-a716-446655440002" \
  -H "Accept: application/json"
```

### Get Location Details

```http
GET /locations/{id}
```

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/locations/550e8400-e29b-41d4-a716-446655440000" \
  -H "Accept: application/json"
```

## List Endpoints

### List All Organizations

```http
GET /organizations
```

**Query Parameters:**
- `page`: Page number (default: 1)
- `per_page`: Results per page (default: 20, max: 100)
- `sort`: Sort field (`name`, `last_modified`)
- `order`: Sort order (`asc`, `desc`)

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/organizations?limit=10&offset=0" \
  -H "Accept: application/json"
```

### List All Services

```http
GET /services
```

**Query Parameters:**
- `page`: Page number (default: 1)
- `per_page`: Results per page (default: 20, max: 100)
- `status`: Filter by service status
- `organization_id`: Filter by organization

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/services?limit=20&offset=0" \
  -H "Accept: application/json"
```

### List All Locations

```http
GET /locations
```

**Query Parameters:**
- `page`: Page number (default: 1)
- `per_page`: Results per page (default: 20, max: 100)
- `location_type`: Filter by location type (`physical`, `postal`, `virtual`)
- `organization_id`: Filter by organization

## Health and Status Endpoints

### Health Checks

#### Main Health Check
```http
GET /api/v1/health
```

**Example:**
```bash
curl http://localhost:8000/api/v1/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "correlation_id": "req-12345678-abcd-efgh-ijkl-123456789012"
}
```

#### LLM Health Check
```http
GET /api/v1/health/llm
```

**Example:**
```bash
curl http://localhost:8000/api/v1/health/llm
```

**Response:**
```json
{
  "status": "healthy",
  "provider": "openai",
  "model": "gpt-4",
  "correlation_id": "req-12345678-abcd-efgh-ijkl-123456789012"
}
```

### System Metrics

```http
GET /api/v1/metrics
```

**Example:**
```bash
curl http://localhost:8000/api/v1/metrics
```

Returns Prometheus-formatted metrics for monitoring:
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/api/v1/locations",status="200"} 1234
```

## Error Handling

All errors follow a consistent format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input parameters provided",
    "details": {
      "type": "ValidationError",
      "field": "latitude",
      "value": 91.0,
      "constraint": "Latitude must be between -90 and 90 degrees"
    },
    "timestamp": "2024-01-15T15:30:00Z",
    "request_id": "req-12345678-abcd-efgh-ijkl-123456789012"
  }
}
```

### Common Error Codes

- `VALIDATION_ERROR` (400): Invalid input parameters
- `NOT_FOUND` (404): Requested resource not found
- `RATE_LIMIT_EXCEEDED` (429): Too many requests
- `SERVICE_UNAVAILABLE` (503): Temporary system issue

See [error_responses.json](../examples/api_responses/error_responses.json) for complete error examples.

## Pagination

All list endpoints support pagination using limit and offset:

```json
{
  "locations": [...],
  "total": 150,
  "limit": 20,
  "offset": 0
}
```

**Navigation:**
- Use `limit` to control page size (max 100)
- Use `offset` to skip results for pagination
- Calculate pages: `page = (offset / limit) + 1`
- Get next page: `offset = offset + limit`

## Response Headers

All responses include useful headers:

```http
Content-Type: application/json
X-Request-ID: req-12345678-abcd-efgh-ijkl-123456789012
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1640995200
```

## Code Examples

### Python Example

```python
import requests

# Search for locations
response = requests.get(
    "http://localhost:8000/api/v1/locations",
    params={
        "latitude": 40.7128,
        "longitude": -74.0060,
        "radius": 5,
        "limit": 20
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"Found {data['total']} locations")
    
    for location in data['locations']:
        print(f"- {location['name']}")
        print(f"  {location['address_1']}, {location['city']}, {location['state_province']}")
else:
    print(f"Error: {response.status_code}")
```

### JavaScript Example

```javascript
// Search for locations using fetch
async function searchLocations(latitude, longitude, radius) {
  const params = new URLSearchParams({
    latitude,
    longitude,
    radius,
    limit: 20
  });
  
  try {
    const response = await fetch(
      `http://localhost:8000/api/v1/locations?${params}`
    );
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    console.log(`Found ${data.total} locations`);
    return data.locations;
  } catch (error) {
    console.error('Error:', error);
    return [];
  }
}

// Usage
searchLocations(40.7128, -74.0060, 5)
  .then(locations => {
    locations.forEach(location => {
      console.log(`- ${location.name}`);
    });
  });
```

## Common Use Cases

### Find Food Service Locations Near Me

```bash
# Search within 5 miles of a location
curl -X GET "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5" \
  -H "Accept: application/json"
```

### Get All Organizations

```bash
# List organizations with pagination
curl -X GET "http://localhost:8000/api/v1/organizations?limit=20&offset=0" \
  -H "Accept: application/json"
```

### Get All Services

```bash
# List services with pagination
curl -X GET "http://localhost:8000/api/v1/services?limit=20&offset=0" \
  -H "Accept: application/json"
```

### Get Service-at-Location Relationships

```bash
# List service-at-location mappings
curl -X GET "http://localhost:8000/api/v1/service-at-location?limit=20&offset=0" \
  -H "Accept: application/json"
```

## Rate Limiting Best Practices

1. **Check Rate Limit Headers**: Always check `X-RateLimit-Remaining` before making requests
2. **Implement Exponential Backoff**: Use exponential backoff when receiving 429 responses
3. **Cache Responses**: Cache API responses to reduce request frequency
4. **Use Appropriate Page Sizes**: Don't request more data than you need

## Performance Tips

1. **Use Geographic Filters**: Always use location-based filtering for better performance
2. **Limit Radius**: Use the smallest radius that meets your needs (max 80 miles)
3. **Paginate Results**: Use pagination for large result sets
4. **Filter Early**: Apply filters to reduce response size
5. **Request Only Needed Fields**: Use field selection when available

## Testing with Bouy

```bash
# Run API tests
./bouy test --pytest tests/test_api_integration_simple.py

# Check API logs
./bouy logs app

# Access API shell for debugging
./bouy shell app

# Test endpoints from within container
./bouy exec app curl http://localhost:8000/api/v1/health
```

## Support

For API support:
1. Check the [API documentation](./api.md)
2. Review the [HAARRRvest Quick Start](./haarrvest-quickstart.md)
3. Submit issues to the [GitHub repository](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)

## Next Steps

1. **Explore Interactive Documentation**: Visit `http://localhost:8000/docs` for Swagger UI
2. **Generate Data**: Run scrapers with `./bouy scraper --list` and `./bouy scraper [name]`
3. **Access Published Data**: View data at GitHub Pages after HAARRRvest publishes
4. **Monitor API**: Check metrics at `http://localhost:8000/api/v1/metrics`