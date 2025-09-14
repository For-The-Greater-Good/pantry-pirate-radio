# Consumer API Specification

## Executive Summary

This specification defines a new set of consumer-focused API endpoints designed to replace the current `export-simple` endpoint. The new endpoints provide efficient, viewport-based data loading with dynamic location grouping and transparent multi-source data exposure.

### Key Improvements
- **99% reduction** in initial payload size (from ~20MB to ~100KB)
- **Sub-100ms response times** for map loads (vs 3.7 seconds)
- **Dynamic grouping** adjustable in real-time by users
- **Progressive detail loading** - fetch only what's needed
- **Multi-source transparency** - show data from all scrapers

---

## User Stories

### Story 1: Initial Map Load
**As a** hungry person looking for food assistance
**I want to** see nearby food locations on a map quickly
**So that I** can find help without waiting for large downloads

**Acceptance Criteria:**
- Map shows locations within 1 second of opening app
- Only loads locations visible in current viewport
- Shows clustered pins when locations are close together
- Works on slow 3G connections

### Story 2: Adjusting Location Grouping
**As a** user in a dense urban area
**I want to** control how locations are grouped on the map
**So that I** can see individual locations when zoomed in or grouped overview when zoomed out

**Acceptance Criteria:**
- Slider or control to adjust grouping radius from 0-500 meters
- Map updates immediately when grouping changes
- Groups show count of locations contained
- Can tap group to see all member locations

### Story 3: Viewing Grouped Locations
**As a** user who tapped on a grouped pin
**I want to** see all locations in that group
**So that I** can choose which specific location to visit

**Acceptance Criteria:**
- List shows all locations in the group
- Each location shows name, address, and distance
- Can tap any location for full details
- Shows which locations might be duplicates

### Story 4: Viewing Location Details
**As a** user viewing a specific location
**I want to** see all available information including conflicting data
**So that I** can make an informed decision about visiting

**Acceptance Criteria:**
- Shows canonical (best) information prominently
- Lists all data sources with their variations
- Highlights where sources disagree (schedule, phone, etc.)
- Shows when each source was last updated

### Story 5: Offline Map Usage
**As a** user with limited data
**I want to** cache map data for offline use
**So that I** can find food locations without internet

**Acceptance Criteria:**
- Can pre-download locations for a specific area
- Cached data remains usable for 7 days
- Shows indicator when viewing cached vs live data
- Updates cache incrementally when online

---

## API Endpoints

### 1. Map Pins Endpoint

#### `GET /api/v1/consumer/map/pins`

**Purpose**: Retrieve location pins for map display with dynamic grouping based on viewport.

**Request Parameters:**
```typescript
{
  // Required: Viewport boundaries
  min_lat: number,        // -90 to 90
  max_lat: number,        // -90 to 90
  min_lng: number,        // -180 to 180
  max_lng: number,        // -180 to 180

  // Optional: Grouping control
  grouping_radius?: number,  // Meters, 0-500, default: 150

  // Optional: Filters
  min_confidence?: number,    // 0-100, default: 0
  open_now?: boolean,         // Filter by current schedule
  services?: string[],        // Filter by service types
}
```

**Response:**
```json
{
  "pins": [
    {
      "type": "single",
      "lat": 40.7128,
      "lng": -74.0060,
      "location_ids": ["550e8400-e29b-41d4-a716-446655440000"],
      "name": "St. Mary's Food Bank",
      "confidence": 95,
      "source_count": 3,
      "has_schedule": true,
      "open_now": true
    },
    {
      "type": "group",
      "lat": 40.7256,
      "lng": -74.0125,
      "location_ids": [
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
        "6ba7b812-9dad-11d1-80b4-00c04fd430c8"
      ],
      "name": "3 locations",
      "primary_name": "Community Kitchen",
      "confidence_avg": 82,
      "source_count": 7,
      "bounds": {
        "north": 40.7258,
        "south": 40.7254,
        "east": -74.0123,
        "west": -74.0127
      }
    }
  ],
  "metadata": {
    "total_pins": 42,
    "total_locations": 67,
    "viewport_bounds": {
      "north": 40.73,
      "south": 40.71,
      "east": -74.00,
      "west": -74.02
    },
    "grouping_radius": 150,
    "timestamp": "2024-01-15T10:00:00Z"
  }
}
```

