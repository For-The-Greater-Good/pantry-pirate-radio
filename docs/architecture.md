# Pantry Pirate Radio Architecture

> **📚 Documentation Hub**: For complete project documentation including scrapers, API reference, deployment guides, and more, see the **[Documentation Index](INDEX.md)**.

## Overview

Pantry Pirate Radio is a modular food security data aggregation system built with FastAPI, featuring independently operable searchers aligned with the Human Services Data Specification (HSDS). As part of the FTGG initiative, it connects scattered resources through a single, intuitive interface while adhering to strict ethical principles:

- No collection of personal data
- Aggregation of only publicly available information
- Focus on accessibility and ease of use
- Open source and transparent operations

Each searcher can run as a standalone service or as an integrated component, providing flexibility in deployment and scaling. The FastAPI framework provides a robust foundation for type safety through Pydantic, modular architecture, and asynchronous Python development.

### Data Model

The system fully implements OpenReferral's Human Services Data Specification (HSDS) standard. All schema details can be found in the docs/HSDS directory.

- Core HSDS objects:
  - Organization: Food pantry/provider details
  - Service: Food distribution programs
  - Location: Physical service locations
  - Service_at_Location: Service availability
- Supporting HSDS objects:
  - Address: Location details
  - Schedule: Operating hours
  - Phone: Contact information
  - Language: Supported languages
  - Service_Area: Coverage boundaries
  - Accessibility: Facility access info
- All searchers normalize to HSDS format
- Validation via Pydantic models
- Common taxonomy for services

### Taxonomy Mapping

- HSDS taxonomy implementation:
  - Services taxonomy: Food distribution categories
  - Accessibility taxonomy: Facility features
  - Language taxonomy: ISO 639-1/2 codes
  - Service area taxonomy: Geographic boundaries
- Source mapping requirements:
  - Each searcher must provide taxonomy mappings
  - Maps source-specific terms to HSDS standard
  - Preserves original terms in attributes
  - Documents mapping decisions
- Common food service types:
  - food-pantry: General food distribution
  - meals-served: Prepared meal service
  - grocery-delivery: Home delivery service
  - specialty-food: Dietary/cultural specific
  - emergency-food: Crisis/immediate assistance
- Accessibility features:
  - wheelchair: Wheelchair accessible
  - parking: Accessible parking
  - restroom: ADA compliant facilities
  - asl: Sign language support
  - mobility: Mobility assistance available

### Geographic Scope

- Designed for United States coverage
- Latitude range: 25°N (Southern Florida) to 49°N (Northern border)
- Longitude range: -125°W (Western Washington) to -67°W (Eastern Maine)
- Coordinate calculations optimized for continental US distances

## Core Components

### 1. Content Deduplication Store

The content store prevents duplicate LLM processing by tracking all scraped content using SHA-256 hashing.

#### Architecture

```python
class ContentStore:
    """Content-addressable storage for deduplication"""

    def store_content(self, content: str, metadata: dict) -> ContentEntry:
        """Store content and check if already processed"""
        content_hash = self.hash_content(content)

        # Check if already processed
        if result := self.get_result(content_hash):
            return ContentEntry(
                hash=content_hash,
                status="completed",
                result=result,
                job_id=self.get_job_id(content_hash)
            )

        # Store new content
        self._store_to_file(content_hash, content, metadata)
        self._update_index(content_hash, "pending")
        return ContentEntry(hash=content_hash, status="pending")
```

#### Key Features

- **SHA-256 Hashing**: Deterministic content identification
- **SQLite Index**: Fast lookups with status tracking
- **File Storage**: Organized by hash prefix (e.g., `ab/cd/abcdef...json`)
- **Thread-Safe**: Handles concurrent access from multiple scrapers
- **Transparent Integration**: Works seamlessly with existing pipeline

#### Integration Points

1. **Scraper Integration** (`app/scraper/utils.py`):
   ```python
   def queue_for_processing(self, content: str, job_metadata: dict):
       # Check content store first
       content_store = get_content_store()
       if content_store:
           entry = content_store.store_content(content, job_metadata)
           if entry.status == "completed":
               return entry.job_id  # Skip LLM processing

       # Queue for processing if new
       job = enqueue_llm_job(content, job_metadata)
       return job.id
   ```

2. **Worker Integration** (`app/llm/queue/processor.py`):
   ```python
   def process_job(job: LLMJob):
       # Process with LLM
       result = llm_provider.process(job.content)

       # Store result in content store
       content_store = get_content_store()
       if content_store and "content_hash" in job.metadata:
           content_store.store_result(
               job.metadata["content_hash"],
               result.text,
               job.id
           )
   ```

3. **HAARRRvest Sync**: Content store is automatically synced to HAARRRvest repository for durable backup

#### Monitoring

