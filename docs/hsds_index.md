# HSDS Implementation Guide

This document provides a detailed guide to the HSDS (Human Services Data Specification) implementation in the Pantry Pirate Radio project. For the complete HSDS documentation and specification files, see [`/docs/HSDS/README.md`](HSDS/README.md).

## Project-Specific HSDS Implementation

### Overview
The Pantry Pirate Radio project uses HSDS as its core data model for representing food pantries and community resources. This implementation focuses specifically on food assistance services while maintaining full HSDS compliance.

### Data Flow Architecture

```
Web Sources → Scrapers → HSDS Aligner → Database → API → Consumers
                             ↓
                    LLM Validation & Transformation
```

### Key Implementation Components

#### 1. HSDS Aligner (`/app/llm/hsds_aligner/`)
The HSDS Aligner is an LLM-powered component that transforms unstructured scraped data into HSDS-compliant format:

- **`aligner.py`** - Main alignment orchestrator
- **`type_defs.py`** - TypedDict definitions for all HSDS structures
- **`validator.py`** - Ensures data meets HSDS requirements
- **`schema_converter.py`** - Converts between different data formats
- **`field_validator.py`** - Field-level validation logic

#### 2. Database Models (`/app/models/hsds/`)
SQLAlchemy models that persist HSDS data:

- **`organization.py`** - Organization entities
- **`service.py`** - Service definitions
- **`location.py`** - Physical and virtual locations
- **`service_at_location.py`** - Service-location relationships
- **`base.py`** - Base model with common fields

#### 3. API Endpoints (`/app/api/v1/`)
RESTful endpoints serving HSDS data:

- **`/organizations`** - CRUD operations for organizations
- **`/services`** - Service management
- **`/locations`** - Location data access
- **`/service-at-location`** - Service-location links

All endpoints return HSDS-compliant JSON and support standard query parameters.

## Practical HSDS Examples in This Project

### Example: Food Pantry Organization
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Community Food Bank of Example County",
  "description": "Provides emergency food assistance to residents in need",
  "email": "info@examplefoodbank.org",
  "website": "https://examplefoodbank.org",
  "tax_id": "12-3456789",
  "services": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "Emergency Food Distribution",
      "description": "Weekly food distribution for families in need",
      "status": "active",
      "application_process": "Walk-in during distribution hours, bring photo ID"
    }
  ]
}
```

### Example: Service Location
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "name": "Main Distribution Center",
  "location_type": "physical",
  "latitude": 40.7128,
  "longitude": -74.0060,
  "addresses": [
    {
      "address_1": "123 Main Street",
      "city": "Example City",
      "state_province": "NY",
      "postal_code": "10001",
      "country": "US",
      "address_type": "physical"
    }
  ],
  "schedules": [
    {
      "freq": "WEEKLY",
      "wkst": "TU",
      "opens_at": "09:00",
      "closes_at": "13:00",
      "description": "Food distribution every Tuesday morning"
    }
  ]
}
```

## Implementation Best Practices

### 1. Data Quality Assurance
- **Geocoding**: All locations are geocoded with fallback providers to ensure accurate coordinates
- **Validation**: LLM-based validation detects and corrects data quality issues
- **Deduplication**: Reconciler prevents duplicate organizations and services
- **Incremental Updates**: Only changed data is updated to maintain data integrity

### 2. HSDS Compliance Checklist
- ✅ Use UUIDs for all `id` fields (RFC 4122 compliant)
- ✅ Include required fields for each object type
- ✅ Follow proper relationship modeling (1:1 and 1:many)
- ✅ Validate against JSON schemas before storage
- ✅ Maintain proper metadata for change tracking
- ✅ Use standard status values (active, inactive, temporarily closed)
- ✅ Format schedules using RRULE specification
- ✅ Store coordinates as decimal degrees (latitude/longitude)

### 3. Common Patterns

#### Pattern: Creating a New Food Pantry
```python
# 1. Create organization
org = Organization(
    name="Food Pantry Name",
    description="What they do",
    email="contact@pantry.org"
)

# 2. Create location
location = Location(
    name="Distribution Site",
    location_type="physical",
    latitude=40.7128,
    longitude=-74.0060
)

# 3. Create service
service = Service(
    name="Food Distribution",
    description="Emergency food assistance",
    status="active"
)

# 4. Link service to location
service_at_location = ServiceAtLocation(
    service_id=service.id,
    location_id=location.id
)
```

#### Pattern: Handling Schedule Data
```python
schedule = {
    "freq": "WEEKLY",  # Frequency: DAILY, WEEKLY, MONTHLY
    "wkst": "MO",      # Week start day
    "opens_at": "09:00",
    "closes_at": "17:00",
    "description": "Regular business hours"
}
```

## Troubleshooting HSDS Implementation

### Common Issues and Solutions

1. **Missing Required Fields**
   - Check `type_defs.py` for required fields
   - Use validator to identify missing data
   - Provide defaults where appropriate

2. **Invalid Coordinates**
   - Ensure latitude is between -90 and 90
   - Ensure longitude is between -180 and 180
   - Use geocoding service for address-based lookup

3. **Schedule Format Errors**
   - Use RRULE format for recurring schedules
   - Times must be in HH:MM format (24-hour)
   - Day codes: MO, TU, WE, TH, FR, SA, SU

4. **Relationship Integrity**
   - Always create parent objects before children
   - Use proper foreign key references
   - Maintain referential integrity in database

## Further Reading

- **HSDS Specification**: See [`/docs/HSDS/README.md`](HSDS/README.md) for complete documentation
- **API Documentation**: [`/docs/api.md`](api.md) for endpoint details
- **Architecture**: [`/docs/architecture.md`](architecture.md) for system design
- **Reconciler**: [`/docs/reconciler.md`](reconciler.md) for data processing pipeline
