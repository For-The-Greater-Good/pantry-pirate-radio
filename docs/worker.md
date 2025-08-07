# Worker System

## Overview

The worker system in Pantry Pirate Radio uses RQ (Redis Queue) for asynchronous job processing, particularly for LLM-based HSDS data alignment operations. The system manages multiple worker types, each handling specific job queues with automatic retry logic, health monitoring, and integration with the content deduplication store.

## Architecture

### RQ (Redis Queue) Components

1. **Queue System** (`app/llm/queue/`)
   - Redis-backed job queues with connection pooling
   - Separate queues for different job types: `llm`, `reconciler`, `recorder`
   - Job result TTL management (default: 30 days)
   - Connection pool with 50 max connections for concurrency

2. **Worker Types**
   - **LLM Worker**: Processes LLM alignment jobs with Claude/OpenAI
   - **Reconciler Worker**: Handles data reconciliation after LLM processing
   - **Recorder Worker**: Records job results to JSON files
   - **Simple Worker**: Generic RQ worker for other queues

3. **Job Processing Pipeline**
   ```
   Scraper → LLM Queue → LLM Worker → Reconciler Queue → Reconciler Worker
                                    ↓
                              Recorder Queue → Recorder Worker
   ```

## Configuration

### Environment Variables

```bash
# Redis Configuration
REDIS_URL=redis://cache:6379/0           # Redis connection URL
REDIS_POOL_SIZE=10                       # Connection pool size
REDIS_TTL_SECONDS=2592000                # Job result TTL (30 days)

# Worker Configuration
WORKER_COUNT=1                           # Number of workers (1-20)
LLM_WORKER_COUNT=2                       # Number of LLM workers
LLM_QUEUE_KEY=llm:jobs                   # LLM job queue key
LLM_CONSUMER_GROUP=llm-workers           # LLM consumer group

# Claude Configuration (for LLM workers)
CLAUDE_QUOTA_RETRY_DELAY=3600           # Initial retry delay (1 hour)
CLAUDE_QUOTA_MAX_DELAY=14400            # Max retry delay (4 hours)
CLAUDE_QUOTA_BACKOFF_MULTIPLIER=1.5     # Exponential backoff multiplier
```

### Queue Configuration (`app/llm/queue/queues.py`)

```python
# Redis connection with pooling
redis_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=50,
    socket_timeout=5,
    socket_connect_timeout=5,
    socket_keepalive=True
)

# Queue definitions
llm_queue = Queue("llm", connection=redis.Redis(connection_pool=redis_pool))
reconciler_queue = Queue("reconciler", connection=redis.Redis(connection_pool=redis_pool))
recorder_queue = Queue("recorder", connection=redis.Redis(connection_pool=redis_pool))
```

## Content Store Integration

The worker system integrates with the content deduplication store to prevent duplicate LLM processing:

### Deduplication Check

Before processing, workers check if content has already been processed:

```python
async def should_process_job(self, job: Job) -> bool:
    """Check if job needs processing or already has results"""
    content_store = get_content_store()
    if not content_store:
        return True  # No content store, process normally

    if "content_hash" in job.metadata:
        result = content_store.get_result(job.metadata["content_hash"])
        if result:
            # Already processed, skip LLM
            await self.store_cached_result(job.id, result)
            return False

    return True
```

### Result Storage

After successful LLM processing, results are stored in content store:

```python
async def store_llm_result(self, job: Job, result: LLMResponse) -> None:
    """Store LLM result in content store for future use"""
    content_store = get_content_store()
    if content_store and "content_hash" in job.metadata:
        content_store.store_result(
            job.metadata["content_hash"],
            result.text,
            job.id
        )
```

### Benefits

- **Cost Reduction**: Avoid redundant LLM API calls
- **Performance**: Instant results for duplicate content
- **Consistency**: Same content always produces same result
- **Durability**: Results backed up to HAARRRvest repository

## Job Processing

### RQ Job Processing (`app/llm/queue/processor.py`)

```python
def process_llm_job(job: LLMJob, provider: BaseLLMProvider) -> LLMResponse:
    """Process an LLM job with RQ."""
    # 1. Process with LLM provider
    result = provider.generate(
        prompt=job.prompt,
        format=job.format,
        config=None
    )
    
    # 2. Store in content store (if configured)
    content_store = get_content_store()
    if content_store and "content_hash" in job.metadata:
        content_store.store_result(
            job.metadata["content_hash"],
            result.text,
            job.id
        )
    
    # 3. Enqueue follow-up jobs
    reconciler_queue.enqueue_call(
        func="app.reconciler.job_processor.process_job_result",
        args=(job_result,),
        result_ttl=settings.REDIS_TTL_SECONDS
    )
    
    recorder_queue.enqueue_call(
        func="app.recorder.utils.record_result",
        args=(job_data,),
        result_ttl=settings.REDIS_TTL_SECONDS
    )
    
    return result
```