```bash
# Content store management using bouy
./bouy content-store status

=== Content Store Summary ===
Total Content: 15,234
Processed: 14,892 (97.8%)
Pending: 342
Store Size: 156.3 MB

Deduplication Rate: 23.4%
Space Saved: 48.2 MB

# Generate detailed report
./bouy content-store report

# Find duplicate content
./bouy content-store duplicates

# Show storage efficiency
./bouy content-store efficiency
```

### 2. Search Orchestration Layer

The search orchestrator manages the execution of scrapers through the bouy command interface, running them within unified Docker containers.

#### Scraper Discovery

```bash
# List available scrapers using bouy
./bouy scraper --list

Available scrapers:
  - sample
  - the_food_pantries_org
  - vivery_api
  - nyc_efap_programs
  - ... (30+ scrapers total)
```

#### Scraper Execution

```bash
# Run specific scraper
./bouy scraper nyc_efap_programs

# Run all scrapers sequentially
./bouy scraper --all

# Run scrapers in parallel (scouting party mode)
./bouy scraper scouting-party      # Default: 5 concurrent
./bouy scraper scouting-party 10   # Custom concurrency

# Test scraper without processing (dry run)
./bouy scraper-test nyc_efap_programs
./bouy scraper-test --all
```

```python
class SearchOrchestrator:
    """Manages scraper execution through unified Docker image"""

    async def execute_scraper(self, name: str) -> None:
        """Execute a specific scraper via unified image"""
        try:
            # Scrapers run in unified image with scraper command
            process = await asyncio.create_subprocess_exec(
                "python", "-m", "app.scraper", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise ScraperError(f"Scraper {name} failed: {stderr.decode()}")
        except Exception as e:
            self.handle_scraper_error(name, e)
```

#### Configuration

```python
class OrchestratorConfig(BaseModel):
    """Configuration for search orchestrator"""
    cron_schedule: str = Field(
        default="0 */4 * * *",  # Every 4 hours
        description="Cron schedule for scraper execution"
    )
    max_concurrent: int = Field(
        default=5,
        ge=1,
        description="Maximum concurrent scrapers"
    )
    timeout: int = Field(
        default=3600,
        ge=0,
        description="Scraper timeout in seconds"
    )
```

### 3. Scraper Layer

#### Base Scraper

```python
from abc import ABC, abstractmethod
from typing import Optional, List
from pydantic import BaseModel

class BaseScraper(ABC):
    """Abstract base class for all scraper implementations"""

    @abstractmethod
    async def scrape(self) -> None:
        """Execute scraping operation and write to Redis queue"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check scraper health status"""
        pass
```

#### Scraper Types

- `APIClient`: For REST API-based providers
- `WebScraper`: For web scraping providers
- Each scraper:
  - Runs as a process in the orchestrator container
  - Writes directly to Redis queue
  - Handles its own error recovery
  - Reports health status

#### Scraper Resilience

- Client-controlled scraping parameters:
  ```python
  class ScraperConfig(BaseModel):
      user_agent: Optional[str]
      respect_robots_txt: bool = True
      rate_limit: Optional[RateLimit]
      timeout: Optional[int]

  class RateLimit(BaseModel):
      requests_per_minute: int
      delay_ms: int
  ```

- Default fallback behavior:
  - Standard user agent if none specified
  - Robots.txt respected by default
  - Conservative rate limiting
  - Reasonable timeout defaults
- Error handling:
  - Automatic retry on temporary failures
  - Circuit breaking on persistent errors
  - Detailed error reporting
  - Fallback strategies per source

#### Search Results Interface

- Standardized result format using HSDS Pydantic models
- Raw search results sent to registry
- Metadata requirements:
  - Search parameters
  - Source identification
  - Timestamp information
  - Geographic coverage

### 4. Database Layer

- PostgreSQL with PostGIS for geographic data
- SQLAlchemy models mapped to HSDS schema
- Manages data persistence and versioning
- Handles data validation and integrity:
  - Schema compliance checks
  - Geographic data validation
  - Relationship integrity
  - Version tracking
- Export functionality:
  - JSON API responses
  - CSV data exports
  - Geographic data exports
  - Audit trail exports
- Performance optimization:
  - Spatial indexing
  - Query optimization
  - Caching strategies
  - Batch operations

### 5. Search Request Processor

#### Request Normalization

- Primary responsibility for search request transformation:
  ```python
  class SearchProcessor:
      async def normalize_request(self, request: SearchRequest) -> NormalizedRequest:
          """Convert all requests to internal HSDS format"""
          # Handle coordinate systems
          # Validate parameters
          # Apply radius limits
          return normalized
  ```
- Large area request handling:
  - Detects requests exceeding 80-mile diagonal
  - Calculates optimal grid pattern
  - Generates sub-requests with proper bounds
  - Manages sub-request distribution

- Request format standardization:
  ```python
  def clamp_coordinates(lat: float, lon: float) -> Tuple[float, float]:
      """Clamp coordinates to continental US bounds"""
      lat = min(49.0, max(25.0, lat))
      lon = min(-67.0, max(-125.0, lon))
      return lat, lon
  ```

