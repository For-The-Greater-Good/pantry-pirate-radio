# Validator Service

The validator service is a critical component in the data processing pipeline that enriches, validates, and scores HSDS data between LLM processing and reconciliation. It ensures data quality through geocoding enrichment, validation rules, and confidence scoring before records enter the database.

## Overview

The validator acts as a quality control gateway in the data pipeline, processing job results from the LLM queue. It enriches location data with missing geocoding information, validates the data against business rules, calculates confidence scores, and routes high-quality data to the reconciler while flagging or rejecting problematic records.

The validator implements:
- **Multi-provider geocoding enrichment** for missing coordinates or addresses
- **Comprehensive validation rules** to detect test data, invalid coordinates, and geographic inconsistencies
- **Confidence scoring algorithm** (0-100 scale) to assess data quality
- **Redis-based distributed caching** for geocoding results
- **Circuit breaker pattern** for provider reliability
- **Prometheus metrics** for monitoring and alerting

## Architecture

### Position in Pipeline

```plaintext
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Scrapers   │───►│     LLM     │───►│  Validator  │───►│ Reconciler  │───►│ HAARRRvest  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ Geocoding APIs  │
                                    │ - ArcGIS        │
                                    │ - Google Maps   │
                                    │ - Nominatim     │
                                    │ - Census        │
                                    └─────────────────┘
```

### Core Components

1. **Base Components**
   - `ValidationService`: Base class providing database and Redis connections
   - `BaseValidator`: Abstract validator interface for extensibility

2. **Processing Components**
   - `ValidationProcessor`: Main job processing logic and orchestration
   - `JobProcessor`: RQ worker entry point for queue processing

3. **Enrichment Components**
   - `GeocodingEnricher`: Multi-provider geocoding with fallback
   - Circuit breaker for provider reliability
   - TTL-based Redis caching for API efficiency

4. **Validation Components**
   - `ValidationRules`: Rule engine for data quality checks
   - `ConfidenceScorer`: Scoring algorithm (0-100 scale)
   - Geographic boundary validation (US states including AK/HI)

5. **Infrastructure Components**
   - `ValidatorConfig`: Configuration management
   - `MetricsCollector`: Prometheus metrics integration
   - Queue management for RQ job processing

## Key Features

### Geocoding Enrichment

The validator enriches location data through intelligent geocoding:

1. **Missing Coordinates**: When locations lack latitude/longitude, the validator geocodes addresses using multiple providers in fallback order
2. **Missing Addresses**: When coordinates exist but addresses are missing, reverse geocoding populates address fields
3. **Postal Code Enrichment**: Missing postal codes are filled using geocoding results

**Provider Fallback Chain**:
```python
providers = ["arcgis", "google", "nominatim", "census"]
```

Each provider is tried sequentially until successful geocoding is achieved. Failed providers trigger circuit breakers to prevent cascading failures.

### Confidence Scoring Algorithm

The validator calculates confidence scores (0-100) based on multiple factors:

**Critical Failures (Score = 0-5)**:
- Missing coordinates after enrichment attempts (0)
- Invalid 0,0 or near-zero coordinates (0)
- Coordinates outside US bounds (5)
- Test data patterns detected (5)

**Major Deductions**:
- Placeholder addresses like "123 Main St" (-75 points)
- Coordinates outside claimed state bounds (-20 points)

**Geocoding Quality Deductions**:
- Census geocoder results (-10 points)
- Fallback/state centroid geocoding (-15 points)

**Minor Deductions**:
- Missing postal code after enrichment (-5 points)
- Missing city after enrichment (-10 points)

### Validation Rules

The validator applies comprehensive rules to ensure data quality:

1. **Coordinate Validation**
   - Detects and rejects 0,0 coordinates (null island)
   - Validates coordinates within US boundaries (including Alaska and Hawaii)
   - Verifies coordinates match claimed state boundaries

2. **Test Data Detection**
   - Identifies test patterns in names, cities, and addresses
   - Detects test postal codes (00000, 99999, 12345, etc.)
   - Flags placeholder addresses

3. **Geographic Consistency**
   - Ensures coordinates fall within continental US or AK/HI bounds
   - Validates state codes against known US states
   - Checks coordinate-state alignment

4. **Data Completeness**
   - Tracks missing critical fields
   - Calculates field completeness percentages
   - Flags incomplete records for review

### Redis-Based Caching

The validator implements distributed caching for geocoding results:

- **Cache Key Format**: `geocoding:{provider}:{address_hash}`
- **TTL Configuration**: Default 86400 seconds (24 hours)
- **Cache Metrics**: Hit/miss rates tracked for optimization

### Circuit Breaker Pattern

Provider reliability is ensured through circuit breakers:

- **Failure Threshold**: 5 consecutive failures (configurable)
- **Cooldown Period**: 300 seconds before retry (configurable)
- **Automatic Recovery**: Circuit resets after successful request

### Retry Logic

The validator implements exponential backoff with jitter:

