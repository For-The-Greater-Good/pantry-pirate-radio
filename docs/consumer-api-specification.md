# Consumer API Migration Guide

## For Mobile & Web Developers

This guide helps you migrate from the legacy `export-simple` endpoint to the new Consumer API endpoints, which provide 99% smaller payloads and real-time viewport-based loading.

---

## Quick Start: Migration Overview

### Before (Legacy Approach)
```javascript
// ❌ OLD: Downloads ALL locations (20MB+, 3-5 seconds)
const response = await fetch('https://api.for-the-gg.org/api/v1/locations/export-simple');
const data = await response.json();
// Then filter client-side to viewport... inefficient!
```

### After (New Consumer API)
```javascript
// ✅ NEW: Downloads only visible locations (100KB, <100ms)
const bounds = map.getBounds();
const response = await fetch(`https://api.for-the-gg.org/api/v1/consumer/map/pins?` +
  `min_lat=${bounds.south}&max_lat=${bounds.north}&` +
  `min_lng=${bounds.west}&max_lng=${bounds.east}`);
const data = await response.json();
// Already filtered and grouped!
```

---

## The Three New Endpoints

### 1. Map Pins - For Map Display
**GET** `/api/v1/consumer/map/pins`

Use this when displaying locations on a map. Returns minimal data for pins with automatic clustering.

### 2. Multi-Location - For Grouped Pins
**GET** `/api/v1/consumer/locations/multi`

Use this when user taps a grouped pin to see all locations in that group.

### 3. Location Detail - For Full Information
**GET** `/api/v1/consumer/locations/{id}`

Use this when user selects a specific location for detailed view.

---

## Implementation Examples

### Flutter/Dart Implementation

```dart
class ConsumerApiService {
  static const baseUrl = 'https://api.for-the-gg.org/api/v1/consumer';

  // Step 1: Load map pins for current viewport
  Future<MapPinsResponse> getMapPins(LatLngBounds bounds, {int groupingRadius = 150}) async {
    final params = {
      'min_lat': bounds.southwest.latitude.toString(),
      'max_lat': bounds.northeast.latitude.toString(),
      'min_lng': bounds.southwest.longitude.toString(),
      'max_lng': bounds.northeast.longitude.toString(),
      'grouping_radius': groupingRadius.toString(),
    };

    final uri = Uri.parse('$baseUrl/map/pins').replace(queryParameters: params);
    final response = await http.get(uri);

    if (response.statusCode == 200) {
      return MapPinsResponse.fromJson(json.decode(response.body));
    }
    throw Exception('Failed to load map pins');
  }

  // Step 2: When user taps grouped pin
  Future<List<LocationDetail>> getGroupedLocations(List<String> locationIds) async {
    final params = {'ids': locationIds.join(',')};

    final uri = Uri.parse('$baseUrl/locations/multi').replace(queryParameters: params);
    final response = await http.get(uri);

    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return (data['locations'] as List)
        .map((loc) => LocationDetail.fromJson(loc))
        .toList();
    }
    throw Exception('Failed to load locations');
  }

  // Step 3: When user wants full details
  Future<LocationDetail> getLocationDetail(String locationId, {bool includeNearby = false}) async {
    final params = includeNearby ? {'include_nearby': 'true', 'nearby_radius': '1000'} : {};

    final uri = Uri.parse('$baseUrl/locations/$locationId').replace(queryParameters: params);
    final response = await http.get(uri);

    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return LocationDetail.fromJson(data['location']);
    }
    throw Exception('Failed to load location detail');
  }
}
```

### React/TypeScript Implementation

```typescript
import { useQuery } from '@tanstack/react-query';

const API_BASE = 'https://api.for-the-gg.org/api/v1/consumer';

// Custom hook for map pins
export const useMapPins = (bounds: MapBounds, groupingRadius = 150) => {
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

      const response = await fetch(`${API_BASE}/map/pins?${params}`);
      if (!response.ok) throw new Error('Failed to fetch pins');
      return response.json();
    },
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });
};

// Custom hook for grouped locations
export const useGroupedLocations = (locationIds: string[]) => {
  return useQuery({
    queryKey: ['locations', locationIds],
    queryFn: async () => {
      const params = new URLSearchParams({ ids: locationIds.join(',') });

      const response = await fetch(`${API_BASE}/locations/multi?${params}`);
      if (!response.ok) throw new Error('Failed to fetch locations');
      return response.json();
    },
    enabled: locationIds.length > 0,
    staleTime: 60 * 60 * 1000, // Cache for 1 hour
  });
};