- Enhanced deduplication:
  ```python
  async def generate_service_key(service: HSDSService) -> str:
      """Generate composite key for deduplication"""
      clean_name = normalize_string(service.name)
      clean_addr = normalize_address(service.location)
      lat = round(service.coordinates.lat, 3)
      lon = round(service.coordinates.lon, 3)
      return f"{clean_name}-{clean_addr}-{lat},{lon}"
  ```

#### Geographic Partitioning

- Supports two search input types:
  - Point-based: Generates bounding box from point + radius
  - Bounding box: Direct geographic bounds input
- Handles large bounding boxes through partitioning:
  ```python
  def calculate_diagonal_distance(north: float, south: float,
                                east: float, west: float) -> float:
      """Calculate diagonal distance of bounding box in miles"""
      lat_diff = abs(north - south) * 69
      avg_lat = math.radians((north + south) / 2)
      lon_diff = abs(east - west) * math.cos(avg_lat) * 69
      return math.sqrt(lat_diff**2 + lon_diff**2)
  ```
- Grid generation strategy:
  ```python
  def generate_search_grid(bounds: BoundingBox,
                          max_diagonal: float = 80.0) -> List[BoundingBox]:
      """Generate sub-boxes for large area searches"""
      diagonal = calculate_diagonal_distance(bounds)
      splits = math.ceil(diagonal / max_diagonal)
      return partition_bounds(bounds, splits)
  ```

#### Result Aggregation

- Manages results from request partitioning:
  - Collects responses from all sub-searches
  - Maintains original request context
  - Tracks sub-request completion status
  - Handles partial or failed sub-requests
- HSDS Transformation:
  - Normalizes all source data to HSDS format via Pydantic
  - Maps provider-specific fields to standard schema
  - Validates required HSDS fields
  - Preserves source-specific data in attributes
- Deduplication strategy:
  - Primary key based on lat/long coordinates
  - Merges data from overlapping areas
  - Preserves most complete entry when duplicated
  - Maintains source attribution
- Response assembly:
  - Reconstructs complete result set
  - Validates against HSDS schema
  - Includes coverage metadata
  - Reports any gaps in coverage

### 6. Unified Geocoding Service

The unified geocoding service provides centralized, cached, and rate-limited geocoding functionality across all components, dramatically reducing API usage and improving performance. Recent improvements include zero-coordinate detection and exhaustive provider fallback.

#### Architecture

```python
class UnifiedGeocodingService:
    """Centralized geocoding with caching, zero detection, and automatic provider fallback"""
    
    def __init__(self):
        self.cache = RedisCache(ttl=30*24*3600)  # 30-day TTL
        self.providers = [
            ArcGISGeocoder(rate_limit=0.5),  # Primary
            NominatimGeocoder(rate_limit=1.1)  # Fallback
        ]
        self.zero_coordinate_detection = True  # Detect invalid 0,0 coordinates
        self.exhaustive_fallback = True  # Try all providers before failing
```

#### Key Features

1. **Advanced Caching Strategy**
   - **30-day Redis cache** with SHA256 keys for security
   - **90%+ cache hit rate** in production
   - Automatic cache key generation from address components
   - Thread-safe concurrent access
   
2. **Provider Management**
   - **ArcGIS** as primary provider (faster, more accurate)
   - **Nominatim** as automatic fallback
   - Transparent failover on errors or rate limits
   - Provider-specific rate limiting:
     - ArcGIS: 0.5 seconds between requests
     - Nominatim: 1.1 seconds (respects OSM guidelines)
   - **Zero Coordinate Detection**: Automatically detects and rejects invalid 0,0 coordinates
   - **Exhaustive Fallback**: Tries all available providers before returning failure

3. **Performance Optimization**
   ```python
   async def geocode(self, address: str) -> Optional[Coordinates]:
       # Generate secure cache key
       cache_key = hashlib.sha256(
           address.lower().strip().encode()
       ).hexdigest()
       
       # Check cache first
       if cached := await self.cache.get(cache_key):
           return cached  # ~90% of requests hit cache
       
       # Try providers with automatic fallback
       for provider in self.providers:
           try:
               coords = await provider.geocode(address)
               if coords:
                   await self.cache.set(cache_key, coords)
                   return coords
           except ProviderError:
               continue  # Automatic fallback
   ```

4. **Error Handling**
   - Graceful degradation on provider failures
   - Comprehensive error logging with context
   - Retry logic with exponential backoff
   - Circuit breaker pattern for provider health

#### Integration Points

1. **Scraper Integration**
   ```python
   # app/scraper/utils.py
   from app.core.geocoding import geocode_address
   
   async def geocode_with_fallback(address: str) -> Optional[Coordinates]:
       """Wrapper maintaining backward compatibility"""
       return await geocode_address(address)
   ```

2. **Reconciler Integration**
   - Uses geocoding for address validation
   - Enriches location data with coordinates
   - Handles batch geocoding efficiently