```python
base_delay = 2**attempt  # 1s, 2s, 4s
jitter = random.uniform(0, 0.5)  # Add 0-0.5s jitter
delay = base_delay + jitter
```

## Configuration

### Environment Variables

```bash
# Core Settings
VALIDATOR_ENABLED=true                      # Enable/disable validator (default: true)
VALIDATOR_QUEUE_NAME=validator              # RQ queue name (default: "validator")
VALIDATOR_REDIS_TTL=3600                    # Redis TTL in seconds (default: 3600)
VALIDATOR_LOG_DATA_FLOW=false               # Enable detailed logging (default: false)
VALIDATOR_ONLY_HSDS=true                    # Only validate HSDS jobs (default: true)

# Validation Thresholds
VALIDATOR_CONFIDENCE_THRESHOLD=0.7          # Minimum confidence score (default: 0.7)
VALIDATION_REJECTION_THRESHOLD=10           # Score below this is rejected (default: 10)

# Enrichment Settings
VALIDATOR_ENRICHMENT_ENABLED=true           # Enable geocoding enrichment (default: true)
ENRICHMENT_GEOCODING_PROVIDERS=["arcgis", "google", "nominatim", "census"]
ENRICHMENT_TIMEOUT=30                       # Geocoding timeout in seconds
ENRICHMENT_CACHE_TTL=86400                  # Cache TTL in seconds (24 hours)

# Provider Configuration
ENRICHMENT_PROVIDER_CONFIG={
    "arcgis": {
        "circuit_breaker_threshold": 5,
        "circuit_breaker_cooldown": 300
    },
    "google": {
        "circuit_breaker_threshold": 3,
        "circuit_breaker_cooldown": 600
    }
}

# Worker Settings
VALIDATOR_WORKERS=1                         # Number of worker processes
VALIDATOR_MAX_RETRIES=3                     # Max retry attempts
VALIDATOR_RETRY_DELAY=1                     # Initial retry delay in seconds
VALIDATOR_BATCH_SIZE=100                    # Jobs per batch
VALIDATOR_TIMEOUT=600                       # Job timeout in seconds
```

### Feature Flags

Control which validation checks are performed:

```python
VALIDATOR_VALIDATE_GEOCODING=true           # Validate geographic data
VALIDATOR_VALIDATE_PHONE_NUMBERS=true       # Validate phone formats
VALIDATOR_VALIDATE_SCHEDULES=true           # Validate schedule data
VALIDATOR_VALIDATE_SERVICES=true            # Validate service records
VALIDATOR_VALIDATE_ADDRESSES=true           # Validate address formats
VALIDATOR_VALIDATE_EMAILS=false             # Email validation (disabled by default)
VALIDATOR_VALIDATE_URLS=false               # URL validation (disabled by default)
```

## Validation Rules

### Critical Rules (Automatic Rejection)

1. **Missing Coordinates After Enrichment**
   - If geocoding fails across all providers
   - Results in confidence score = 0
   - Record is rejected

2. **Zero Coordinates Detection**
   - Exact 0,0 coordinates (null island)
   - Near-zero coordinates (within 0.001 degrees)
   - Results in confidence score = 0

3. **Geographic Boundary Violations**
   - Coordinates outside US bounds
   - Continental US: 24.5°N to 49.5°N, -125°W to -66.5°W
   - Alaska and Hawaii handled separately

4. **Test Data Patterns**
   - Keywords: "test", "demo", "example", "sample", "dummy"
   - Test postal codes: 00000, 99999, 12345
   - Results in confidence score = 5

### Major Rules (Significant Deductions)

1. **Placeholder Addresses**
   - "123 Main Street", "1 Test Avenue"
   - Regex patterns for generic addresses
   - Deduction: -75 points

2. **State Boundary Mismatch**
   - Coordinates outside claimed state
   - Deduction: -20 points

### Quality Rules (Minor Deductions)

1. **Geocoding Source Quality**
   - Census geocoder: -10 points
   - Fallback/centroid: -15 points

2. **Missing Fields**
   - No postal code: -5 points
   - No city: -10 points

## Confidence Scoring

### Score Ranges

- **80-100**: Verified - High confidence, ready for production
- **10-79**: Needs Review - Manual verification recommended
- **0-9**: Rejected - Critical issues, excluded from processing

### Organization Scoring

Organizations inherit scores from their locations:
- Average of all location scores
- Heavily penalized if any location is rejected
- Maximum score of 50 if any location fails

### Service Scoring

Services inherit confidence from associated locations:
- Base score from location confidence
- Minor deductions for missing service details
- -5 points for missing name or description

## Integration Points

### LLM Integration

The validator receives `JobResult` objects from the LLM queue:

```python
# LLM routes to validator when enabled
if settings.VALIDATOR_ENABLED:
    validator_job_id = enqueue_to_validator(job_result)
```

### Reconciler Integration

After validation, jobs are forwarded to the reconciler:

```python
# Enqueue to reconciler after validation
reconciler_job_id = enqueue_to_reconciler(job_result)
```