// Component example
function MapView() {
  const [bounds, setBounds] = useState(getInitialBounds());
  const [groupingRadius, setGroupingRadius] = useState(150);

  const { data: pinsData, isLoading } = useMapPins(bounds, groupingRadius);

  const handleMapMove = (newBounds: MapBounds) => {
    setBounds(newBounds);
  };

  const handlePinClick = (pin: MapPin) => {
    if (pin.type === 'group') {
      // Fetch details for all locations in group
      fetchGroupedLocations(pin.location_ids);
    } else {
      // Show single location
      navigateToLocation(pin.location_ids[0]);
    }
  };

  return (
    <Map
      onBoundsChange={handleMapMove}
      pins={pinsData?.pins || []}
      loading={isLoading}
    />
  );
}
```

---

## API Reference - Live Implementation

**Base URL**: `https://api.for-the-gg.org/api/v1/consumer`
**Status**: ✅ **All endpoints are LIVE and operational**

### 1. Map Pins Endpoint

**GET** `/api/v1/consumer/map/pins`

**Live URL**: `https://api.for-the-gg.org/api/v1/consumer/map/pins`

#### Required Parameters
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| min_lat | float | Southern boundary (-90 to 90) | 40.7 |
| max_lat | float | Northern boundary (-90 to 90) | 40.8 |
| min_lng | float | Western boundary (-180 to 180) | -74.1 |
| max_lng | float | Eastern boundary (-180 to 180) | -74.0 |

#### Optional Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| grouping_radius | int | 150 | Clustering radius in meters (0-500, 0=disabled) |
| min_confidence | int | null | Minimum confidence score (0-100) |
| open_now | bool | null | Filter to currently open locations |
| services | string | null | Comma-separated service types |

#### Response Structure
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
      "location_ids": ["id1", "id2", "id3"],
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
    "viewport_bounds": {...},
    "grouping_radius": 150,
    "timestamp": "2024-01-15T10:00:00Z"
  }
}
```

#### Example Requests

```bash
# Basic viewport query with default grouping (150m)
curl "https://api.for-the-gg.org/api/v1/consumer/map/pins?min_lat=40.7&max_lat=40.8&min_lng=-74.1&max_lng=-74.0"

# Disable grouping to see all individual locations
curl "https://api.for-the-gg.org/api/v1/consumer/map/pins?min_lat=40.7&max_lat=40.8&min_lng=-74.1&max_lng=-74.0&grouping_radius=0"

# Filter high-confidence locations only
curl "https://api.for-the-gg.org/api/v1/consumer/map/pins?min_lat=40.7&max_lat=40.8&min_lng=-74.1&max_lng=-74.0&min_confidence=70"

# Filter by services
curl "https://api.for-the-gg.org/api/v1/consumer/map/pins?min_lat=40.7&max_lat=40.8&min_lng=-74.1&max_lng=-74.0&services=food_pantry,meal_program"
```

### 2. Multi-Location Fetch Endpoint

**GET** `/api/v1/consumer/locations/multi`

**Live URL**: `https://api.for-the-gg.org/api/v1/consumer/locations/multi`

#### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ids | string | Yes | Comma-separated location UUIDs (max 100) |
| include_sources | bool | No | Include source data (default: true) |
| include_schedule | bool | No | Include schedules (default: true) |

#### Response Structure
```json
{
  "locations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "canonical": {
        "name": "St. Mary's Food Bank",
        "address": {
          "street": "123 Main St",
          "city": "New York",
          "state": "NY",
          "zip": "10001"
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
        },
        "confidence": 95,
        "validation_status": "verified"
      },
      "sources": [
        {
          "scraper_id": "feeding_america",
          "last_updated": "2024-01-15T10:00:00Z",
          "name": "St. Mary's Food Bank",
          "phone": "212-555-0100",
          "confidence": 100
        }
      ],
      "schedule_merged": {...}
    }
  ]
}
```

#### Example Requests

```bash
# Fetch details for 2 locations (from a grouped pin)
curl "https://api.for-the-gg.org/api/v1/consumer/locations/multi?ids=550e8400-e29b-41d4-a716-446655440000,6ba7b810-9dad-11d1-80b4-00c04fd430c8"

# Fetch without source data (faster response)
curl "https://api.for-the-gg.org/api/v1/consumer/locations/multi?ids=550e8400-e29b-41d4-a716-446655440000&include_sources=false&include_schedule=false"

# Batch fetch up to 100 locations
curl "https://api.for-the-gg.org/api/v1/consumer/locations/multi?ids=id1,id2,id3,id4,id5"
```

### 3. Single Location Detail Endpoint

**GET** `/api/v1/consumer/locations/{location_id}`

**Live URL**: `https://api.for-the-gg.org/api/v1/consumer/locations/{location_id}`

#### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| location_id | UUID | Yes | Location UUID (in path) |
| include_nearby | bool | No | Include nearby locations (default: false) |
| nearby_radius | int | No | Radius for nearby search in meters (default: 500) |
| include_history | bool | No | Include version history (default: false) |

