# Pantry Pirate Radio API Documentation

> **📖 Note**: This is the complete API reference. For the full project documentation including architecture, scrapers, deployment, and more, see the **[Documentation Hub](docs/INDEX.md)**.

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Base URL](#base-url)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Response Format](#response-format)
- [Geographic Search Features](#geographic-search-features)
- [Endpoints](#endpoints)
  - [Organizations](#organizations)
  - [Locations](#locations)
  - [Services](#services)
  - [Service-at-Location](#service-at-location)
- [Common Use Cases](#common-use-cases)
- [Error Handling](#error-handling)
- [Data Standards](#data-standards)
- [Geographic Coverage](#geographic-coverage)
- [Performance Considerations](#performance-considerations)
- [CORS Configuration](#cors-configuration)
- [Security Headers](#security-headers)
- [Request Tracking](#request-tracking)
- [Health Check Endpoints](#health-check-endpoints)
- [Metrics Endpoint](#metrics-endpoint)
- [OpenAPI Documentation](#openapi-documentation)
- [Support](#support)

## Overview

The Pantry Pirate Radio API provides **read-only access** to food security resources using the Human Services Data Specification (HSDS) v3.1.1. This API serves pantry locations, services, and organizations across the continental United States with safe, non-destructive data exploration capabilities.

## Getting Started

### Starting the API Server

Use the bouy command to start the API and all required services:

```bash
# Start all services (development mode)
./bouy up

# Start in production mode
./bouy up --prod

# Check service status
./bouy ps
```

Once started, the API will be available at:
- **Local**: `http://localhost:8000/api/v1`
- **Production**: `https://api.for-the-gg.org/api/v1`

## Base URL

```
http://localhost:8000/api/v1
```

For production deployments, use `https://api.for-the-gg.org`.

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

## Data Quality Fields

As of Issues #362-#369, all organization, location, and service records include data quality and validation fields to ensure high-quality food security information:

### Confidence Score
- **confidence_score** (integer, 0-100): Indicates the data quality confidence level
  - **80-100**: High confidence - verified data with complete information
  - **50-79**: Medium confidence - partial data or needs verification
  - **0-49**: Low confidence - minimal data or significant issues
  - **< 10**: Rejected - data deemed unreliable (not returned by default in API responses)

### Validation Fields
- **validation_status** (string): Current validation state of the record
  - `"verified"`: Data has been validated and confirmed
  - `"needs_review"`: Data requires manual review or additional verification
  - `"rejected"`: Data failed validation (confidence score < 10)

- **validation_notes** (object): Additional validation details and metadata
  - May include reasons for rejection, verification sources, or review notes
  - Structure varies based on validation type and issues found

### Location-Specific Fields
- **geocoding_source** (string, locations only): Provider used for geocoding
  - Indicates which service validated the location coordinates
  - Examples: `"arcgis"`, `"google_maps"`, `"nominatim"`, `"census"`
  - Helps track geocoding accuracy and reliability

### API Behavior
- Records with confidence scores below 10 are automatically filtered from standard API responses
- This ensures only reliable data is served to API consumers
- Future API versions may support filtering by confidence score ranges

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

**Response Fields:**
Each organization in the response includes:
- `id` (UUID): Unique identifier
- `name` (string): Organization name
- `description` (string): Organization description
- `url` (string): Organization website
- `email` (string): Contact email
- `confidence_score` (integer): Data quality score (0-100)
- `validation_status` (string): Validation state (verified/needs_review/rejected)
- `validation_notes` (object): Additional validation metadata
- `services` (array): Associated services (if include_services=true)
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp

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
      "confidence_score": 85,
      "validation_status": "verified",
      "validation_notes": {"source": "manual_review", "verified_date": "2024-01-15"},
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

**Response Fields:**
Each location in the response includes:
- `id` (UUID): Unique identifier
- `name` (string): Location name
- `description` (string): Location description
- `latitude` (float): Geographic latitude
- `longitude` (float): Geographic longitude
- `confidence_score` (integer): Data quality score (0-100)
- `validation_status` (string): Validation state (verified/needs_review/rejected)
- `validation_notes` (object): Additional validation metadata
- `geocoding_source` (string): Provider used for geocoding (e.g., arcgis, google_maps)
- `distance` (string): Distance from search point (only in geographic searches)
- `services` (array): Associated services (if include_services=true)
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp

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
      "confidence_score": 92,
      "validation_status": "verified",
      "validation_notes": {"geocoding_confidence": "high"},
      "geocoding_source": "arcgis",
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

**Response Fields:**
Each service in the response includes:
- `id` (UUID): Unique identifier
- `organization_id` (UUID): Parent organization ID
- `name` (string): Service name
- `description` (string): Service description
- `url` (string): Service-specific URL
- `email` (string): Service contact email
- `status` (string): Service status (active/inactive/defunct/temporarily closed)
- `confidence_score` (integer): Data quality score (0-100)
- `validation_status` (string): Validation state (verified/needs_review/rejected)
- `validation_notes` (object): Additional validation metadata
- `locations` (array): Associated locations (if include_locations=true)
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp

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

**Note:** This is a convenience endpoint that internally calls the list services endpoint with `status=active`. This endpoint must be defined before the `/{service_id}` endpoint to avoid route conflicts.

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
      "confidence_score": 75,
      "validation_status": "needs_review",
      "validation_notes": {"missing_fields": ["phone", "hours"]},
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
- Supports multiple providers (ArcGIS, Google Maps, Nominatim, Census)
- Implements intelligent fallback - tries ALL providers before accepting failure
- Detects and corrects invalid (0,0) coordinates automatically
- TTL-based caching with rate limiting to respect API quotas
- Tracks geocoding source in `geocoding_source` field for transparency
- Configurable via environment variables

## Performance Considerations

- Responses are cached using Redis for improved performance
- Geographic searches are optimized with PostGIS spatial indexes
- Pagination is enforced with a maximum of 100 items per page
- Distance calculations use efficient PostGIS ST_Distance functions
- Database queries use async SQLAlchemy for non-blocking operations
- Connection pooling with configurable limits for database efficiency
- All endpoints include correlation IDs for request tracing
- Query optimization with selective eager loading of relationships

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
2. Review the interactive OpenAPI specification at:
   - **Local**: `http://localhost:8000/docs`
   - **Production**: `https://api.for-the-gg.org/docs`
3. Test endpoints directly using the Swagger UI
4. Report issues on [GitHub](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
5. Consult the [Bouy Command Reference](BOUY.md) for Docker fleet management

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
### Local Development
- **Swagger UI**: `http://localhost:8000/docs` - Interactive API exploration with try-it-out features
- **ReDoc**: `http://localhost:8000/redoc` - Alternative documentation interface with better readability
- **OpenAPI JSON**: `http://localhost:8000/openapi.json` - Machine-readable API specification

### Production
- **Swagger UI**: `https://api.for-the-gg.org/docs` - Interactive API exploration with try-it-out features
- **ReDoc**: `https://api.for-the-gg.org/redoc` - Alternative documentation interface with better readability
- **OpenAPI JSON**: `https://api.for-the-gg.org/openapi.json` - Machine-readable API specification

The Swagger UI provides an interactive interface where you can:
- Browse all available endpoints
- View request/response schemas
- Test endpoints directly from the browser
- Download the OpenAPI specification

## Related Documentation

- **[Documentation Hub](docs/INDEX.md)** - Complete project documentation index
- **[Architecture Overview](docs/architecture.md)** - System design and components
- **[API Examples](docs/api-examples.md)** - Practical usage examples
- **[HSDS Specification](docs/hsds_index.md)** - Human Services Data Specification details
- **[Bouy Commands](BOUY.md)** - Docker fleet management for running the API