### Job Submission Example

```python
from app.llm.queue.queues import llm_queue
from app.llm.queue.models import LLMJob

# Create job
job = LLMJob(
    id="job_123",
    prompt="Align this pantry data to HSDS format...",
    format="json_schema",
    metadata={"content_hash": "abc123", "source": "scraper_x"}
)

# Enqueue job
rq_job = llm_queue.enqueue_call(
    func="app.llm.queue.processor.process_llm_job",
    args=(job, provider),
    result_ttl=2592000,  # 30 days
    failure_ttl=2592000
)
```

## Error Handling

### Claude-Specific Error Handling

```python
# Authentication errors - retry every 5 minutes
if isinstance(e, ClaudeNotAuthenticatedException):
    auth_manager = AuthStateManager(llm_queue.connection)
    auth_manager.set_auth_failed(str(e), retry_after=e.retry_after)
    # Jobs automatically retry until authentication succeeds

# Quota exceeded - exponential backoff
elif isinstance(e, ClaudeQuotaExceededException):
    auth_manager = AuthStateManager(llm_queue.connection)
    auth_manager.set_quota_exceeded(str(e), retry_after=e.retry_after)
    # Retry with exponential backoff: 1h → 1.5h → 2.25h → 4h max
```

### RQ Retry Configuration

```python
from rq import Retry

# Enqueue job with retry configuration
llm_queue.enqueue_call(
    func="app.llm.queue.processor.process_llm_job",
    args=(job, provider),
    retry=Retry(max=3, interval=[60, 300, 900]),  # 1min, 5min, 15min
    result_ttl=2592000,
    failure_ttl=2592000
)
```

## Monitoring and Management

### RQ Dashboard

Access the RQ dashboard for real-time monitoring:

```bash
# Start services with dashboard
./bouy up

# Access dashboard at http://localhost:9181
# Shows:
# - Queue sizes and job counts
# - Worker status and activity
# - Failed jobs and retry status
# - Job details and results
```

### Worker Health Monitoring

```bash
# Check worker status
./bouy ps

# View worker logs
./bouy logs worker
./bouy logs worker -f  # Follow logs

# Check specific worker health (Claude workers)
curl http://localhost:8080/health

# Response example:
{
  "provider": "claude",
  "status": "healthy",
  "authenticated": true,
  "model": "claude-sonnet-4",
  "message": "Ready to process requests"
}
```

### Queue Management with Bouy

```bash
# Monitor queue sizes
./bouy exec worker rq info

# List failed jobs
./bouy exec worker rq info --failed

# Requeue failed jobs
./bouy exec worker rq requeue --all

# Clear specific queue
./bouy exec worker rq empty llm
```

## Worker Scaling and Management

### Starting Workers

```bash
# Start single worker
./bouy up worker

# Scale workers (Docker Compose)
./bouy up --scale worker=3

# Workers with different configurations
WORKER_COUNT=5 ./bouy up worker
```

### Worker Types and Commands

```bash
# LLM Worker (with Claude authentication)
./bouy up worker  # Default, includes Claude setup

# Simple RQ workers for other queues
./bouy exec worker rq worker reconciler
./bouy exec worker rq worker recorder

# Multiple workers in one container
WORKER_COUNT=3 ./bouy up worker
```

### Graceful Shutdown

```bash
# Stop workers gracefully
./bouy down worker

# Workers will:
# 1. Stop accepting new jobs
# 2. Complete current jobs
# 3. Register death with RQ
# 4. Clean up resources
```

## Structured Output Handling

### LLM Response Format

The worker system supports structured output formats for LLM operations, particularly for HSDS data alignment tasks. This ensures consistent, validated responses that conform to the HSDS specification.

```python
class StructuredOutputFormat(TypedDict):
    """Format specification for structured output"""
    type: Literal["json_schema"]
    json_schema: Dict[str, Any]
```

### HSDS Schema Conversion

The worker uses the `SchemaConverter` to transform HSDS schema definitions into LLM-compatible JSON schemas:

```python
async def prepare_hsds_alignment_job(
    self,
    raw_data: str,
    known_fields: Optional[Dict[str, List[str]]] = None
) -> Job:
    """Prepare HSDS alignment job with structured output"""
    # Convert HSDS schema to LLM format
    schema_converter = SchemaConverter(schema_path)
    hsds_schema = schema_converter.convert_to_llm_schema("organization")

    # Configure structured output
    config = GenerateConfig(
        temperature=0.7,
        max_tokens=64768,
        format={
            "type": "json_schema",
            "schema": hsds_schema["json_schema"],
            "strict": True
        }
    )

    return Job(
        type="hsds_alignment",
        payload={
            "raw_data": raw_data,
            "known_fields": known_fields,
            "config": config
        }
    )
```

### JSON Schema Format

The structured output uses JSON Schema Draft 7 format with specific constraints for HSDS compliance:

```python
{
    "type": "json_schema",
    "json_schema": {
        "name": "hsds_organization",
        "description": "Structured output schema for HSDS organization data",
        "schema": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": "HSDS Organization Schema",
            "properties": {
                "organization": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/organization"}
                },
                "service": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/service"}
                },
                "location": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/location"}
                }
            },
            "required": ["organization", "service", "location"],
            "additionalProperties": false,
            "definitions": {
                # Organization, service, location definitions
            }
        },
        "strict": true,
        "max_tokens": 64768,
        "temperature": 0.4
    }
}
```

Key features:
- **Strict mode**: Ensures exact schema compliance
- **Required fields**: Enforces HSDS mandatory fields
- **Type constraints**: Validates data types (string, number, array)
- **Enum values**: Restricts fields to allowed values (e.g., status: ["active", "inactive"])
- **Format validation**: Checks patterns for emails, URIs, dates
- **Relationship validation**: Ensures proper linkage between entities

### Response Validation

Workers validate structured responses against the expected schema:

```python
async def validate_structured_response(
    self,
    response: LLMResponse,
    expected_schema: Dict[str, Any]
) -> ValidationResult:
    """Validate structured LLM response"""
    if response.parsed is None:
        # Parse JSON response
        try:
            parsed_data = json.loads(response.text)
        except json.JSONDecodeError as e:
            return ValidationResult(
                valid=False,
                error=f"Invalid JSON: {str(e)}"
            )
    else:
        parsed_data = response.parsed

    # Validate against schema
    validator = ValidationProvider(self.llm_provider, self.validation_config)
    return await validator.validate(
        raw_data=response.original_input,
        hsds_data=parsed_data,
        known_fields=response.known_fields
    )
```

### Structured Output Types

The worker system supports several structured output types for HSDS data:

```python
# Organization output structure
class OrganizationDict(TypedDict):
    name: Required[str]
    description: Required[str]
    services: Required[List[ServiceDict]]
    phones: Required[List[PhoneDict]]
    organization_identifiers: Required[List[OrganizationIdentifierDict]]
    contacts: Required[List[Any]]
    metadata: Required[List[MetadataDict]]

# Service output structure
class ServiceDict(TypedDict):
    name: Required[str]
    description: Required[str]
    status: Required[str]
    phones: Required[List[PhoneDict]]
    schedules: Required[List[ScheduleDict]]

# Location output structure
class LocationDict(TypedDict):
    name: Required[str]
    location_type: Required[str]
    addresses: Required[List[AddressDict]]
    phones: Required[List[PhoneDict]]
    latitude: Required[float]
    longitude: Required[float]
```

### Provider Support

Different LLM providers have varying levels of structured output support:

```python
class ProviderCapabilities:
    """LLM provider structured output capabilities"""

    # OpenAI/OpenRouter - Full structured output support
    OPENAI = {
        "supports_structured": True,
        "format_type": "json_schema",
        "strict_mode": True,
        "max_schema_size": 100000
    }

    # Ollama - Basic JSON format support
    OLLAMA = {
        "supports_structured": False,  # Uses prompt-based JSON
        "format_type": "json",
        "strict_mode": False,
        "requires_system_prompt": True
    }
```

### Error Handling for Structured Output

Workers handle structured output errors specifically:

```python
async def handle_structured_output_error(
    self,
    job: Job,
    error: Exception
) -> None:
    """Handle structured output processing errors"""
    if isinstance(error, json.JSONDecodeError):
        # Retry with adjusted prompt
        await self.retry_with_feedback(
            job,
            feedback="Response must be valid JSON matching the schema"
        )
    elif isinstance(error, ValidationError):
        # Retry with validation feedback
        await self.retry_with_feedback(
            job,
            feedback=error.validation_feedback
        )
    else:
        # Standard error handling
        await self.handle_job_error(job, error)
```