**Implementation Notes:**
```sql
-- Efficient viewport query with clustering
WITH viewport_locations AS (
    SELECT
        l.id,
        l.latitude,
        l.longitude,
        l.name,
        l.confidence_score,
        COUNT(DISTINCT ls.scraper_id) as source_count,
        EXISTS(SELECT 1 FROM schedule s WHERE s.location_id = l.id) as has_schedule
    FROM location l
    LEFT JOIN location_source ls ON ls.location_id = l.id
    WHERE l.latitude BETWEEN :min_lat AND :max_lat
      AND l.longitude BETWEEN :min_lng AND :max_lng
      AND (l.validation_status != 'rejected' OR l.validation_status IS NULL)
      AND l.confidence_score >= COALESCE(:min_confidence, 0)
    GROUP BY l.id
    LIMIT 1000
),
clustered AS (
    SELECT *,
        CASE
            WHEN :grouping_radius > 0 THEN
                ST_ClusterDBSCAN(
                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
                    eps := :grouping_radius / 111000.0,
                    minpoints := 1
                ) OVER()
            ELSE NULL
        END as cluster_id
    FROM viewport_locations
)
SELECT
    COALESCE(cluster_id, -1 * ROW_NUMBER() OVER()) as group_key,
    json_agg(
        json_build_object(
            'id', id,
            'lat', latitude,
            'lng', longitude,
            'name', name,
            'confidence', confidence_score,
            'source_count', source_count,
            'has_schedule', has_schedule
        )
    ) as locations
FROM clustered
GROUP BY group_key;
```

**Error Responses:**
- `400 Bad Request` - Invalid viewport bounds or parameters
- `429 Too Many Requests` - Rate limit exceeded

---

### 2. Multi-Location Fetch Endpoint

#### `GET /api/v1/consumer/locations/multi`

**Purpose**: Fetch detailed information for multiple locations (used when user taps a grouped pin).

**Request Parameters:**
```typescript
{
  ids: string[],           // Array of location UUIDs (max 100)
  include_sources?: boolean,  // Include source data, default: true
  include_schedule?: boolean, // Include schedules, default: true
}
```

**Response:**
```json
{
  "locations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "canonical": {
        "name": "St. Mary's Food Bank",
        "address": "123 Main St, New York, NY 10001",
        "phone": "212-555-0100",
        "website": "www.stmarysfb.org",
        "lat": 40.7128,
        "lng": -74.0060,
        "confidence": 95,
        "validation_status": "verified"
      },
      "sources": [
        {
          "scraper_id": "feeding_america",
          "last_updated": "2024-01-15T10:00:00Z",
          "name": "St. Mary's Food Bank",
          "address": "123 Main St",
          "phone": "212-555-0100",
          "website": "www.stmarysfb.org",
          "schedule": {
            "monday": {"open": "09:00", "close": "17:00"},
            "tuesday": {"open": "09:00", "close": "17:00"},
            "wednesday": {"open": "09:00", "close": "17:00"},
            "thursday": {"open": "09:00", "close": "17:00"},
            "friday": {"open": "09:00", "close": "17:00"}
          },
          "services": ["food_pantry", "meal_program"],
          "confidence": 100
        },
        {
          "scraper_id": "findhelp",
          "last_updated": "2024-01-14T15:00:00Z",
          "name": "Saint Mary Food Bank",
          "address": "123 Main Street",
          "phone": "(212) 555-0100",
          "schedule": {
            "text": "Weekdays 9am-5pm"
          },
          "services": ["food_pantry"],
          "confidence": 85
        }
      ],
      "distance_meters": 150,
      "is_open": true
    }
  ],
  "similarities": [
    {
      "location_ids": ["id1", "id2"],
      "similarity_score": 0.92,
      "same_phone": true,
      "same_address": false,
      "distance_meters": 75
    }
  ]
}
```

**Implementation Notes:**
- Maximum 100 locations per request to prevent timeout
- Uses batch queries to minimize database round trips
- Returns similarity analysis to help identify duplicates

---

### 3. Single Location Detail Endpoint

#### `GET /api/v1/consumer/locations/{id}`

**Purpose**: Get comprehensive details for a single location.

**Request Parameters:**
```typescript
{
  include_nearby?: boolean,   // Include nearby locations, default: false
  nearby_radius?: number,     // Radius in meters, default: 500
  include_history?: boolean,  // Include version history, default: false
}
```

