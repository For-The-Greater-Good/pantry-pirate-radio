# API Usage Examples

This document provides comprehensive examples of how to use the Pantry Pirate Radio API. The API follows the OpenReferral Human Services Data Specification (HSDS) and provides RESTful endpoints for accessing food security data.

## Base URL

```
https://api.pantrypirate.org/v1
```

For local development:
```
http://localhost:8000/api/v1
```

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

## Search Services

### Geographic Search by Point and Radius

Search for food services within a specific radius of a point.

```http
GET /services?latitude=40.7128&longitude=-74.0060&radius=5
```

**Example Response:**
```json
{
  "search_query": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "radius": 5
  },
  "services": [
    {
      "id": "svc-example-001",
      "organization": {
        "id": "org-example-001",
        "name": "Example Community Food Bank",
        "description": "A full-service food bank serving the Example County area...",
        "email": "info@examplefoodbank.org",
        "url": "https://www.examplefoodbank.org"
      },
      "service": {
        "id": "svc-example-001",
        "name": "Emergency Food Pantry",
        "description": "Free groceries and emergency food assistance...",
        "status": "active",
        "eligibility_description": "Open to all residents of Example County experiencing food insecurity"
      },
      "location": {
        "id": "loc-example-001",
        "name": "Example Community Food Bank - Main Warehouse",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "distance_miles": 0.1,
        "address": {
          "address_1": "123 Main Street",
          "city": "Example City",
          "state_province": "NY",
          "postal_code": "10001",
          "country": "US"
        }
      },
      "schedules": [
        {
          "opens_at": "09:00",
          "closes_at": "17:00",
          "byday": "MO,TU,WE,TH,FR",
          "description": "Food pantry open Monday through Friday, 9 AM to 5 PM"
        }
      ],
      "contacts": [
        {
          "name": "Sarah Johnson",
          "title": "Food Pantry Manager",
          "email": "sarah.johnson@examplefoodbank.org"
        }
      ],
      "phones": [
        {
          "number": "555-123-4567",
          "type": "voice",
          "description": "Main food pantry hotline"
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 1,
    "total_pages": 1
  },
  "metadata": {
    "timestamp": "2024-01-15T15:30:00Z",
    "query_time": 0.089,
    "total_results": 1
  }
}
```

### Geographic Search with Filters

Add filters to narrow down your search results.

```http
GET /services?latitude=40.7128&longitude=-74.0060&radius=10&status=active&service_type=food_pantry
```

**Query Parameters:**
- `latitude` (required): Latitude coordinate (25.0 to 49.0)
- `longitude` (required): Longitude coordinate (-125.0 to -67.0)
- `radius` (required): Search radius in miles (max 80)
- `status`: Service status filter (`active`, `inactive`, `defunct`, `temporarily closed`)
- `service_type`: Type of service (`food_pantry`, `hot_meals`, `mobile_pantry`, etc.)
- `languages`: Language support filter (comma-separated language codes)
- `accessibility`: Accessibility features filter
- `page`: Page number for pagination (default: 1)
- `per_page`: Results per page (default: 20, max: 100)

### Bounding Box Search

Search within a geographic bounding box.

```http
GET /services?bounds[north]=40.8&bounds[south]=40.7&bounds[east]=-73.9&bounds[west]=-74.1
```

**Example cURL:**
```bash
curl -X GET "https://api.pantrypirate.org/v1/services?bounds[north]=40.8&bounds[south]=40.7&bounds[east]=-73.9&bounds[west]=-74.1" \
  -H "Accept: application/json" \
  -H "User-Agent: MyApp/1.0"
```

## Individual Resource Endpoints

### Get Organization Details

```http
GET /organizations/{id}
```

**Example:**
```bash
curl -X GET "https://api.pantrypirate.org/v1/organizations/org-example-001" \
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
curl -X GET "https://api.pantrypirate.org/v1/services/svc-example-001" \
  -H "Accept: application/json"
```

See [service_detail.json](../examples/api_responses/service_detail.json) for a complete example response.

### Get Location Details

```http
GET /locations/{id}
```

**Example:**
```bash
curl -X GET "https://api.pantrypirate.org/v1/locations/loc-example-001" \
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
curl -X GET "https://api.pantrypirate.org/v1/organizations?page=1&per_page=10&sort=name&order=asc" \
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
curl -X GET "https://api.pantrypirate.org/v1/services?status=active&page=1&per_page=20" \
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

### Health Check

```http
GET /health
```

**Example Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 86400,
  "timestamp": "2024-01-15T15:30:00Z"
}
```

### System Metrics

```http
GET /metrics
```

Returns Prometheus-formatted metrics for monitoring.

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

All list endpoints support pagination:

```json
{
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

**Navigation:**
- Use `page` parameter to navigate between pages
- Check `total_pages` to determine the last page
- Use `per_page` to control page size (max 100)

## Response Metadata

All responses include metadata:

```json
{
  "metadata": {
    "timestamp": "2024-01-15T15:30:00Z",
    "query_time": 0.089,
    "api_version": "v1",
    "total_results": 42
  }
}
```

## Common Use Cases

### Find Food Pantries Near a Location

```bash
curl -X GET "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=2&service_type=food_pantry&status=active" \
  -H "Accept: application/json"
```

### Find Services Open Right Now

```bash
curl -X GET "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=5&open_now=true" \
  -H "Accept: application/json"
```

### Find Mobile Food Pantries

```bash
curl -X GET "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=10&service_type=mobile_pantry" \
  -H "Accept: application/json"
```

### Find Services with Spanish Support

```bash
curl -X GET "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=5&languages=es" \
  -H "Accept: application/json"
```

### Get All Services for an Organization

```bash
curl -X GET "https://api.pantrypirate.org/v1/services?organization_id=org-example-001" \
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

## Support

For API support, please:
1. Check the [troubleshooting guide](../TROUBLESHOOTING.md)
2. Review the [API documentation](./api.md)
3. Submit issues to the [GitHub repository](https://github.com/example/pantry-pirate-radio/issues)

## Next Steps

- [Quick Start Guide](./quickstart.md) - Get started with the API
- [Integration Examples](../examples/integrations/) - See language-specific examples
- [Sample Data](../examples/sample_data/) - Explore example HSDS data