3. **API Integration**
   - Geographic search validation
   - Address-to-coordinate conversion
   - Coverage area calculations

#### Configuration

```bash
# Environment variables
ARCGIS_API_KEY=your_api_key_here
GEOCODING_CACHE_TTL=2592000  # 30 days in seconds
GEOCODING_RATE_LIMIT_ARCGIS=0.5
GEOCODING_RATE_LIMIT_NOMINATIM=1.1
REDIS_GEOCODING_PREFIX=geo:
```

#### Monitoring and Metrics

```python
# Prometheus metrics
GEOCODING_REQUESTS = Counter(
    'geocoding_requests_total',
    'Total geocoding requests',
    ['provider', 'cache_hit']
)

GEOCODING_LATENCY = Histogram(
    'geocoding_latency_seconds',
    'Geocoding request latency',
    ['provider']
)

GEOCODING_ERRORS = Counter(
    'geocoding_errors_total',
    'Geocoding errors by provider',
    ['provider', 'error_type']
)
```

#### Benefits

- **90% reduction in external API calls** through intelligent caching
- **100% uptime** through automatic provider fallback
- **Improved response times** with cache hits < 10ms
- **Cost savings** on metered geocoding APIs
- **GDPR compliance** through secure cache key generation
- **Centralized rate limiting** prevents API throttling

### 7. Core Infrastructure

#### HTTP Client

- HTTPX for async HTTP requests
- Rate limiting per searcher instance
- Retry logic with exponential backoff
- Request header management

#### Configuration Management

```python
class SearcherConfig(BaseModel):
    """Configuration for searcher instances"""
    mode: Literal["standalone", "integrated", "export"]
    port: Optional[int]  # Required for standalone
    export_path: Optional[str]  # Required for export mode
    health_check: HealthCheckConfig
```

## Deployment Models

### 1. Unified Docker Image Architecture

All services run from a single unified Docker image (`pantry-pirate-radio:latest`) with different entry points:

#### Service Architecture
- **Unified Image**: Single image built with all dependencies and code
- **Service Selection**: Entry point script (`docker-entrypoint.sh`) routes to appropriate service
- **Shared Volumes**: Common data volumes across all services
- **Configuration**: Environment-based service configuration

#### Core Services (defined in `.docker/compose/base.yml`):
- `app`: FastAPI server for API endpoints (port 8000)
- `worker`: LLM processing workers with Claude CLI support
- `recorder`: Job archival with volume mounts
- `reconciler`: Data consistency service
- `haarrrvest-publisher`: Automated data publishing to HAARRRvest
- `scraper`: Data collection service
- `db`: PostgreSQL 15 with PostGIS 3.3 extensions
- `cache`: Redis for queue and caching
- `db-init`: Database initialization with SQL dumps
- `datasette`: SQLite data browser (production mode)

### 2. Bouy-Managed Deployment

All Docker operations are managed through the bouy command interface:

```bash
# Start services (development mode by default)
./bouy up

# Production mode with all services
./bouy up --prod

# With database initialization from SQL dumps
./bouy up --with-init

# Scale worker containers
./bouy up --scale worker=3

# Test mode for running tests
./bouy up --test
```

#### Deployment Modes:
- **Development** (`--dev` or default): Hot reload, debug logging, volume mounts
- **Production** (`--prod`): Optimized, includes Datasette, production logging
- **Test** (`--test`): Isolated test environment
- **With Init** (`--with-init`): Includes database initialization from SQL dumps

### 3. Production Deployment

#### Bouy Production Commands:
```bash
# Start production environment
./bouy up --prod --with-init

# Monitor services
./bouy ps
./bouy logs -f app worker

# Health checks
./bouy exec app curl http://localhost:8000/health
```

#### Persistent Volumes:
- `postgres_data`: PostgreSQL database files
- `redis_data`: Redis persistence
- `haarrrvest_repo`: HAARRRvest repository clone
- `app_data`: Shared application data
- `claude_config`: Claude CLI authentication
- `outputs`: Processed data outputs

#### Production Features:
- Unified image reduces deployment complexity
- Health checks on all critical services
- Automatic restart policies
- Resource limits enforced
- Datasette for data exploration

## Data Flow

```plaintext
┌─────────────┐
│   Search    │
│ Orchestrator│
│  [Scrapers] │──────┐
└─────────────┘      │
                     ▼
                ┌─────────────┐
                │    Redis    │
                │    Queue    │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │   Worker    │
                │    Pool     │
                └──────┬──────┘
                       │
       ┌───────────────┴───────────────┐
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Reconciler  │ │  Recorder   │ │     LLM     │
│  Service    │ │  Service    │ │   Service   │
└──────┬──────┘ └──────┬──────┘ └─────────────┘
       │              │
       ▼              ▼
┌─────────────┐ ┌─────────────┐
│  Database   │ │  outputs/   │
└──────┬──────┘ │   Folder    │
       │        └──────┬──────┘
       ▼               │ (reads)
┌─────────────┐        ▼
│   FastAPI   │ ┌─────────────┐
│   Server    │ │ HAARRRvest  │
└─────────────┘ │ Publisher   │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │ HAARRRvest  │
                │ Repository  │
                └─────────────┘
```