**Response:**
```json
{
  "location": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "canonical": {
      "name": "St. Mary's Food Bank",
      "alternate_name": "St. Mary's Community Pantry",
      "description": "Serving the community since 1985",
      "address": {
        "street": "123 Main St",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "country": "US"
      },
      "coordinates": {
        "lat": 40.7128,
        "lng": -74.0060,
        "geocoding_source": "google",
        "confidence": 95
      },
      "contact": {
        "phone": "212-555-0100",
        "email": "info@stmarysfb.org",
        "website": "www.stmarysfb.org"
      }
    },
    "sources": [
      {
        "scraper_id": "feeding_america",
        "scraper_name": "Feeding America",
        "last_updated": "2024-01-15T10:00:00Z",
        "first_seen": "2023-06-01T00:00:00Z",
        "update_frequency": "weekly",
        "data": {
          "name": "St. Mary's Food Bank",
          "address": "123 Main St",
          "phone": "212-555-0100",
          "email": "info@stmarysfb.org",
          "website": "www.stmarysfb.org",
          "schedule": {
            "monday": {"open": "09:00", "close": "17:00"},
            "tuesday": {"open": "09:00", "close": "17:00"},
            "wednesday": {"open": "09:00", "close": "17:00"},
            "thursday": {"open": "09:00", "close": "17:00"},
            "friday": {"open": "09:00", "close": "17:00"},
            "saturday": null,
            "sunday": null
          },
          "services": [
            {
              "name": "food_pantry",
              "description": "Emergency food assistance"
            },
            {
              "name": "meal_program",
              "description": "Hot meals served daily"
            }
          ],
          "requirements": "Photo ID required",
          "languages": ["en", "es"],
          "accessibility": "Wheelchair accessible"
        }
      },
      {
        "scraper_id": "211",
        "scraper_name": "211 Information",
        "last_updated": "2024-01-10T08:00:00Z",
        "data": {
          "name": "ST MARYS FOOD BANK",
          "phone": "2125550100",
          "schedule": {
            "text": "M-F 9-5"
          }
        }
      }
    ],
    "schedule_merged": {
      "monday": {
        "open": "09:00",
        "close": "17:00",
        "sources_agree": ["feeding_america", "211"],
        "confidence": "high"
      }
    },
    "data_quality": {
      "confidence_score": 95,
      "validation_status": "verified",
      "last_verified": "2024-01-15T10:00:00Z",
      "source_count": 3,
      "update_frequency": "weekly",
      "conflicts": [
        {
          "field": "name",
          "values": ["St. Mary's Food Bank", "ST MARYS FOOD BANK"],
          "resolution": "St. Mary's Food Bank"
        }
      ]
    }
  },
  "nearby_locations": [
    {
      "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "name": "Community Kitchen",
      "distance_meters": 230,
      "bearing": "NE",
      "address": "456 Oak Ave",
      "is_open": false
    }
  ],
  "version_history": [
    {
      "version": 5,
      "timestamp": "2024-01-15T10:00:00Z",
      "changes": ["schedule updated", "phone verified"],
      "source": "feeding_america"
    }
  ]
}
```

---

## Implementation Guide

### Performance Requirements

1. **Response Times**
   - Map pins endpoint: < 100ms for viewport with 1000 locations
   - Multi-location fetch: < 200ms for 20 locations
   - Single location detail: < 150ms

2. **Payload Sizes**
   - Map pins: ~1KB per pin (grouped), ~200 bytes per pin (single)
   - Multi-location: ~2KB per location with sources
   - Single location: ~5-10KB with full details

3. **Rate Limits**
   - Map pins: 60 requests per minute
   - Location details: 120 requests per minute
   - Multi-fetch: 30 requests per minute

### Caching Strategy

