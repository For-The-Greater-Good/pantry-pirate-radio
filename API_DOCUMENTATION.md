# Pantry Pirate Radio API Documentation

## Overview

The Pantry Pirate Radio API provides **read-only access** to food security resources using the Human Services Data Specification (HSDS) v3.1.1. This API serves pantry locations, services, and organizations across the continental United States with safe, non-destructive data exploration capabilities.

## Base URL

```
http://localhost:8000/api/v1
```

For production deployments, replace `localhost:8000` with your domain.

## Authentication

The API is publicly accessible and read-only. No authentication is required for accessing food security data.

## Rate Limiting

The API implements fair use rate limiting. Please be respectful of the service and cache responses when possible. Geographic searches are optimized with spatial indexes for efficient queries.

## Response Format

All API responses follow a consistent paginated structure:

```json
{
  "count": 25,
  "total": 123,
  "per_page": 25,
  "current_page": 1,
  "total_pages": 5,
  "links": {
    "first": "/api/v1/locations?page=1",
    "last": "/api/v1/locations?page=5",
    "next": "/api/v1/locations?page=2",
    "prev": null
  },
  "data": [...]
}
```

### Response Fields

- **count**: Number of items in the current page
- **total**: Total number of items across all pages
- **per_page**: Maximum items per page (25 default, 100 max)
- **current_page**: Current page number
- **total_pages**: Total number of pages available
- **links**: Pagination links for navigation
  - **first**: Link to first page
  - **last**: Link to last page
  - **next**: Link to next page (null if on last page)
  - **prev**: Link to previous page (null if on first page)
- **data**: Array of resource objects

## Geographic Search Features

### Radius Search
Find resources within a specific distance from a point:

```
GET /api/v1/locations/search?latitude=40.7128&longitude=-74.0060&radius_miles=10
```

### Bounding Box Search
Find resources within a geographic rectangle:

```
GET /api/v1/locations/search?min_latitude=40.7&max_latitude=40.8&min_longitude=-74.1&max_longitude=-74.0
```

### Address-Based Search
Combine geographic search parameters with other filters:

```
GET /api/v1/locations/search?latitude=40.7128&longitude=-74.0060&radius_miles=10&organization_id=550e8400-e29b-41d4-a716-446655440000
```

## Endpoints

### Organizations

Organizations represent the entities that provide food security services.

#### List Organizations
```
GET /api/v1/organizations/
```

**Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 25, max: 100)
- `name` (string): Filter by organization name
- `include_services` (bool): Include service details in response

**Example Response:**
```json
{
  "count": 10,
  "total": 45,
  "per_page": 10,
  "current_page": 1,
  "total_pages": 5,
  "links": {
    "first": "/api/v1/organizations?page=1",
    "last": "/api/v1/organizations?page=5",
    "next": "/api/v1/organizations?page=2",
    "prev": null
  },
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Community Food Bank",
      "description": "Providing food assistance to families in need",
      "url": "https://example.com",
      "email": "info@example.com",
      "services": null,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### Get Organization
```
GET /api/v1/organizations/{organization_id}
```

**Parameters:**
- `include_services` (bool): Include service details in response

#### Search Organizations
```
GET /api/v1/organizations/search
```

**Parameters:**
- `q` (string): Search query (required)
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 25, max: 100)

### Locations

Locations represent physical or virtual places where services are provided.

#### List Locations
```
GET /api/v1/locations/
```

**Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 25, max: 100)
- `organization_id` (UUID): Filter by organization ID
- `include_services` (bool): Include service details in response

#### Geographic Search
```
GET /api/v1/locations/search
```

**Parameters:**
- `latitude` (float): Latitude for radius search
- `longitude` (float): Longitude for radius search
- `radius_miles` (float): Search radius in miles (max: 100)
- `min_latitude` (float): Minimum latitude for bounding box
- `max_latitude` (float): Maximum latitude for bounding box
- `min_longitude` (float): Minimum longitude for bounding box
- `max_longitude` (float): Maximum longitude for bounding box
- `organization_id` (UUID): Filter by organization ID
- `include_services` (bool): Include service details in response

**Example Response:**
```json
{
  "count": 5,
  "total": 5,
  "per_page": 25,
  "current_page": 1,
  "total_pages": 1,
  "links": {
    "first": "/api/v1/locations/search?page=1",
    "last": "/api/v1/locations/search?page=1",
    "next": null,
    "prev": null
  },
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Main Distribution Center",
      "description": "Primary food distribution location",
      "latitude": 40.7128,
      "longitude": -74.0060,
      "distance": "2.3mi",
      "services": null,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### Get Location
```
GET /api/v1/locations/{location_id}
```

**Parameters:**
- `include_services` (bool): Include service details in response

### Services

Services represent the specific assistance programs offered by organizations.

#### List Services
```
GET /api/v1/services/
```

**Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 25, max: 100)
- `organization_id` (UUID): Filter by organization ID
- `status` (string): Filter by service status (active, inactive, defunct, temporarily closed)
- `include_locations` (bool): Include location details in response