The LLM Layer provides:
- HSDS field mapping with validation feedback
- Schema compliance checks with confidence scoring
- Taxonomy classification and normalization
- Field coherence validation
- Retry logic for failed alignments

## Testing Framework

### Testing with Bouy

```bash
# Run all tests and checks
./bouy test

# Run specific test types
./bouy test --pytest        # Run pytest tests
./bouy test --mypy          # Type checking
./bouy test --black         # Code formatting
./bouy test --ruff          # Linting
./bouy test --bandit        # Security scanning
./bouy test --coverage      # Tests with coverage

# Run specific test files
./bouy test --pytest tests/test_api.py
./bouy test --pytest tests/test_reconciler/

# Pass additional arguments
./bouy test --pytest -- -v -x
```

### Unit Testing with pytest

```python
import pytest
from app.searchers import BaseSearcher

@pytest.mark.asyncio
async def test_searcher_validation():
    """Test HSDS validation on searcher results"""
    searcher = MockSearcher()
    results = await searcher.search(test_query)
    assert_valid_hsds_results(results)
```

### Integration Testing

```python
@pytest.mark.integration
async def test_service_registry():
    """Test service registry with multiple searchers"""
    registry = ServiceRegistry()
    await registry.register(searcher1)
    await registry.register(searcher2)

    results = await registry.search(test_query)
    assert len(results) > 0
    assert_no_duplicates(results)
```

### Property-Based Testing

```python
from hypothesis import given, strategies as st

@given(st.floats(min_value=25, max_value=49),
       st.floats(min_value=-125, max_value=-67))
async def test_coordinate_validation(lat, lon):
    """Test coordinate validation with property-based testing"""
    processor = SearchProcessor()
    normalized = await processor.normalize_coordinates(lat, lon)
    assert 25 <= normalized.lat <= 49
    assert -125 <= normalized.lon <= -67
```

## Error Handling

### Searcher Errors

```python
class SearcherError(Exception):
    """Base class for searcher errors"""
    pass

class RateLimitError(SearcherError):
    """Raised when rate limit is exceeded"""
    pass

class ValidationError(SearcherError):
    """Raised when results fail HSDS validation"""
    pass
```

### HSDS Validation

- Schema compliance checks:
  ```python
  async def validate_hsds_result(result: Dict) -> None:
      """Validate result against HSDS schema"""
      try:
          HSDSService(**result)
      except ValidationError as e:
          log_validation_error(e)
          raise HSDSValidationError(str(e))
  ```

### Circuit Breaker Configuration

```python
class CircuitBreaker:
    """Circuit breaker for searcher resilience"""
    def __init__(self):
        self.failure_threshold: int = 5
        self.reset_timeout: int = 60
        self.state: CircuitState = CircuitState.CLOSED

    async def call(self, func: Callable) -> Any:
        """Execute function with circuit breaker pattern"""
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError()
        try:
            result = await func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
```

## Monitoring

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram

SEARCH_REQUESTS = Counter(
    'pantry_searcher_requests_total',
    'Total search requests by searcher',
    ['searcher_name']
)

SEARCH_LATENCY = Histogram(
    'pantry_searcher_latency_seconds',
    'Search request latency in seconds',
    ['searcher_name']
)
```

### Health Checks

```python
async def health_check() -> Dict[str, Any]:
    """System health check status"""
    return {
        "status": "healthy",
        "version": __version__,
        "uptime": get_uptime(),
        "searchers": await get_searcher_status(),
        "cache": await get_cache_stats(),
        "database": await get_db_stats()
    }
```

### Logging Configuration

```python
import logging.config

logging.config.dictConfig({
    "version": 1,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "detailed"
        }
    },
    "formatters": {
        "detailed": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"]
    }
})
```

### 8. Queue System

#### Configuration Management

```python
class QueueConfig(BaseModel):
    """Configuration for queue system"""
    redis_url: str = Field(..., description="Redis connection URL")
    pool_size: int = Field(
        default=10,
        ge=1,
        description="Redis connection pool size"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts for Redis operations"
    )
    retry_delay: float = Field(
        default=1.0,
        ge=0,
        description="Delay between retries in seconds"
    )
    worker_count: int = Field(
        default=1,
        ge=1,
        description="Number of worker processes"
    )
    shutdown_timeout: float = Field(
        default=30.0,
        ge=0,
        description="Graceful shutdown timeout in seconds"
    )