#### Response Structure
```json
{
  "location": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "canonical": {...},
    "sources": [...],
    "schedule_merged": {...}
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
  ]
}
```

#### Example Requests

```bash
# Get basic location details
curl "https://api.for-the-gg.org/api/v1/consumer/locations/550e8400-e29b-41d4-a716-446655440000"

# Include nearby locations within 1km
curl "https://api.for-the-gg.org/api/v1/consumer/locations/550e8400-e29b-41d4-a716-446655440000?include_nearby=true&nearby_radius=1000"

# Include version history (future feature)
curl "https://api.for-the-gg.org/api/v1/consumer/locations/550e8400-e29b-41d4-a716-446655440000?include_history=true"
```

---

## Multi-Source Data Architecture

### The Problem
Food assistance locations are listed across dozens of different websites and databases:
- **Feeding America** has their own directory
- **FindHelp/211** maintains separate listings
- **Local government** websites have their own databases
- **Churches and community organizations** list locations independently
- **Google Maps** may have different information

Each source may have:
- Different names for the same location (e.g., "St. Mary's Food Bank" vs "Saint Mary Food Pantry")
- Different phone numbers (main line vs direct line)
- Different schedules (some sources more up-to-date than others)
- Different addresses (formatting variations or outdated info)
- Different service descriptions

### Our Solution: Multi-Source Transparency

Instead of arbitrarily picking one source as "truth", we:

1. **Collect Everything**: Our scrapers gather data from 12+ different sources
2. **Track Sources**: The `location_source` table maintains a record of every source that knows about a location
3. **Create Canonical Records**: The reconciler creates a single "best" record but preserves all variations
4. **Expose All Data**: The Consumer API returns both canonical data AND all source variations

### Data Flow

```
Multiple Scrapers → location_source table → Reconciler → location table (canonical)
                            ↓                                    ↓
                    (preserves all sources)            (best consolidated view)
                            ↓                                    ↓
                    Consumer API returns BOTH
```

### Why This Matters for Consumers

1. **Transparency**: Users can see if multiple sources agree on information (high confidence)
2. **Conflict Resolution**: When sources disagree, users see all options (e.g., two different phone numbers)
3. **Freshness**: Users can see which source was updated most recently
4. **Verification**: Multiple sources listing the same location increases confidence it's real

### Example: Multi-Source Response

When you call `/api/v1/consumer/locations/multi`, you get:

```json
{
  "canonical": {
    "name": "St. Mary's Food Bank",        // Best name (most common)
    "phone": "212-555-0100",               // Most reliable phone
    "confidence": 95                       // High confidence (3 sources agree)
  },
  "sources": [
    {
      "scraper_id": "feeding_america",
      "name": "St. Mary's Food Bank",
      "phone": "212-555-0100",
      "last_updated": "2024-01-15T10:00:00Z"
    },
    {
      "scraper_id": "findhelp",
      "name": "Saint Mary Food Pantry",     // Different name
      "phone": "(212) 555-0100",            // Different format
      "last_updated": "2024-01-14T15:00:00Z"
    },
    {
      "scraper_id": "211",
      "name": "ST MARYS FOOD BANK",         // Different capitalization
      "phone": "2125550100",                // No formatting
      "last_updated": "2024-01-10T08:00:00Z"
    }
  ]
}
```

### Confidence Scoring

Locations receive higher confidence scores when:
- Multiple sources list the same location
- Sources agree on key details (name, address, phone)
- Data is recently updated
- Sources are considered reliable

### Benefits of This Approach

1. **No Single Point of Failure**: If one source goes down or has bad data, others compensate
2. **Better Coverage**: Some sources know about locations others don't
3. **Quality Through Quantity**: Agreement between sources validates data
4. **User Empowerment**: Users can make informed decisions when sources conflict

---

## Implementation Notes

### Technology Stack
- **Backend**: Python/FastAPI with async support
- **Database**: PostgreSQL with PostGIS extension
- **Clustering**: PostGIS ST_ClusterDBSCAN function
- **Caching**: Redis (future enhancement)

### Key Implementation Details

#### 1. Dynamic Clustering Algorithm
- Uses PostGIS ST_ClusterDBSCAN for efficient spatial clustering
- Converts grouping_radius from meters to degrees dynamically
- Groups locations within specified radius (0-500m)
- Returns cluster centroids and bounds

#### 2. Performance Optimizations
- Viewport queries limited to 1000 locations max
- Spatial indexes on latitude/longitude columns
- Batch queries for multi-location fetches
- Query result limits prevent timeouts

#### 3. Data Quality Features
- Leverages existing confidence_score field (0-100)
- Filters by validation_status (excludes 'rejected')
- Shows all source variations with timestamps
- Identifies data conflicts between sources