#### Client-Side Caching
```typescript
// Recommended cache durations
const CACHE_DURATIONS = {
  mapPins: 5 * 60 * 1000,        // 5 minutes
  locationDetails: 24 * 60 * 60 * 1000,  // 24 hours
  multiLocation: 60 * 60 * 1000,  // 1 hour
};

// LRU cache for location details
class LocationCache {
  private cache = new Map();
  private maxSize = 500;

  get(id: string): Location | null {
    const item = this.cache.get(id);
    if (item && Date.now() - item.timestamp < CACHE_DURATIONS.locationDetails) {
      // Move to front (LRU)
      this.cache.delete(id);
      this.cache.set(id, item);
      return item.data;
    }
    return null;
  }

  set(id: string, data: Location): void {
    if (this.cache.size >= this.maxSize) {
      // Remove oldest
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    this.cache.set(id, {
      data,
      timestamp: Date.now()
    });
  }
}
```

#### Server-Side Caching
- Use Redis with viewport-based keys
- Cache grouped results for common zoom levels
- Invalidate on data updates

### Migration from export-simple

#### Phase 1: Parallel Operation (Months 1-2)
```typescript
// Mobile app code
class MapDataService {
  async loadMapData() {
    // Check API capabilities
    const apiVersion = await this.getApiVersion();

    if (apiVersion.supports('consumer/map/pins')) {
      // Use new viewport-based loading
      return this.loadViewportPins();
    } else {
      // Fallback to legacy export-simple
      return this.loadAllLocations();
    }
  }

  private async loadViewportPins() {
    const bounds = this.map.getBounds();
    const response = await fetch(`/api/v1/consumer/map/pins?${
      new URLSearchParams({
        min_lat: bounds.south,
        max_lat: bounds.north,
        min_lng: bounds.west,
        max_lng: bounds.east,
        grouping_radius: this.groupingRadius
      })
    }`);
    return response.json();
  }

  private async loadAllLocations() {
    // Legacy approach
    const response = await fetch('/api/v1/locations/export-simple');
    const data = await response.json();
    // Filter client-side to viewport
    return this.filterToViewport(data.locations);
  }
}
```

#### Phase 2: Migration Period (Months 3-4)
- Monitor usage of both endpoints
- Gradual rollout via feature flags
- A/B testing for performance validation

#### Phase 3: Deprecation (Months 5-12)
```typescript
// Add deprecation headers to export-simple
response.headers['X-Deprecated'] = 'true';
response.headers['X-Sunset-Date'] = '2024-12-31';
response.headers['X-Alternative'] = '/api/v1/consumer/map/pins';
```

### Mobile App Integration

#### Flutter Example
```dart
class LocationService {
  final Dio _dio = Dio();
  final LocationCache _cache = LocationCache();

  Future<List<MapPin>> getMapPins(LatLngBounds bounds, int groupingRadius) async {
    final response = await _dio.get('/api/v1/consumer/map/pins',
      queryParameters: {
        'min_lat': bounds.south,
        'max_lat': bounds.north,
        'min_lng': bounds.west,
        'max_lng': bounds.east,
        'grouping_radius': groupingRadius,
      }
    );

    return (response.data['pins'] as List)
      .map((pin) => MapPin.fromJson(pin))
      .toList();
  }

  Future<List<Location>> getGroupedLocations(List<String> ids) async {
    // Check cache first
    final cached = ids.map((id) => _cache.get(id)).whereType<Location>().toList();
    if (cached.length == ids.length) {
      return cached;
    }

    // Fetch missing
    final response = await _dio.get('/api/v1/consumer/locations/multi',
      queryParameters: {
        'ids': ids.join(','),
      }
    );

    final locations = (response.data['locations'] as List)
      .map((loc) => Location.fromJson(loc))
      .toList();

    // Update cache
    for (final location in locations) {
      _cache.set(location.id, location);
    }

    return locations;
  }
}
```

#### React Native Example
```typescript
import { useQuery } from '@tanstack/react-query';

const useMapPins = (bounds: Bounds, groupingRadius: number) => {
  return useQuery({
    queryKey: ['mapPins', bounds, groupingRadius],
    queryFn: async () => {
      const params = new URLSearchParams({
        min_lat: bounds.south.toString(),
        max_lat: bounds.north.toString(),
        min_lng: bounds.west.toString(),
        max_lng: bounds.east.toString(),
        grouping_radius: groupingRadius.toString(),
      });

      const response = await fetch(`/api/v1/consumer/map/pins?${params}`);
      return response.json();
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    cacheTime: 10 * 60 * 1000, // 10 minutes
  });
};

const useLocationDetails = (ids: string[]) => {
  return useQuery({
    queryKey: ['locations', ids],
    queryFn: async () => {
      const response = await fetch('/api/v1/consumer/locations/multi', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      return response.json();
    },
    staleTime: 60 * 60 * 1000, // 1 hour
  });
};
```