```

#### Job Processing

```python
class JobProcessor:
    """Manages job processing and worker lifecycle"""

    async def enqueue(
        self,
        prompt: str,
        provider_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Submit job to queue"""
        job_id = generate_job_id()
        await self.redis.set(
            f"job:{job_id}:status",
            JobStatus.PENDING.value
        )
        return job_id

    async def process(self) -> None:
        """Process jobs from queue"""
        while True:
            try:
                job = await self.get_next_job()
                if job is None:
                    await asyncio.sleep(0.1)
                    continue

                result = await self.provider.generate(
                    job.prompt,
                    **job.provider_config
                )
                await self.store_result(job.id, result)

            except Exception as e:
                self.handle_error(e)

    async def get_status(self, job_id: str) -> JobStatus:
        """Get current job status"""
        status = await self.redis.get(f"job:{job_id}:status")
        return JobStatus(status)

    async def get_result(self, job_id: str) -> Optional[str]:
        """Get job result when complete"""
        status = await self.get_status(job_id)
        if status != JobStatus.COMPLETED:
            return None
        return await self.redis.get(f"job:{job_id}:result")
```

#### Health Management

```python
class QueueHealth:
    """Queue system health monitoring"""

    async def check_health(self) -> Dict[str, Any]:
        """Perform health check of queue system"""
        return {
            "status": "healthy",
            "components": {
                "redis": await self.check_redis(),
                "workers": await self.check_workers(),
                "job_processor": await self.check_processor()
            },
            "metrics": {
                "queue_size": await self.get_queue_size(),
                "active_workers": self.worker_count,
                "processed_jobs": self.processed_count
            }
        }

    async def check_redis(self) -> bool:
        """Verify Redis connection"""
        try:
            await self.redis.ping()
            return True
        except RedisError:
            return False

    async def check_workers(self) -> Dict[str, int]:
        """Check worker status"""
        return {
            "total": self.worker_count,
            "active": await self.count_active_workers(),
            "idle": await self.count_idle_workers()
        }
```

### 9. AI Layer

#### Configuration Management

```python
class LLMConfig(BaseModel):
    """Base configuration for LLM providers"""
    model_path: str = Field(..., description="Path or identifier for the model")
    context_length: int = Field(
        default=16384,
        ge=1,
        le=32768,
        description="Maximum number of tokens in context window"
    )
    temperature: float = Field(
        default=0.1,
        ge=0,
        le=1,
        description="Lower temperature for more deterministic HSDS alignment"
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0,
        le=1,
        description="Minimum confidence score for HSDS field mappings"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts for failed alignments"
    )
    validation_feedback: bool = Field(
        default=True,
        description="Enable validation feedback loops"
    )
    max_tokens: int = Field(
        default=16384,
        ge=1,
        description="Maximum tokens to generate"
    )
    cache_ttl: int = Field(
        default=3600,
        ge=0,
        description="Cache TTL in seconds"
    )
```

#### Provider Interface

```python
class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.cache = RedisCache(ttl=config.cache_ttl)

    @abstractmethod
    async def generate(self, prompt: str) -> str | AsyncIterator[str]:
        """Generate text completion"""
        pass

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate text embeddings"""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ) -> str | AsyncIterator[str]:
        """Generate chat completion"""
        pass
```

#### Current Providers

- OpenAI Integration:
  - Uses OpenAI GPT models for HSDS alignment
  - Supports structured output with JSON schema validation
  - Configurable through OpenAI API key

- Provider Features:
  - Schema-guided HSDS mapping
  - Example-based alignment
  - Confidence scoring with thresholds
  - Validation feedback loops
  - Smart retry logic
  - Response caching
  - Field coherence checking

#### Caching Strategy

- Redis-based caching:
  ```python
  class RedisCache:
      """LLM response cache"""
      def __init__(self, ttl: int):
          self.ttl = ttl
          self.prefix = "llm:"

      async def get(self, key: str) -> Optional[str]:
          """Get cached response"""
          return await self.redis.get(f"{self.prefix}{key}")

      async def set(self, key: str, value: str) -> None:
          """Cache response with TTL"""
          await self.redis.set(
              f"{self.prefix}{key}",
              value,
              ex=self.ttl
          )
  ```

- Cache key generation:
  ```python
  def generate_cache_key(
      prompt: str,
      config: LLMConfig
  ) -> str:
      """Generate deterministic cache key"""
      config_hash = hash_config(config)
      prompt_hash = hashlib.sha256(
          prompt.encode()
      ).hexdigest()
      return f"{config_hash}:{prompt_hash}"
  ```

### 10. Reconciler Service

The reconciler service processes HSDS data from LLM outputs and integrates it into the database while maintaining data consistency and versioning.

#### Core Components

1. **Base Components**
   - `BaseReconciler`: Abstract base class providing database and Redis connections
   - Implements async context management for resource cleanup

2. **Core Components**
   - `JobProcessor`: Handles job queue processing and HSDS data extraction
   - `LocationCreator`: Manages location creation and matching
   - `OrganizationCreator`: Handles organization and identifier creation
   - `ServiceCreator`: Manages services, phones, languages, and schedules
   - `VersionTracker`: Maintains record version history
   - `ReconcilerUtils`: High-level utility wrapper

#### Data Flow

1. **Job Processing**
   ```python
   async def process_job_result(self, job_result: JobResult) -> None:
       """Process completed LLM job results"""
       data = json.loads(job_result.result.text)

       # Process organization
       if "organization" in data:
           org = data["organization"][0]
           org_id = await org_creator.create_organization(
               name=org["name"],
               description=org.get("description", ""),
               metadata=job_result.job.metadata
           )

       # Process locations and services
       if "location" in data:
           for location in data["location"]:
               location_id = await location_creator.create_location(
                   name=location["name"],
                   latitude=float(location["latitude"]),
                   longitude=float(location["longitude"])
               )
   ```

2. **Version Tracking**
   ```sql
   WITH next_version AS (
       SELECT COALESCE(MAX(version_num), 0) + 1 as version_num
       FROM record_version
       WHERE record_id = :record_id
       AND record_type = :record_type
   )
   INSERT INTO record_version (
       record_id,
       record_type,
       version_num,
       data,
       created_by
   )
   SELECT
       :record_id,
       :record_type,
       version_num,
       :data,
       :created_by
   FROM next_version
   ```

#### Metrics

```python
RECONCILER_JOBS = Counter(
    "reconciler_jobs_total",
    "Total number of jobs processed by reconciler",
    ["scraper_id", "status"]
)

