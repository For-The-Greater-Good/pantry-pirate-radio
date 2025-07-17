# Pantry Pirate Radio API Documentation

## Overview

The Pantry Pirate Radio API provides access to food security resources using the Human Services Data Specification (HSDS) v3.1.1. This API serves pantry locations, services, and organizations across the continental United States.

## Base URL

```
https://your-domain.com/api/v1
```

## Authentication

Currently, no authentication is required. The API is publicly accessible for food security data.

## Rate Limiting

The API implements fair use rate limiting. Please be respectful of the service and cache responses when possible.

## Response Format

All API responses follow a consistent structure:

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

### State/ZIP Search
Find resources by state or ZIP code (planned feature):

```
GET /api/v1/locations/search?state=NJ
GET /api/v1/locations/search?zip=10001
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
    "first": "/api/v1/organizations/?page=1",
    "last": "/api/v1/organizations/?page=5",
    "next": "/api/v1/organizations/?page=2",
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
GET /api/v1/organizations/search?q=food+bank
```

**Parameters:**
- `q` (string): Search query
- `page` (int): Page number
- `per_page` (int): Items per page

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

#### Get Active Services
```
GET /api/v1/services/active
```

**Parameters:**
- `page` (int): Page number
- `per_page` (int): Items per page
- `include_locations` (bool): Include location details in response

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

#### Get Service
```
GET /api/v1/services/{service_id}
```

**Parameters:**
- `include_locations` (bool): Include location details in response

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

### Find Pantries Near Me
```
GET /api/v1/locations/search?latitude=40.7128&longitude=-74.0060&radius_miles=10&include_services=true
```

### Find All Food Banks in a State
```
GET /api/v1/organizations/search?q=food+bank&include_services=true
```

### Get All Services at a Location
```
GET /api/v1/service-at-location/location/{location_id}/services?include_details=true
```

### Find Active Food Pantries
```
GET /api/v1/services/search?q=pantry&status=active&include_locations=true
```

### Map-based Search
```
GET /api/v1/locations/search?min_latitude=40.7&max_latitude=40.8&min_longitude=-74.1&max_longitude=-74.0&include_services=true
```

## Error Handling

The API returns standard HTTP status codes:

- `200 OK`: Successful request
- `201 Created`: Resource created successfully
- `204 No Content`: Resource deleted successfully
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Validation errors
- `500 Internal Server Error`: Server error

**Error Response Format:**
```json
{
  "error": "Resource not found",
  "error_code": "NOT_FOUND",
  "details": {
    "resource_type": "organization",
    "resource_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

## Data Standards

This API follows the [Human Services Data Specification (HSDS) v3.1.1](https://docs.openreferral.org/en/latest/hsds/hsds.html) for consistent data representation across food security platforms.

## Geographic Coverage

The API covers the continental United States (coordinates: 25°N-49°N, -125°W to -67°W).

## Performance Considerations

- Responses are cached for improved performance
- Geographic searches are optimized with spatial indexes
- Pagination is required for large result sets
- Results are sorted by relevance and distance when applicable

## Support

For API support, please:
1. Check this documentation
2. Review the OpenAPI specification at `/docs`
3. Report issues on GitHub

## OpenAPI Documentation

Interactive API documentation is available at:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`