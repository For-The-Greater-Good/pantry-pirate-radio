# Production API Issues Summary

## API Status: https://api.for-the-gg.org

### ✅ Working Endpoints (15/33)
1. **Health Monitoring** - All working
   - `/api/v1/health` - ✅ Returns healthy
   - `/api/v1/health/db` - ✅ Database connected
   - `/api/v1/health/redis` - ✅ Redis connected  
   - `/api/v1/health/llm` - ✅ LLM provider connected
   - `/api/v1/metrics` - ✅ Prometheus metrics available

2. **API Metadata** - Working
   - `/api/v1/` - ✅ Returns HSDS v3.1.1 metadata

3. **Map Features** - Partially working
   - `/api/v1/map/metadata` - ✅ Shows 28,101 locations
   - `/api/v1/map/states` - ✅ State coverage data
   - `/api/v1/map/locations` - ✅ Returns location data (some params work)

4. **Taxonomy** - Returns empty but no errors
   - `/api/v1/taxonomies/` - ✅ Returns empty list
   - `/api/v1/taxonomy-terms/` - ✅ Returns empty list

### ❌ Broken Endpoints (18/33)

1. **Organizations** (All failing with 500 errors)
   - `/api/v1/organizations/` - ❌ ValidationError: missing metadata.last_updated
   - `/api/v1/organizations/{id}` - ❌ UUID type mismatch error
   - `/api/v1/organizations/search` - ❌ Returns 422 error

2. **Locations** (All failing with 500 errors)
   - `/api/v1/locations/` - ❌ ValidationError: missing metadata.last_updated
   - `/api/v1/locations/{id}` - ❌ UUID type mismatch error
   - `/api/v1/locations/search` - ❌ ValidationError

3. **Services** (All failing)
   - `/api/v1/services/` - ❌ 422 Unprocessable Entity
   - `/api/v1/services/{id}` - ❌ 500 UUID type error
   - `/api/v1/services/active` - ❌ 422 error
   - `/api/v1/services/search` - ❌ 500 ValidationError

4. **Service-at-Location** (All failing with 500 errors)
   - `/api/v1/service-at-location/` - ❌ ValidationError
   - `/api/v1/service-at-location/{id}` - ❌ UUID type error
   - `/api/v1/service-at-location/service/{id}/locations` - ❌ UUID type error
   - `/api/v1/service-at-location/location/{id}/services` - ❌ UUID type error

## Root Causes

### 1. Pydantic Model Issues
```python
# Error: Field required [type=missing, input_value=MetaData(), input_type=MetaData]
metadata.last_updated  # This field is not being populated
```

### 2. UUID Type Mismatch in PostgreSQL
```sql
-- Error: operator does not exist: character varying = uuid
-- The ID columns are stored as VARCHAR but being queried as UUID
```

### 3. SQLAlchemy Async Context
```python
# Error: MissingGreenlet: greenlet_spawn has not been called
# Trying to access lazy-loaded relationships outside async context
```

## Fixes Needed

### Priority 1: Fix Response Models
1. Add default value for `metadata.last_updated` in Pydantic schemas
2. Ensure all required fields have proper defaults or are populated

### Priority 2: Fix UUID Handling
1. Cast UUID parameters to string before querying
2. Or update database schema to use UUID type

### Priority 3: Fix Async Queries
1. Use eager loading for relationships (`selectinload` or `joinedload`)
2. Ensure all database access happens within async context

## Test Command

To reproduce these issues:
```bash
python3 test_api.py
```

This will generate:
- `api_test_report.html` - Detailed test results
- `api_test_findings.md` - Summary report

## Current Impact

- **45.5% API availability** - Only health/monitoring and map endpoints work
- **Core functionality broken** - Cannot retrieve organizations, locations, or services
- **Search non-functional** - All search endpoints fail
- **Data inaccessible** - Despite having 28,101 locations in database, they cannot be retrieved via API