## Debugging and Troubleshooting

### Common Issues and Solutions

#### 1. Worker Not Processing Jobs

```bash
# Check worker is running
./bouy ps | grep worker

# Check Redis connection
./bouy exec worker redis-cli -h cache ping

# Check queue status
./bouy exec worker rq info

# View worker logs for errors
./bouy logs worker --tail 100
```

#### 2. Claude Authentication Issues

```bash
# Check authentication status
./bouy claude-auth status

# Re-authenticate if needed
./bouy claude-auth setup

# Check worker health
curl http://localhost:8080/health
```

#### 3. Jobs Stuck in Queue

```bash
# Check for failed jobs
./bouy exec worker rq info --failed

# Requeue failed jobs
./bouy exec worker rq requeue --all

# Check worker registration
./bouy exec worker rq info --workers
```

#### 4. Memory Issues

```bash
# Check worker memory usage
./bouy exec worker ps aux | grep rq

# Restart workers to free memory
./bouy down worker && ./bouy up worker

# Scale down if needed
./bouy up --scale worker=1
```

### Testing Workers

```bash
# Run worker tests
./bouy test --pytest tests/test_llm/test_queue/

# Test specific worker functionality
./bouy test --pytest tests/test_llm/test_queue/test_worker.py

# Test job processing
./bouy test --pytest tests/test_llm/test_queue/test_processor.py

# Integration test with Redis
./bouy test --pytest tests/test_llm/test_queue/ -k integration
```

### Manual Testing

```bash
# Submit test job via shell
./bouy shell worker
python -c "
import json
from app.llm.queue.queues import llm_queue
from app.llm.queue.models import LLMJob

job = LLMJob(
    id='test_job_1',
    prompt='Test prompt',
    format='json'
)

rq_job = llm_queue.enqueue_call(
    func='app.llm.queue.processor.process_llm_job',
    args=(job, None)
)
print(f'Enqueued job: {rq_job.id}')
"

# Check job status
./bouy exec worker rq info --jobs
```

## Best Practices

### 1. Job Design
- Keep jobs small and focused
- Include metadata for tracking and debugging
- Use content hashes for deduplication
- Set appropriate TTL values

### 2. Error Handling
- Let RQ handle retries for transient failures
- Use specific exception types for different error scenarios
- Log errors with context for debugging
- Monitor failed job queue regularly

### 3. Performance
- Use connection pooling for Redis
- Scale workers based on queue size
- Monitor memory usage and restart if needed
- Use content store to avoid duplicate processing

### 4. Monitoring
- Use RQ dashboard for real-time monitoring
- Set up alerts for queue size thresholds
- Monitor worker health endpoints
- Track job processing times

### 5. Development
- Test with `./bouy test` before deploying
- Use `./bouy logs` to debug issues
- Keep worker logic simple and testable
- Document custom job processors

## Worker and LLM Integration

### How Workers and LLM Processing Work Together

The worker system and LLM module are tightly integrated to provide efficient, scalable HSDS data alignment:

#### Processing Pipeline

```
1. Scraper generates raw data
   ↓
2. LLM job enqueued to 'llm' queue with content hash
   ↓
3. LLM Worker picks up job:
   - Checks content store for cached result
   - If not cached, processes with LLM provider
   - Stores result in content store
   - Enqueues follow-up jobs
   ↓
4. Reconciler Worker processes HSDS data:
   - Validates structure
   - Geocodes addresses
   - Updates database
   ↓
5. Recorder Worker saves results:
   - Writes JSON to outputs/
   - Maintains audit trail
```

#### Key Integration Points

1. **Content Deduplication**: Workers check content store before LLM processing
2. **Job Chaining**: LLM workers automatically trigger reconciler and recorder jobs
3. **Error Propagation**: Failed LLM jobs prevent downstream processing
4. **Shared Configuration**: Workers and LLM use same Redis connection pool
5. **Health Monitoring**: Unified health checks across all worker types

#### Configuration Coordination

```bash
# Shared Redis configuration
REDIS_URL=redis://cache:6379/0

# LLM-specific worker settings
LLM_PROVIDER=openai
LLM_WORKER_COUNT=2

# Worker scaling
WORKER_COUNT=3  # Total workers in container
```

## References

- Architecture Overview: [docs/architecture.md](architecture.md)
- LLM Integration: [docs/llm.md](llm.md)
- API Documentation: [docs/api.md](api.md)
- Getting Started: [docs/getting-started-locally.md](getting-started-locally.md)