---

## Testing Requirements

### Load Testing Scenarios

1. **Dense Urban Area**
   - 5000 locations in viewport
   - Grouping radius: 150m
   - Expected: < 200ms response, ~200 pins returned

2. **Rapid Panning**
   - 10 viewport changes per second
   - Different bounds each time
   - Expected: No rate limiting, all responses < 100ms

3. **Group Expansion**
   - Fetch details for group of 50 locations
   - Expected: < 500ms response

### End-to-End Test Cases

```typescript
describe('Consumer API', () => {
  it('should return grouped pins for dense areas', async () => {
    const response = await api.getMapPins({
      min_lat: 40.7,
      max_lat: 40.8,
      min_lng: -74.1,
      max_lng: -74.0,
      grouping_radius: 150
    });

    expect(response.pins).toBeDefined();
    expect(response.pins.some(p => p.type === 'group')).toBe(true);
    expect(response.metadata.grouping_radius).toBe(150);
  });

  it('should return individual pins when grouping disabled', async () => {
    const response = await api.getMapPins({
      min_lat: 40.7,
      max_lat: 40.8,
      min_lng: -74.1,
      max_lng: -74.0,
      grouping_radius: 0
    });

    expect(response.pins.every(p => p.type === 'single')).toBe(true);
  });

  it('should fetch multiple locations efficiently', async () => {
    const ids = ['uuid1', 'uuid2', 'uuid3'];
    const response = await api.getMultipleLocations(ids);

    expect(response.locations).toHaveLength(3);
    expect(response.locations[0].sources).toBeDefined();
  });
});
```

---

## Security Considerations

1. **Rate Limiting**
   - Implement per-IP and per-user limits
   - Use sliding window algorithm
   - Return 429 with Retry-After header

2. **Input Validation**
   - Validate viewport bounds are reasonable
   - Limit number of IDs in multi-fetch
   - Sanitize all query parameters

3. **Data Privacy**
   - No PII in responses
   - Audit log API access
   - GDPR compliance for location data

---

## Monitoring and Analytics

### Key Metrics to Track

1. **Performance Metrics**
   - P50, P95, P99 response times per endpoint
   - Payload sizes
   - Cache hit rates

2. **Usage Metrics**
   - Unique users per day
   - Average viewport size
   - Most common grouping radius values
   - Peak request times

3. **Business Metrics**
   - Locations viewed per session
   - Group expansion rate
   - Time to first meaningful paint

### Alerting Thresholds

```yaml
alerts:
  - name: high_response_time
    condition: p95_response_time > 500ms
    severity: warning

  - name: excessive_payload
    condition: avg_payload_size > 100KB
    severity: warning

  - name: low_cache_hit_rate
    condition: cache_hit_rate < 0.7
    severity: info
```

---

## Appendix A: Database Schema Requirements

### Indexes Needed
```sql
-- Spatial index for viewport queries
CREATE INDEX idx_location_coordinates_gist
ON location USING GIST (
  ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
);

-- Composite index for filtered queries
CREATE INDEX idx_location_viewport_filter
ON location (latitude, longitude, validation_status, confidence_score)
WHERE validation_status != 'rejected';

-- Source lookup index
CREATE INDEX idx_location_source_location
ON location_source (location_id, scraper_id);
```

---

## Appendix B: API Versioning Strategy

All consumer endpoints will be versioned via URL path:
- Current: `/api/v1/consumer/...`
- Future: `/api/v2/consumer/...`

Breaking changes require new version. Non-breaking changes:
- Adding optional parameters
- Adding fields to responses
- Adding new endpoints

---

## Approval and Sign-off

**Prepared by**: Assistant
**Date**: 2024-01-15
**Version**: 1.0

**Reviewers**:
- [ ] Backend Team Lead
- [ ] Mobile App Team Lead
- [ ] Product Manager
- [ ] DevOps/Infrastructure

**Implementation Timeline**:
- Week 1-2: Backend implementation
- Week 3: Internal testing
- Week 4: Mobile app integration
- Week 5-6: Beta testing
- Week 7: Production rollout
- Week 8-12: Migration period
- Month 6: Deprecate export-simple