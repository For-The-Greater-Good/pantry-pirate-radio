# Worker System

## Overview

The worker system is a critical component of Pantry Pirate Radio's job processing infrastructure, responsible for executing asynchronous tasks, particularly LLM-based HSDS data alignment operations. Built on Redis for reliable job queuing and state management, the worker system ensures robust, scalable processing of resource-intensive operations.

## Architecture

### Components

1. Job Queue
   - Redis-backed priority queue
   - Support for job dependencies
   - Batch processing capabilities
   - Dead letter queue for failed jobs

2. Worker Process
   - Asynchronous job execution
   - Resource management
   - Health monitoring
   - Graceful shutdown handling

3. Job Types
   - LLM Processing
   - HSDS Alignment
   - Data Validation
   - Bulk Operations

## Configuration

```python
class WorkerConfig(BaseModel):
    """Worker configuration settings"""
    redis_url: str = Field(..., description="Redis connection URL")
    worker_count: int = Field(
        default=1,
        ge=1,
        description="Number of worker processes"
    )
    batch_size: int = Field(
        default=10,
        ge=1,
        description="Maximum batch size for processing"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts"
    )
    shutdown_timeout: float = Field(
        default=30.0,
        ge=0,
        description="Graceful shutdown timeout in seconds"
    )
    health_check_interval: int = Field(
        default=60,
        ge=10,
        description="Health check interval in seconds"
    )
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

### Job Lifecycle

1. Submission
   ```python
   async def submit_job(
       self,
       job_type: str,
       payload: Dict[str, Any],
       priority: int = 0
   ) -> str:
       """Submit a new job to the queue"""
       job_id = generate_job_id()
       await self.redis.set(
           f"job:{job_id}:status",
           JobStatus.PENDING.value
       )
       return job_id
   ```

2. Processing
   ```python
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

3. Completion/Error
   ```python
   async def handle_job_completion(self, job: Job, result: Any) -> None:
       """Handle successful job completion"""
       # Store result in content store if applicable
       content_store = get_content_store()
       if content_store and "content_hash" in job.metadata:
           content_store.store_result(
               job.metadata["content_hash"],
               result.text,
               job.id
           )

       # Update job status
       await self.update_status(job.id, JobStatus.COMPLETED)

   async def handle_job_error(
       self,
       job: Job,
       error: Exception
   ) -> None:
       """Handle job processing errors"""
       if job.retry_count < self.config.max_retries:
           await self.retry_job(job)
       else:
           await self.move_to_dead_letter(job)
   ```

### Batch Processing

```python
async def process_batch(
    self,
    batch: List[Job]
) -> None:
    """Process a batch of jobs concurrently"""
    tasks = [
        self.process_job(job)
        for job in batch
    ]
    await asyncio.gather(*tasks)
```

## Error Handling

### Retry Strategy

```python
class RetryStrategy(BaseModel):
    """Job retry configuration"""
    max_retries: int
    backoff_factor: float
    jitter: bool = True

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay before next retry"""
        delay = self.backoff_factor * (2 ** attempt)
        if self.jitter:
            delay *= random.uniform(0.5, 1.5)
        return delay
```

### Dead Letter Queue

```python
async def move_to_dead_letter(self, job: Job) -> None:
    """Move failed job to dead letter queue"""
    await self.redis.lpush(
        "dead_letter_queue",
        json.dumps({
            "job_id": job.id,
            "error": str(job.last_error),
            "timestamp": datetime.utcnow().isoformat()
        })
    )
```

## Monitoring

### Health Checks

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

### Metrics

```python
# Prometheus metrics
JOBS_PROCESSED = Counter(
    'worker_jobs_processed_total',
    'Total number of jobs processed',
    ['status']
)

JOB_PROCESSING_TIME = Histogram(
    'worker_job_processing_seconds',
    'Time spent processing jobs',
    ['job_type']
)

QUEUE_SIZE = Gauge(
    'worker_queue_size',
    'Current size of the job queue'
)
```

## Resource Management

### Memory Management

```python
class MemoryManager:
    """Manage worker memory usage"""

    def __init__(self, max_memory_mb: int = 1024):
        self.max_memory = max_memory_mb * 1024 * 1024

    async def check_memory(self) -> bool:
        """Check if memory usage is within limits"""
        current = self.get_memory_usage()
        return current < self.max_memory

    async def cleanup(self) -> None:
        """Perform memory cleanup if needed"""
        if not await self.check_memory():
            gc.collect()
```

### Graceful Shutdown

```python
async def shutdown(self) -> None:
    """Gracefully shutdown worker"""
    self.running = False

    # Wait for current jobs to complete
    try:
        await asyncio.wait_for(
            self.wait_for_jobs(),
            timeout=self.config.shutdown_timeout
        )
    except asyncio.TimeoutError:
        logger.warning("Shutdown timeout reached")

    # Cleanup resources
    await self.cleanup_resources()
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

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_job_processing():
    """Test basic job processing"""
    worker = Worker(test_config)
    job = create_test_job()

    result = await worker.process_job(job)
    assert result.status == JobStatus.COMPLETED
```

### Structured Output Tests

```python
@pytest.mark.asyncio
async def test_structured_output_processing():
    """Test processing with structured output"""
    worker = Worker(test_config)

    # Create job with structured output format
    job = await worker.prepare_hsds_alignment_job(
        raw_data=test_pantry_data,
        known_fields={"organization_fields": ["name", "website"]}
    )

    result = await worker.process_job(job)

    # Verify structured output
    assert result.status == JobStatus.COMPLETED
    assert "organization" in result.data
    assert "service" in result.data
    assert "location" in result.data

    # Validate against schema
    validation = await worker.validate_structured_response(
        result.response,
        job.payload["config"]["format"]["schema"]
    )
    assert validation.valid

@pytest.mark.asyncio
async def test_structured_output_error_handling():
    """Test error handling for invalid structured output"""
    worker = Worker(test_config)

    # Create job that will produce invalid output
    job = create_test_job_with_invalid_schema()

    result = await worker.process_job(job)

    # Should retry with feedback
    assert result.retry_count > 0
    assert "feedback" in result.metadata
```

### Integration Tests

```python
@pytest.mark.integration
async def test_worker_lifecycle():
    """Test complete worker lifecycle"""
    worker = Worker(test_config)
    await worker.start()

    # Submit test jobs
    job_ids = []
    for i in range(5):
        job_id = await worker.submit_job(
            "test",
            {"data": f"test_{i}"}
        )
        job_ids.append(job_id)

    # Wait for completion
    results = await worker.wait_for_jobs(job_ids)

    # Verify results
    for result in results:
        assert result.status == JobStatus.COMPLETED

    await worker.shutdown()
```

## Implementation Guidelines

1. Error Handling
   - Implement comprehensive error handling
   - Use appropriate retry strategies
   - Maintain error context for debugging
   - Log errors with sufficient detail

2. Resource Management
   - Monitor memory usage
   - Implement graceful shutdown
   - Clean up resources properly
   - Handle connection failures

3. Testing
   - Write comprehensive unit tests
   - Include integration tests
   - Test error scenarios
   - Verify resource cleanup

4. Monitoring
   - Implement health checks
   - Add Prometheus metrics
   - Monitor resource usage
   - Track job statistics

## References

- Architecture Overview: [docs/architecture.md](architecture.md)
- Implementation Plan: [docs/implementation-plan.python.md](implementation-plan.python.md)
- Queue System: [docs/queue.md](queue.md)
- LLM Integration: [docs/llm.md](llm.md)