LOCATION_MATCHES = Counter(
    "reconciler_location_matches_total",
    "Total number of location matches found",
    ["match_type"]
)

SERVICE_RECORDS = Counter(
    "reconciler_service_records_total",
    "Total number of service records created",
    ["has_organization"]
)
```

### 11. Recorder Service

The recorder service persists and archives job results from the LLM processing system.

#### Core Components

1. **RecorderUtils**
   - Main utility class handling recorder operations
   - Manages Redis connections and file system operations
   - Implements async context management
   - Handles job polling and processing

2. **File System Organization**
   - `outputs/`: Directory for JSON job results
     - `daily/YYYY-MM-DD/scrapers/{scraper_id}/`: Scraper job results
     - `daily/YYYY-MM-DD/processed/`: Processed LLM results
     - `latest/`: Symlink to most recent daily directory
   - Automatic directory creation and management
   - Daily summary files tracking all jobs

#### Job Result Processing

```python
async def save_completed_jobs(
    self,
    scraper_id: str | None = None
) -> list[Path]:
    """Save completed job results to JSON files."""
    paths = []
    for job_id in await self._get_completed_jobs(scraper_id):
        path = await self._process_job(job_id, self.output_dir)
        if path:
            paths.append(path)
    return paths
```

#### Archive Creation

```python
async def archive_raw_data(
    self,
    content: str,
    source_url: str,
    metadata: dict[str, Any],
) -> Path:
    """Archive raw content to compressed file."""
    archive_path = self._generate_archive_path()
    async with aiofiles.open(archive_path, "wb") as f:
        await f.write(compress_content(content, metadata))
    return archive_path