#### 4. Error Handling
- Validates viewport boundaries (min < max)
- Validates coordinate ranges (-90 to 90, -180 to 180)
- Limits multi-fetch to 100 locations
- Returns appropriate HTTP status codes

### Current Limitations
- Similarity analysis between locations (planned)
- Version history tracking (planned)
- Advanced caching strategies (planned)
- Real-time schedule evaluation for open_now filter (planned)

---

## Migration Checklist ✅ COMPLETED

### Phase 1: Parallel Implementation ✅
- [x] Add new Consumer API service layer
- [x] Implement viewport-based pin loading
- [x] Add fallback to export-simple if needed
- [x] Test with production data

### Phase 2: Feature Parity (In Progress)
- [ ] Implement location grouping UI
- [x] Add progressive detail loading
- [x] Handle multi-source data display
- [ ] Test offline caching

### Phase 3: Complete Migration (Planned)
- [ ] Remove export-simple calls
- [ ] Update all map views
- [ ] Optimize cache strategies
- [ ] Monitor performance metrics

---

## Performance Tips

### 1. Viewport Management
```javascript
// Debounce map moves to avoid excessive API calls
const debouncedFetch = debounce((bounds) => {
  fetchMapPins(bounds);
}, 300);

map.on('moveend', () => {
  debouncedFetch(map.getBounds());
});
```

### 2. Smart Caching
```javascript
// Cache location details to avoid refetching
const locationCache = new LRUCache({ max: 500 });

async function getLocation(id) {
  if (locationCache.has(id)) {
    return locationCache.get(id);
  }
  const location = await fetchLocationDetail(id);
  locationCache.set(id, location);
  return location;
}
```

### 3. Grouping Radius Strategy
```javascript
// Adjust grouping based on zoom level
function getGroupingRadius(zoomLevel) {
  if (zoomLevel >= 15) return 0;      // No grouping when zoomed in
  if (zoomLevel >= 12) return 150;    // Default grouping
  if (zoomLevel >= 10) return 300;    // More grouping
  return 500;                         // Maximum grouping when zoomed out
}
```

---

## Common Issues & Solutions

### Issue: Too Many Pins Returned
**Solution**: Increase grouping_radius or limit viewport size
```javascript
const MAX_VIEWPORT_SIZE = 2.0; // degrees
if (bounds.north - bounds.south > MAX_VIEWPORT_SIZE) {
  // Viewport too large, warn user or adjust
}
```

### Issue: Grouped Pins at High Zoom
**Solution**: Disable grouping when zoomed in
```javascript
const groupingRadius = map.getZoom() > 14 ? 0 : 150;
```

### Issue: Slow Response Times
**Solution**: Check viewport size and reduce if needed
```javascript
// Log slow requests for debugging
if (responseTime > 500) {
  console.warn('Slow API response:', {
    viewport: bounds,
    locationCount: response.metadata.total_locations,
    time: responseTime
  });
}
```

---

## Support & Resources

- **API Base URL**: `https://api.for-the-gg.org/api/v1/consumer/`
- **OpenAPI Documentation**: `https://api.for-the-gg.org/docs`
- **Legacy Endpoint** (deprecated): `/api/v1/locations/export-simple`
- **GitHub Issues**: Report issues at the project repository
- **Migration Deadline**: export-simple will be deprecated on 2024-12-31

---

## Example: Complete Flutter Migration

```dart
// Before: Using export-simple
class OldLocationService {
  Future<List<Location>> getAllLocations() async {
    // Downloads 20MB+ of data!
    final response = await http.get(
      Uri.parse('https://api.for-the-gg.org/api/v1/locations/export-simple')
    );
    final data = json.decode(response.body);
    return (data['locations'] as List)
      .map((loc) => Location.fromJson(loc))
      .toList();
  }
}

// After: Using Consumer API
class NewLocationService {
  final _pinCache = <String, MapPinsResponse>{};
  final _locationCache = <String, LocationDetail>{};

  // Only fetch what's visible
  Future<MapPinsResponse> getVisiblePins(LatLngBounds bounds) async {
    final cacheKey = '${bounds.toString()}_${DateTime.now().minute ~/ 5}';

    if (_pinCache.containsKey(cacheKey)) {
      return _pinCache[cacheKey]!;
    }

    final response = await _fetchMapPins(bounds);
    _pinCache[cacheKey] = response;

    // Clean old cache entries
    if (_pinCache.length > 10) {
      _pinCache.remove(_pinCache.keys.first);
    }

    return response;
  }

  // Progressive loading for details
  Future<LocationDetail> getLocationDetail(String id) async {
    if (_locationCache.containsKey(id)) {
      return _locationCache[id]!;
    }

    final detail = await _fetchLocationDetail(id);
    _locationCache[id] = detail;
    return detail;
  }
}
```

---

**Last Updated**: 2024-01-15
**API Version**: 1.0.0
**Status**: ✅ Production Ready