The reconciler receives enriched and scored data with:
- Added coordinates from geocoding
- Confidence scores for each entity
- Validation status (verified/needs_review/rejected)
- Enrichment source tracking

## Metrics and Monitoring

### Prometheus Metrics

```python
# Job Metrics
validator_jobs_total                        # Total jobs processed
validator_jobs_passed                       # Jobs that passed validation
validator_jobs_failed                       # Jobs that failed validation
validator_processing_seconds                # Processing time histogram

# Queue Metrics
validator_queue_size                        # Current queue depth
validator_active_workers                    # Active worker count

# Rejection Metrics
validator_locations_rejected_total          # Total rejected locations
validator_rejection_rate                    # Percentage rejected (0-100)
validator_locations_rejected_by_reason      # Rejection reason breakdown
```

### Monitoring Endpoints

- **Metrics**: `/metrics` - Prometheus-compatible metrics
- **Health**: `/health/validator` - Service health check
- **Queue Status**: Via RQ dashboard at `http://localhost:9181`

### Key Performance Indicators

1. **Rejection Rate**: Target < 5% for production data
2. **Enrichment Success**: Target > 90% for geocoding
3. **Processing Time**: Target < 5 seconds per job
4. **Cache Hit Rate**: Target > 60% for geocoding

## Usage Examples

### Basic Validation Job Processing

```python
from app.validator import process_validation_job
from app.llm.queue.models import JobResult

# Process a job through validation
job_result = JobResult(
    job_id="123",
    status="completed",
    data={
        "organization": {...},
        "locations": [...],
        "services": [...]
    }
)

# Validation automatically enriches and scores the data
validated_result = process_validation_job(job_result)

# Check results
print(f"Status: {validated_result['status']}")
print(f"Confidence scores added: {validated_result['data']}")
```

### Manual Enrichment

```python
from app.validator.enrichment import GeocodingEnricher

enricher = GeocodingEnricher()

# Enrich a single location
location = {
    "name": "Food Bank",
    "address": "123 Main St",
    "city": "New York",
    "state": "NY"
}

enriched_location, source = enricher.enrich_location(location)
print(f"Coordinates: {enriched_location['latitude']}, {enriched_location['longitude']}")
print(f"Source: {source}")
```

### Confidence Scoring

```python
from app.validator.rules import ValidationRules
from app.validator.scoring import ConfidenceScorer

validator = ValidationRules()
scorer = ConfidenceScorer()

# Validate and score a location
location = {...}
validation_results = validator.validate_location(location)
confidence_score = scorer.calculate_score(location, validation_results)
status = scorer.get_validation_status(confidence_score)

print(f"Score: {confidence_score}, Status: {status}")
```

### Configuration Management

```python
from app.validator.config import get_validator_config

config = get_validator_config()
print(f"Enabled: {config.enabled}")
print(f"Rejection threshold: {config.confidence_threshold}")
print(f"Queue name: {config.queue_name}")
```

## Troubleshooting

### Common Issues

1. **All locations being rejected**
   - Check `VALIDATION_REJECTION_THRESHOLD` setting
   - Verify geocoding providers are configured
   - Check API keys for geocoding services

2. **Geocoding failures**
   - Verify network connectivity
   - Check provider API limits
   - Review circuit breaker states in Redis

3. **Slow processing**
   - Increase `VALIDATOR_WORKERS` for parallelization
   - Check geocoding cache hit rates
   - Review provider response times

4. **Memory issues**
   - Reduce `VALIDATOR_BATCH_SIZE`
   - Check Redis memory usage
   - Monitor worker memory consumption

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
VALIDATOR_LOG_DATA_FLOW=true
LOG_LEVEL=DEBUG
```

### Monitoring Commands

```bash
# Check queue status
./bouy exec worker rq info --queue validator

# View recent failures
./bouy exec worker rq failed --queue validator

# Check Redis cache
./bouy exec cache redis-cli
> KEYS geocoding:*
> GET metrics:geocoding:cache:hits
```

## Performance Considerations

1. **Geocoding API Limits**
   - Implement rate limiting per provider
   - Use caching aggressively
   - Consider batch geocoding for bulk operations

2. **Redis Memory Management**
   - Monitor cache size with TTL expiration
   - Use cache eviction policies if needed
   - Consider separate Redis instance for caching

3. **Worker Scaling**
   - Scale workers based on queue depth
   - Use supervisor for process management
   - Monitor worker memory and CPU usage

4. **Database Impact**
   - Batch database updates when possible
   - Use connection pooling
   - Monitor query performance

## Future Enhancements

1. **Machine Learning Integration**
   - Train models on validation outcomes
   - Improve confidence scoring accuracy
   - Automated threshold adjustment

2. **Additional Validation Rules**
   - Business hours validation
   - Service area polygon checks
   - Duplicate detection across sources

3. **Enhanced Geocoding**
   - Support for international addresses
   - Indoor/suite-level geocoding
   - What3Words integration

4. **Reporting and Analytics**
   - Validation report generation
   - Trend analysis over time
   - Source quality scoring