#### Get Service
```
GET /api/v1/services/{service_id}
```

**Parameters:**
- `include_locations` (bool): Include location details in response

#### Get Active Services
```
GET /api/v1/services/active
```

**Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 25, max: 100)
- `include_locations` (bool): Include location details in response

**Note:** This is a convenience endpoint that internally calls the list services endpoint with `status=active`.

#### Search Services
```
GET /api/v1/services/search?q=food+pantry
```

**Parameters:**
- `q` (string): Search query
- `page` (int): Page number
- `per_page` (int): Items per page
- `status` (string): Filter by service status
- `include_locations` (bool): Include location details in response

**Example Response:**
```json
{
  "count": 3,
  "total": 15,
  "per_page": 25,
  "current_page": 1,
  "total_pages": 1,
  "links": {
    "first": "/api/v1/services/search?page=1",
    "last": "/api/v1/services/search?page=1",
    "next": null,
    "prev": null
  },
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "organization_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Emergency Food Pantry",
      "description": "Provides emergency food assistance to families",
      "url": "https://example.com/pantry",
      "email": "pantry@example.com",
      "status": "active",
      "locations": null,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### Service-at-Location

Service-at-location represents the relationship between services and their locations.

#### List Service-at-Location
```
GET /api/v1/service-at-location/
```

**Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 25, max: 100)
- `service_id` (UUID): Filter by service ID
- `location_id` (UUID): Filter by location ID
- `organization_id` (UUID): Filter by organization ID
- `include_details` (bool): Include service and location details

#### Get Service-at-Location by ID
```
GET /api/v1/service-at-location/{service_at_location_id}
```

**Parameters:**
- `include_details` (bool): Include service and location details

#### Get Services at Location
```
GET /api/v1/service-at-location/location/{location_id}/services
```

**Parameters:**
- `page` (int): Page number
- `per_page` (int): Items per page
- `include_details` (bool): Include service and location details

#### Get Locations for Service
```
GET /api/v1/service-at-location/service/{service_id}/locations
```

**Parameters:**
- `page` (int): Page number
- `per_page` (int): Items per page
- `include_details` (bool): Include service and location details

## Common Use Cases

### Find Pantries Near Me (Radius Search)
```
GET /api/v1/locations/search?latitude=40.7128&longitude=-74.0060&radius_miles=10&include_services=true
```

Returns all locations within 10 miles of the specified coordinates, with service details included.

### Map-based Search (Bounding Box)
```
GET /api/v1/locations/search?min_latitude=40.7&max_latitude=40.8&min_longitude=-74.1&max_longitude=-74.0&include_services=true
```

Returns all locations within the specified geographic rectangle, useful for map viewport queries.

### Find Food Banks by Name
```
GET /api/v1/organizations?name=food+bank&include_services=true
```

Filter organizations by name with service details.

### Search for Specific Services
```
GET /api/v1/services/search?q=pantry&include_locations=true
```

Search services by keyword with location details.

### Get All Active Services
```
GET /api/v1/services/active?include_locations=true
```

Returns only active services with their locations.

### Get All Services at a Location
```
GET /api/v1/service-at-location/location/{location_id}/services?include_details=true
```

Returns all services offered at a specific location.

### Get All Locations for a Service
```
GET /api/v1/service-at-location/service/{service_id}/locations?include_details=true
```

Returns all locations where a specific service is offered.

## Error Handling

The API returns standard HTTP status codes:

- `200 OK`: Successful request
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `405 Method Not Allowed`: HTTP method not allowed
- `422 Unprocessable Entity`: Validation errors
- `500 Internal Server Error`: Server error

**Error Response Format:**
```json
{
  "error": "HTTPException",
  "message": "Organization not found",
  "status_code": 404,
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Validation Error Response (422):**
```json
{
  "error": "RequestValidationError",
  "message": "Invalid parameter value",
  "status_code": 422,
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

All error responses include a `correlation_id` for request tracking and debugging.

## Data Standards

This API follows the [Human Services Data Specification (HSDS) v3.1.1](https://docs.openreferral.org/en/latest/hsds/hsds.html) for consistent data representation across food security platforms.

### HSDS Compliance

All API responses conform to HSDS v3.1.1 specifications:
- Organization records include required fields: id, name, description
- Location records include geographic coordinates when available
- Service records include status tracking (active, inactive, defunct, temporarily closed)
- Service-at-location relationships properly link services to their delivery locations
- All timestamps follow ISO 8601 format
- UUIDs are used for all resource identifiers

## Geographic Coverage

The API covers the continental United States (coordinates: 25°N-49°N, -125°W to -67°W).

### Geocoding Service

The application includes a unified geocoding service for address resolution:
- Supports multiple providers (ArcGIS, Nominatim)
- Implements caching to reduce API calls
- Enforces rate limiting to respect API quotas
- Provides fallback mechanisms for reliability
- Configurable via environment variables

## Performance Considerations

- Responses are cached using Redis for improved performance
- Geographic searches are optimized with PostGIS spatial indexes
- Pagination is enforced with a maximum of 100 items per page
- Distance calculations use efficient PostGIS ST_Distance functions
- Database queries use connection pooling with configurable limits
- All endpoints include correlation IDs for request tracing

## CORS Configuration

The API supports Cross-Origin Resource Sharing (CORS) with the following configuration:
- **Allowed Methods**: GET, HEAD, OPTIONS
- **Allowed Headers**: All headers including Content-Type and X-Request-ID
- **Exposed Headers**: X-Request-ID
- **Max Age**: 600 seconds (10 minutes)
- **Credentials**: Not allowed by default

## Security Headers

The API includes security headers for protection:
- **X-Request-ID**: Correlation ID for request tracking
- Additional security headers applied by middleware

## Request Tracking

Every API request is assigned a unique correlation ID that:
- Is returned in the `X-Request-ID` response header
- Is included in all error responses
- Can be used for debugging and log correlation
- Follows the request through all middleware layers

## Support

For API support, please:
1. Check this documentation
2. Review the OpenAPI specification at `/docs`
3. Report issues on GitHub

## Health Check Endpoints

### Main Health Check
```
GET /api/v1/health
```

Returns the overall health status of the API.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Database Health Check
```
GET /api/v1/health/db
```

Checks PostgreSQL database connectivity and PostGIS extension.

**Response:**
```json
{
  "status": "healthy",
  "database": "postgresql",
  "version": "PostgreSQL 16.1...",
  "postgis_version": "POSTGIS=\"3.4.0\"...",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Redis Health Check
```
GET /api/v1/health/redis
```

Checks Redis cache connectivity and status.

**Response:**
```json
{
  "status": "healthy",
  "redis_version": "7.2.3",
  "connected_clients": "2",
  "used_memory_human": "1.24M",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### LLM Health Check
```
GET /api/v1/health/llm
```

Checks LLM provider connectivity (OpenAI/Claude).

**Response:**
```json
{
  "status": "healthy",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Metrics Endpoint

```
GET /api/v1/metrics
```

Exposes Prometheus metrics for monitoring. Returns metrics in Prometheus text format.

## OpenAPI Documentation

Interactive API documentation is available at:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`