```

### 12. Worker Service

The worker system executes asynchronous tasks, particularly LLM-based HSDS data alignment operations.

#### Core Components

1. **Job Queue**
   - Redis-backed priority queue
   - Support for job dependencies
   - Batch processing capabilities
   - Dead letter queue for failed jobs

2. **Worker Process**
   ```python
   class Worker:
       """Worker process for job execution"""

       async def process_job(self, job: Job) -> None:
           """Process a single job"""
           try:
               result = await self.execute_job(job)
               await self.store_result(job.id, result)
               await self.update_status(
                   job.id,
                   JobStatus.COMPLETED
               )
           except Exception as e:
               await self.handle_job_error(job, e)
   ```

3. **Resource Management**
   ```python
   class MemoryManager:
       """Manage worker memory usage"""

       def __init__(self, max_memory_mb: int = 1024):
           self.max_memory = max_memory_mb * 1024 * 1024

       async def check_memory(self) -> bool:
           """Check if memory usage is within limits"""
           current = self.get_memory_usage()
           return current < self.max_memory
   ```

4. **Health Monitoring**
   ```python
   async def health_check(self) -> Dict[str, Any]:
       """Perform worker health check"""
       return {
           "status": "healthy",
           "worker_id": self.worker_id,
           "processed_jobs": self.processed_count,
           "failed_jobs": self.failed_count,
           "current_memory": self.get_memory_usage(),
           "uptime": self.get_uptime()
       }
   ```

### 13. HAARRRvest Publisher Service

The HAARRRvest Publisher service automates the process of publishing processed data to the HAARRRvest repository for public access.

#### Core Components

1. **Service Architecture**
   ```python
   class HAARRRvestPublisher:
       """Publisher service for HAARRRvest data repository"""

       def __init__(self):
           self.output_dir = Path("/app/outputs")
           self.data_repo_path = Path("/data-repo")
           self.check_interval = 300  # 5 minutes
           self.days_to_sync = 7
   ```

2. **Publishing Workflow**
   - Monitors `outputs/` directory for new recorder files
   - Tracks processed files to avoid duplicates
   - Creates date-based branches (e.g., `data-update-2025-01-25`)
   - Syncs data to HAARRRvest repository structure
   - Generates SQLite database for Datasette
   - Creates merge commits to main branch
   - Pushes changes to remote repository

3. **Data Operations**
   ```python
   async def process_once(self):
       """Run the publishing pipeline once"""
       # 1. Setup/update git repository
       self._setup_git_repo()

       # 2. Find new files from recorder
       new_files = self._find_new_files()

       # 3. Create feature branch
       branch_name = self._create_branch_name()

       # 4. Sync files to repository
       self._sync_files_to_repo(new_files)

       # 5. Update metadata
       self._update_repository_metadata()

       # 6. Export to SQLite
       self._export_to_sqlite()

       # 7. Run location export for maps
       self._run_location_export()

       # 8. Commit and merge
       self._create_and_merge_branch(branch_name)
   ```

4. **SQLite Export**
   - Uses `db-to-sqlite` for PostgreSQL export
   - Python fallback for environments without CLI tool
   - Creates metadata.json for Datasette
   - Optimized for map visualization queries

5. **Git Safety Features**
   - Always pulls latest changes before operations
   - Stashes uncommitted changes automatically
   - Creates unique branch names if conflicts exist
   - Never force-pushes or overwrites data
   - Uses token authentication for security

#### Configuration

```python
# Environment variables
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_personal_access_token
PUBLISHER_CHECK_INTERVAL=300  # seconds
DAYS_TO_SYNC=7  # days of historical data
```

#### Integration Points

- **Recorder Service**: Reads JSON output files from `/app/outputs`
- **Database**: Exports data via db-to-sqlite
- **HAARRRvest Repository**: Pushes data updates
- **Docker Volumes**: Persists repository state

### 14. API Frontend Layer

#### Core Design Principles
- Open access: No authentication required
- Public data only: All endpoints serve publicly available information
- Rate limiting based on fair use, not authentication
- Focus on accessibility and ease of use

#### Request Processing Pipeline
```python
async def process_search_request(request: SearchRequest) -> SearchResponse:
    """Process incoming search requests through the full pipeline"""
    # 1. Request validation and normalization
    normalized = await normalize_request(request)

    # 2. Geographic processing
    coverage = await check_coverage(normalized.bounds)
    if coverage.requires_partition:
        sub_requests = partition_request(normalized)

    # 3. Execute search across searchers
    results = await execute_distributed_search(sub_requests)

    # 4. Aggregate and format results
    response = await format_hsds_response(results)

    # 5. Add metadata
    response.metadata.coverage = coverage
    response.metadata.sources = results.sources

    return response
```

#### Endpoint Categories

1. Search Endpoints
   - Geographic area search with bounding box
   - Point-radius search for local results
   - Multi-criteria filtering (services, accessibility, languages)
   - Results support pagination and sorting

2. Resource Endpoints
   - Organization listings and details
   - Service information and availability
   - Location data with geographic context
   - Combined resource views for UI consumption

3. System Information
   - Health status for all components
   - System metrics for monitoring
   - Coverage information and statistics

#### Response Formatting
```python
class SearchResponse(BaseModel):
    """Standard search response format"""
    results: List[HSDSResource]
    metadata: ResponseMetadata
    coverage: CoverageInfo
    pagination: Optional[PaginationInfo]

class ResponseMetadata(BaseModel):
    """Metadata included with all responses"""
    timestamp: datetime
    source_count: int
    coverage_percent: float
    processing_time: float
```

#### Performance Optimizations

1. Response Caching
   - Geographic tile-based caching
   - Resource-specific caching
   - Cache invalidation on updates
   - Partial cache updates

2. Request Distribution
   - Geographic partitioning for large areas
   - Load balancing across searchers
   - Parallel request processing
   - Result merging and deduplication

3. Fair Use Management
   - Request limits based on:
     - Request size/complexity
     - Server load
     - Geographic coverage
   - Automatic request optimization
   - Clear limit documentation
   - Helpful error messages

#### Error Handling
```python
class APIError(BaseModel):
    """Standardized error response"""
    code: str
    message: str
    details: Optional[Dict[str, Any]]
    correlation_id: str
    suggestions: Optional[List[str]]
```

1. Error Categories
   - Invalid geographic bounds
   - Unsupported search criteria
   - Coverage gaps
   - System limitations
   - Temporary service issues

2. Error Responses
   - Clear error messages
   - Actionable suggestions
   - Correlation IDs for tracking
   - Relevant documentation links

#### Monitoring and Metrics

1. Request Metrics
   - Query patterns
   - Geographic distribution
   - Response times
   - Cache effectiveness

2. Result Quality
   - Coverage completeness
   - Source availability
   - Result freshness
   - Deduplication effectiveness

3. System Health
   - Component status
   - Resource utilization
   - Error rates
   - Performance trends

