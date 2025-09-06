# Map Search API Documentation

## Overview
The Map Search API endpoint (`/api/v1/map/search`) provides comprehensive location search functionality with full-text search, geographic filtering, and multiple output formats optimized for map integration.

## Endpoint
```
GET /api/v1/map/search
```

## Features

### Full-Text Search
- Search across location names, organizations, addresses, services, and descriptions
- Multi-term search with AND logic (all terms must match)
- Case-insensitive matching

### Geographic Filtering
- **Bounding Box**: Define a rectangular area with min/max latitude and longitude
- **Radius Search**: Search within a specified radius from a center point
- **State Filter**: Filter by US state code

### Service & Schedule Filtering
- Filter by services offered (OR logic for multiple services)
- Filter by languages supported
- Filter by days of operation
- Filter by currently open locations

### Quality Filters
- Minimum confidence score
- Validation status
- Locations with multiple sources

### Output Formats
- **full**: Complete location data with all sources (default)
- **compact**: Minimal data for map markers
- **geojson**: GeoJSON FeatureCollection for map libraries

## Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `q` | string | Search query text | `food bank` |
| `min_lat` | float | Minimum latitude for bounding box | `40.7` |
| `min_lng` | float | Minimum longitude for bounding box | `-74.0` |
| `max_lat` | float | Maximum latitude for bounding box | `40.8` |
| `max_lng` | float | Maximum longitude for bounding box | `-73.9` |
| `center_lat` | float | Center latitude for radius search | `40.7128` |
| `center_lng` | float | Center longitude for radius search | `-74.0060` |
| `radius` | float | Search radius in miles (max 500) | `5` |
| `state` | string | State code (2 letters) | `CA` |
| `services` | string | Comma-separated services | `food,clothing` |
| `languages` | string | Comma-separated languages | `spanish,mandarin` |
| `schedule_days` | string | Comma-separated days | `monday,friday` |
| `open_now` | boolean | Filter to currently open | `true` |
| `confidence_min` | integer | Minimum confidence (0-100) | `70` |
| `validation_status` | string | Validation status | `validated` |
| `has_multiple_sources` | boolean | Multiple sources only | `true` |
| `format` | string | Output format | `compact` |
| `page` | integer | Page number (1-based) | `2` |
| `per_page` | integer | Items per page (1-1000) | `50` |

## Example Queries

### Basic Text Search
```
GET /api/v1/map/search?q=food%20bank&per_page=10
```

### Geographic Bounding Box
```
GET /api/v1/map/search?min_lat=40.7&max_lat=40.8&min_lng=-74.0&max_lng=-73.9
```

### Radius Search
```
GET /api/v1/map/search?center_lat=40.7128&center_lng=-74.0060&radius=5
```

### Combined Filters
```
GET /api/v1/map/search?q=food&state=NY&confidence_min=70&format=compact
```

### GeoJSON Output
```
GET /api/v1/map/search?q=pantry&format=geojson&per_page=100
```

## Response Formats

### Full Format (Default)
```json
{
  "metadata": {
    "generated": "2025-09-06T12:00:00Z",
    "total_locations": 150,
    "total_source_records": 200,
    "multi_source_locations": 50,
    "states_covered": 5,
    "coverage": "5 US states/territories"
  },
  "locations": [
    {
      "id": "uuid",
      "lat": 40.7128,
      "lng": -74.0060,
      "name": "Food Pantry Name",
      "org": "Organization Name",
      "address": "123 Main St, New York, NY, 10001",
      "city": "New York",
      "state": "NY",
      "zip": "10001",
      "phone": "555-1234",
      "website": "https://example.org",
      "email": "info@example.org",
      "description": "Food assistance services",
      "source_count": 2,
      "sources": [...],
      "confidence_score": 85,
      "validation_status": "validated",
      "geocoding_source": "google",
      "location_type": "food_pantry"
    }
  ],
  "total": 150,
  "page": 1,
  "per_page": 10,
  "has_more": true
}
```

### Compact Format
```json
{
  "locations": [
    {
      "id": "uuid",
      "lat": 40.7128,
      "lng": -74.0060,
      "name": "Food Pantry Name",
      "confidence": 85
    }
  ]
}
```

### GeoJSON Format
```json
{
  "locations": [{
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {
          "type": "Point",
          "coordinates": [-74.0060, 40.7128]
        },
        "properties": {
          "id": "uuid",
          "name": "Food Pantry Name",
          "org": "Organization Name",
          "address": "123 Main St",
          "city": "New York",
          "state": "NY",
          "services": "food, clothing",
          "confidence": 85
        }
      }
    ],
    "properties": {
      "total": 150,
      "returned": 10,
      "offset": 0,
      "limit": 10
    }
  }]
}
```

## Database Indexes Required

For optimal performance, the following database indexes are required:

### Run Migration
```bash
# Using the migration script
./run_map_search_migration.sh

# Or manually with SQL
./bouy exec db psql -U postgres -d pantry_pirate_radio < app/database/init_scripts/04_map_search_indexes.sql

# Or using Python migration
./bouy exec app python app/database/migrations/add_map_search_indexes.py
```

### Required Indexes
- Geographic indexes on latitude/longitude
- Text search indexes on name, description, address fields
- Relationship indexes for joins
- Composite indexes for common query patterns

### Verify Indexes
```bash
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'idx_%';"
```

## Performance Considerations

1. **Text Search**: Without indexes, text searches will be slow. Always ensure indexes are created.
2. **Large Result Sets**: Use pagination to limit response size
3. **Geographic Queries**: Bounding box queries are faster than radius searches
4. **Caching**: Consider caching frequently accessed queries

## Integration Examples

### JavaScript/Leaflet
```javascript
// Fetch locations for current map view
const bbox = map.getBounds();
const response = await fetch(`/api/v1/map/search?` + new URLSearchParams({
  min_lat: bbox.getSouth(),
  max_lat: bbox.getNorth(),
  min_lng: bbox.getWest(),
  max_lng: bbox.getEast(),
  format: 'geojson',
  per_page: 100
}));
const data = await response.json();
L.geoJSON(data.locations[0]).addTo(map);
```

### Python
```python
import requests

# Search for food banks in California
response = requests.get('https://api.for-the-gg.org/api/v1/map/search', params={
    'q': 'food bank',
    'state': 'CA',
    'confidence_min': 70,
    'per_page': 50
})
locations = response.json()['locations']
```

## Troubleshooting

### Slow Queries
- Ensure database indexes are created
- Reduce search scope with geographic filters
- Use pagination to limit results

### No Results
- Check spelling and try simpler search terms
- Remove filters to broaden search
- Verify geographic coordinates are correct

### Timeouts
- Reduce `per_page` parameter
- Add geographic constraints
- Ensure indexes are properly created