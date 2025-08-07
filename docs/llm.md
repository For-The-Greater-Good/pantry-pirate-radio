# LLM Module Documentation

## Overview

The LLM module provides HSDS (Human Services Data Specification) data alignment capabilities through RQ-based asynchronous job processing. It supports multiple LLM providers (OpenAI via OpenRouter, Claude via API or CLI), implements intelligent retry strategies, and integrates with the content deduplication store for cost optimization.

```plaintext
┌─────────────┐    ┌─────────────┐
│  Scraper 1  │    │  Scraper 2  │
└─────┬───────┘    └─────┬───────┘
      │                  │
      ▼                  ▼
┌──────────────────────────────┐
│      HSDS Alignment          │
│ ┌────────────────────────┐   │
│ │    Provider System     │   │
│ │     (OpenAI)           │   │
│ └────────────────────────┘   │
│ ┌────────────────────────┐   │
│ │    Validation Loop     │   │
│ └────────────────────────┘   │
└──────────────┬───────────────┘
               │
               ▼
┌─────────────────────────────┐
│       Redis Queue           │
├─────────────────────────────┤
│ - Job Management            │
│ - Status Tracking           │
│ - Result Storage            │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│      Results & Stats        │
└─────────────────────────────┘
```

## Core Components

### 1. HSDS Alignment Core (hsds_aligner/)

The alignment system converts raw data into HSDS-compliant format through a sophisticated process that ensures data quality and schema compliance.

#### Schema Conversion System

The SchemaConverter handles conversion of HSDS schemas into structured formats suitable for LLM processing:

```python
from app.llm.hsds_aligner.schema_converter import SchemaConverter
from pathlib import Path

# Initialize converter with schema path
converter = SchemaConverter(Path("docs/HSDS/schema/schema.csv"))

# Convert schema for structured output
schema = converter.convert_to_llm_schema("organization")
```

Key Features:
1. Format Handlers:
```python
FORMAT_HANDLERS = {
    # URI and Email
    "uri": {"type": "string", "format": "uri"},
    "email": {"type": "string", "format": "email"},
    # Date and Time
    "%Y": {"type": "string", "pattern": r"^\d{4}$"},
    "HH:MM": {
        "type": "string",
        "pattern": r"^([01]\d|2[0-3]):([0-5]\d)(Z|[+-]\d{2}:00)$",
    },
    # Standards
    "ISO639": {"type": "string", "pattern": r"^[a-z]{2,3}$"},
    "ISO3361": {"type": "string", "pattern": r"^[A-Z]{2}$"},
    "currency_code": {"type": "string", "pattern": r"^[A-Z]{3}$"},
}
```

2. Type Constraints:
```python
TYPE_CONSTRAINTS = {
    # Geographic coordinates
    "latitude": {"type": "number", "minimum": -90, "maximum": 90},
    "longitude": {"type": "number", "minimum": -180, "maximum": 180},
    # Schedule constraints
    "timezone": {"type": "number", "minimum": -12, "maximum": 14},
    "bymonthday": {"type": "number", "minimum": -31, "maximum": 31},
    "byyearday": {"type": "number", "minimum": -366, "maximum": 366},
    "interval": {"type": "number", "minimum": 1},
    # Age constraints
    "minimum_age": {"type": "number", "minimum": 0},
    "maximum_age": {"type": "number", "minimum": 0},
    # Financial
    "amount": {"type": "number", "minimum": 0},
    # Extensions
    "phone.extension": {"type": "number", "minimum": 0},
}
```

3. Enum Management:
```python
KNOWN_ENUMS = {
    # Service enums
    "service.status": ["active", "inactive", "defunct", "temporarily closed"],
    # Location enums
    "location.location_type": ["physical", "postal", "virtual"],
    "address.address_type": ["physical", "postal", "virtual"],
    # Schedule enums
    "schedule.freq": ["WEEKLY", "MONTHLY"],
    "schedule.wkst": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"],
    # Phone enums
    "phone.type": ["text", "voice", "fax", "cell", "video", "pager", "textphone"],
}
```

#### Field Validation System

The FieldValidator implements a sophisticated validation system with weighted confidence scoring:

```python
from app.llm.hsds_aligner.field_validator import FieldValidator

validator = FieldValidator()

# Validation deductions
DEDUCTIONS = {
    "top_level": 0.15,      # Missing top-level field
    "organization": 0.10,    # Missing organization field
    "service": 0.10,        # Missing service field
    "location": 0.10,       # Missing location field
    "other": 0.05,          # Missing other field
    # Higher deductions for known fields
    "known_top_level": 0.25,    # Missing known top-level field
    "known_organization": 0.20,  # Missing known organization field
    "known_service": 0.20,      # Missing known service field
    "known_location": 0.20,     # Missing known location field
    "known_other": 0.15,        # Missing known other field
}

# Required fields by entity
REQUIRED_FIELDS = {
    "top_level": ["organization", "service", "location"],
    "organization": [
        "name", "description", "services", "phones",
        "organization_identifiers", "contacts", "metadata"
    ],
    "service": [
        "name", "description", "status", "phones", "schedules"
    ],
    "location": [
        "name", "location_type", "addresses", "phones",
        "accessibility", "contacts", "schedules", "languages",
        "metadata"
    ],
    "phone": [
        "number", "type", "languages"
    ]
}
```

Validation Process:
1. Field Validation:
```python
# Validate required fields
missing_fields = validator.validate_required_fields(hsds_data, known_fields)

# Calculate confidence score
confidence = validator.calculate_confidence(missing_fields, known_fields)

# Generate feedback
feedback = validator.generate_feedback(missing_fields)
```

2. Validation Configuration:
```python
from app.llm.hsds_aligner.validation import ValidationConfig

config = ValidationConfig(
    min_confidence=0.85,    # Minimum confidence for acceptance
    retry_threshold=0.5,    # Minimum confidence for retry
    max_retries=5,         # Maximum retry attempts
    validation_model=None   # Optional different model for validation
)
```

3. Validation Provider:
```python
from app.llm.hsds_aligner.validator import ValidationProvider

validator = ValidationProvider(
    provider=llm_provider,
    config=validation_config
)

# Validate with retry logic
validation_result = await validator.validate(
    input_data=raw_data,
    hsds_output=hsds_data,
    known_fields=known_fields
)
```

#### Type System

Comprehensive TypedDict definitions for HSDS structures:

1. Core Types:
```python
class AddressDict(TypedDict):
    """Physical or mailing address information."""
    address_1: Required[str]
    city: Required[str]
    state_province: Required[str]
    postal_code: Required[str]
    country: Required[str]
    address_type: Required[str]
    address_2: NotRequired[str | None]
    region: NotRequired[str | None]
    attention: NotRequired[str | None]

class ServiceDict(TypedDict):
    """Service information."""
    name: Required[str]
    description: Required[str]
    status: Required[str]
    phones: Required[list[PhoneDict]]
    schedules: Required[list[ScheduleDict]]
    alternate_name: NotRequired[str | None]
    organization_id: NotRequired[str | None]
    url: NotRequired[str | None]
    email: NotRequired[str | None]
    application_process: NotRequired[str | None]
    fees_description: NotRequired[str | None]

class OrganizationDict(TypedDict):
    """Organization information."""
    name: Required[str]
    description: Required[str]
    services: Required[list[ServiceDict]]
    phones: Required[list[PhoneDict]]
    organization_identifiers: Required[list[OrganizationIdentifierDict]]
    contacts: Required[list[Any]]
    metadata: Required[list[MetadataDict]]
```

2. Validation Types:
```python
class ValidationResultDict(TypedDict):
    """Result of LLM-based HSDS validation."""
    confidence: Required[float]
    hallucination_detected: Required[bool]
    missing_required_fields: Required[list[str]]
    feedback: NotRequired[str | None]
    mismatched_fields: NotRequired[list[str] | None]
    suggested_corrections: NotRequired[dict[str, str] | None]

class KnownFieldsDict(TypedDict):
    """Known fields that must be present in output."""
    organization_fields: NotRequired[list[str]]
    service_fields: NotRequired[list[str]]
    location_fields: NotRequired[list[str]]
    phone_fields: NotRequired[list[str]]
    address_fields: NotRequired[list[str]]
    schedule_fields: NotRequired[list[str]]
```

#### Example Usage

Complete alignment process with validation:

```python
from app.llm.hsds_aligner import HSDSAligner
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.hsds_aligner.validation import ValidationConfig

# Configure OpenAI provider
provider = OpenAIProvider(
    OpenAIConfig(
        model_name="openai/gpt-4o",
        temperature=0.3,
        supports_structured=True
    ),
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    headers={
        "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
        "X-Title": "Pantry Pirate Radio",
    }
)

# Configure validation
validation_config = ValidationConfig(
    min_confidence=0.90,
    retry_threshold=0.75,
    max_retries=5
)

# Create aligner with validation
aligner = HSDSAligner(
    provider=provider,
    schema_path=Path("docs/HSDS/schema/schema.csv"),
    validation_config=validation_config
)

# Known fields from input
known_fields = {
    "organization_fields": ["name", "description"],
    "service_fields": ["name", "status"],
    "location_fields": ["address", "phone"],
}

# Align data with validation
result = await aligner.align(raw_data, known_fields)

# Check validation results
if result["confidence_score"] >= validation_config.min_confidence:
    hsds_data = result["hsds_data"]
    validation_details = result.get("validation_details")

    if validation_details:
        print(f"Hallucination detected: {validation_details['hallucination_detected']}")
        print(f"Mismatched fields: {validation_details['mismatched_fields']}")
        if validation_details['suggested_corrections']:
            print("Suggested corrections:")
            for field, correction in validation_details['suggested_corrections'].items():
                print(f"  {field}: {correction}")
```

#### Required Fields and Relationships

The aligner enforces specific field requirements and relationships:

```python
# Required Fields by Entity
REQUIRED_FIELDS = {
    "top_level": ["organization", "service", "location"],
    "organization": ["name", "description", "services"],
    "service": ["name", "description"],
    "location": ["name", "addresses"],
}

# Field Relationships
FIELD_RELATIONSHIPS = {
    "services": {
        "parent": "organization",
        "target": "service",
        "description": "Lists all services provided by this organization. Required to show what services this organization offers.",
    },
    "location": {
        "parent": "top_level",
        "target": None,
        "description": "Contains physical locations where services are provided. Required for geographic search and accessibility.",
    },
    "addresses": {
        "parent": "location",
        "target": None,
        "description": "Physical address information for this location. Required for mapping and directions.",
    },
}
```

#### Field Descriptions

Standard field descriptions used for validation:

```python
FIELD_DESCRIPTIONS = {
    "organization": "A list containing at least one organization object",
    "service": "A list containing at least one service object",
    "location": "A list containing at least one location object",
    "services": "A list of service objects associated with this organization",
    "name": "The name of this entity",
    "description": "A description of this entity",
    "addresses": "The physical or mailing address information",
}
```

#### Alignment Process
1. Input Preprocessing
   - Normalize text formatting
   - Strip irrelevant content
   - Handle special characters
   - Split into logical sections

2. LLM-based Field Mapping
   - Schema-guided field extraction
   - Taxonomy classification
   - Required field validation
   - Relationship mapping

3. Validation Feedback Loop
   - Field coherence checking
   - Required field validation
   - Relationship validation
   - Value format verification

4. Schema Compliance Check
   - HSDS schema validation
   - Field type verification
   - Constraint checking
   - Relationship integrity

5. Confidence Scoring
   - Per-field confidence
   - Overall alignment score
   - Coverage metrics
   - Quality indicators

### 2. Provider System (providers/)

The LLM module supports multiple provider implementations with a unified interface for different AI services.

#### Supported Providers

##### OpenAI/OpenRouter Provider (`providers/openai.py`)
- **API-based**: Uses HTTP requests to OpenAI-compatible endpoints
- **Models**: GPT-4o, GPT-4o-mini, GPT-4 Turbo, Claude via OpenRouter
- **Authentication**: API key via `OPENROUTER_API_KEY` environment variable
- **Features**: Structured output (JSON Schema), streaming, high token limits (64k+)
- **Rate Limiting**: Built-in retry logic with exponential backoff

```python
from app.llm.providers.openai import OpenAIProvider, OpenAIConfig

# Configure OpenAI provider
config = OpenAIConfig(
    model_name="openai/gpt-4o",
    temperature=0.3,
    max_tokens=4000,
    supports_structured=True
)

provider = OpenAIProvider(
    config=config,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    headers={
        "HTTP-Referer": "https://github.com/your-org/project",
        "X-Title": "Your App Name"
    }
)
```

##### Claude Provider (`providers/claude.py`)
- **CLI-based**: Uses Claude Code SDK via subprocess calls
- **Models**: claude-sonnet-4-20250514, claude-haiku, claude-opus
- **Authentication**:
  - **Option 1**: API key via `ANTHROPIC_API_KEY` environment variable
  - **Option 2**: CLI authentication (recommended for Claude Max accounts)
- **Features**: Native structured output, high-quality responses, intelligent quota management
- **Special Handling**: Automatic retry on quota exceeded, authentication state management

```python
from app.llm.providers.claude import ClaudeProvider, ClaudeConfig

# Configure Claude provider
config = ClaudeConfig(
    model_name="claude-sonnet-4-20250514",
    temperature=0.3,
    max_tokens=4000,
    supports_structured=True
)

provider = ClaudeProvider(config=config)
```

#### Claude Authentication Setup

The Claude provider supports two authentication methods:

##### Method 1: API Key Authentication
Set during setup or in `.env` file:
```bash
# During setup
./bouy setup  # Choose Claude provider, then API key option

# Or manually in .env
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your-api-key-here
```

##### Method 2: CLI Authentication (Recommended for Claude Max)
For Claude Max accounts with better quotas:

```bash
# Initial setup
./bouy setup  # Choose Claude provider, then CLI option

# Authenticate Claude (one-time)
./bouy claude-auth setup

# Check authentication status
./bouy claude-auth status

# Test Claude connection
./bouy claude-auth test

# View configuration
./bouy claude-auth config
```

**Bouy Commands for Claude:**
```bash
# Interactive authentication
./bouy claude-auth           # Interactive mode

# Specific commands
./bouy claude-auth setup     # Setup authentication
./bouy claude-auth status    # Check status
./bouy claude-auth test      # Test with sample request
./bouy claude-auth config    # Show config files
```

**Worker Scaling with Shared Authentication:**
```bash
# Scale workers (authentication shared via Docker volumes)
./bouy up --scale worker=3

# Or set in environment
WORKER_COUNT=3 ./bouy up worker

# Check worker health (ports 8080-8089)
curl http://localhost:8080/health
curl http://localhost:8081/health
```

#### Claude Quota Management

The Claude provider includes intelligent quota management:

##### Quota Exceeded Handling
- **Exponential Backoff**: Automatic retry with increasing delays
- **Base Delay**: 1 hour (configurable via `CLAUDE_QUOTA_RETRY_DELAY`)
- **Max Delay**: 4 hours (configurable via `CLAUDE_QUOTA_MAX_DELAY`)
- **Backoff Multiplier**: 1.5x (configurable via `CLAUDE_QUOTA_BACKOFF_MULTIPLIER`)

##### Authentication Failure Handling
- **Fixed Interval**: 5-minute retry intervals
- **Max Attempts**: 12 attempts (1 hour total)
- **Clear Instructions**: Logs show exact commands to run

##### Configuration
```bash
# Environment variables for quota management
CLAUDE_QUOTA_RETRY_DELAY=3600        # Base delay: 1 hour
CLAUDE_QUOTA_MAX_DELAY=14400         # Max delay: 4 hours
CLAUDE_QUOTA_BACKOFF_MULTIPLIER=1.5  # Exponential multiplier
```

#### Provider Selection and Configuration

##### Environment Variables
```bash
# Provider selection
LLM_PROVIDER=openai              # or 'claude'
LLM_MODEL_NAME=gpt-4o-mini      # Model to use
LLM_TEMPERATURE=0.7              # Temperature (0-1)
LLM_MAX_TOKENS=4000              # Max tokens to generate
LLM_TIMEOUT=30                   # Request timeout in seconds
LLM_RETRIES=3                    # Number of retries

# OpenAI/OpenRouter specific
OPENROUTER_API_KEY=your-key     # Required for OpenAI provider

# Claude specific
ANTHROPIC_API_KEY=your-key       # Option 1: API key
# Or use CLI authentication (no API key needed)
```

##### Provider Selection During Setup
```bash
./bouy setup
# Interactive prompts will guide you through:
# 1. Choose LLM provider (OpenAI or Claude)
# 2. Configure authentication method
# 3. Set model preferences
```

#### Health Monitoring and Debugging

##### Health Check Endpoints
```bash
# Check worker health (Claude workers only)
curl http://localhost:8080/health

# Response format:
{
  "provider": "claude",
  "status": "healthy",
  "authenticated": true,
  "model": "claude-sonnet-4-20250514",
  "message": "Ready to process requests"
}
```

##### Monitoring with Bouy
```bash
# View LLM worker logs
./bouy logs worker

# Follow logs in real-time
./bouy logs worker -f

# Check queue status
./bouy exec worker rq info

# View failed LLM jobs
./bouy exec worker rq info --failed
```

##### RQ Dashboard
```bash
# Access RQ dashboard for detailed monitoring
# http://localhost:9181

# Shows:
# - LLM queue size and processing rate
# - Worker status and current jobs
# - Failed jobs with error details
# - Job history and results
```

#### Error Handling

The provider system includes comprehensive error handling:

##### Claude-Specific Exceptions
```python
from app.llm.providers.claude import (
    ClaudeNotAuthenticatedException,
    ClaudeQuotaExceededException
)

try:
    result = await provider.generate(prompt="Test", format="json")
except ClaudeNotAuthenticatedException:
    # Authentication required - job will retry automatically
    logger.warning("Claude authentication required")
except ClaudeQuotaExceededException:
    # Quota exceeded - job will retry with backoff
    logger.warning("Claude quota exceeded, scheduling retry")
```

##### Automatic Job Retry
- **Authentication Errors**: Retry every 5 minutes for up to 1 hour
- **Quota Errors**: Exponential backoff retry (1h → 1.5h → 2.25h → up to 4h)
- **Job Preservation**: Jobs are never lost, only delayed until conditions improve

#### Provider Interface

All providers implement the `BaseLLMProvider` interface:

```python
from app.llm.providers.base import BaseLLMProvider

class CustomProvider(BaseLLMProvider[ConfigType, ResponseType]):
    async def generate(
        self,
        prompt: str,
        format: str | None = None,
        config: ConfigType | None = None
    ) -> ResponseType:
        """Generate response from LLM."""
        pass

    async def health_check(self) -> Dict[str, Any]:
        """Check provider health and authentication."""
        pass

    @property
    def model_name(self) -> str:
        """Get current model name."""
        pass
```

## Prompt Engineering

### System Prompts

The LLM module uses carefully crafted prompts for HSDS alignment:

```python
# Located in app/llm/hsds_aligner/prompts/

# food_pantry_mapper.prompt - Main alignment prompt
# - Instructs LLM to map pantry data to HSDS format
# - Provides field descriptions and requirements
# - Includes examples of correct mappings

# validation_prompt.prompt - Validation prompt
# - Checks for hallucinations and missing fields
# - Validates data coherence
# - Suggests corrections
```

### Prompt Structure

1. **Context Setting**: Explains HSDS and the task
2. **Schema Definition**: Provides field requirements
3. **Known Fields**: Lists fields that must be preserved
4. **Examples**: Shows correct transformations
5. **Constraints**: Specifies validation rules

### Optimization Techniques

- **Temperature Control**: Lower temperature (0.3-0.4) for consistency
- **Structured Output**: Use JSON Schema for guaranteed format
- **Validation Loop**: Re-prompt with feedback for corrections
- **Field Hints**: Provide known fields to reduce hallucination

## Rate Limiting and Cost Optimization

### Content Deduplication Store

```bash
# Check content store status
./bouy content-store status

# View deduplication statistics
./bouy content-store report

# Find duplicate processing
./bouy content-store duplicates
```

### Cost Optimization Strategies

1. **Content Hashing**: Avoid reprocessing identical content
2. **Result Caching**: Store and reuse LLM responses
3. **Batch Processing**: Group similar requests
4. **Model Selection**: Use appropriate model for task complexity
5. **Token Management**: Optimize prompt length

### Rate Limiting

```python
# OpenAI/OpenRouter rate limiting
# Automatic retry with exponential backoff
# Headers: X-RateLimit-Remaining, X-RateLimit-Reset

# Claude quota management
CLAUDE_QUOTA_RETRY_DELAY=3600        # 1 hour base delay
CLAUDE_QUOTA_MAX_DELAY=14400         # 4 hour max delay
CLAUDE_QUOTA_BACKOFF_MULTIPLIER=1.5  # Exponential factor
```

## LLM Usage in Reconciler

### Integration Flow

```
Scraper Data → LLM Alignment → Reconciler → Database
      ↓              ↓              ↓           ↓
  Raw JSON    HSDS Format    Validation   PostgreSQL
```

### Reconciler Processing

```python
# app/reconciler/job_processor.py

def process_job_result(job_result: JobResult):
    """Process LLM-aligned HSDS data."""
    
    # 1. Extract HSDS data from LLM response
    hsds_data = job_result.result.parsed or json.loads(job_result.result.text)
    
    # 2. Validate HSDS compliance
    validator = HSDSValidator()
    if not validator.validate(hsds_data):
        raise ValidationError("Invalid HSDS format")
    
    # 3. Geocode addresses
    geocoder = GeocodeCorrector()
    hsds_data = geocoder.correct_coordinates(hsds_data)
    
    # 4. Create/update database records
    reconciler = Reconciler()
    reconciler.reconcile(hsds_data)
    
    # 5. Track data lineage
    version_tracker = VersionTracker()
    version_tracker.track_changes(hsds_data)
```

### Example: Complete Pipeline

```bash
# 1. Run scraper (generates raw data)
./bouy scraper food_bank_scraper

# 2. LLM processes automatically via worker
# Check processing status
./bouy exec worker rq info

# 3. View results in database
./bouy shell app
python -c "
from app.database.repositories import OrganizationRepository
repo = OrganizationRepository()
orgs = repo.get_all()
for org in orgs:
    print(f'{org.name}: {org.description[:50]}...')
"

# 4. Check reconciler logs
./bouy logs reconciler --tail 50
```

## Debugging LLM Processing

### Common Issues

#### 1. LLM Not Processing Jobs
```bash
# Check worker is running
./bouy ps | grep worker

# Check LLM queue
./bouy exec worker rq info | grep llm

# View worker logs
./bouy logs worker --tail 100
```

#### 2. Authentication Failures
```bash
# For Claude
./bouy claude-auth status
./bouy claude-auth setup  # Re-authenticate

# For OpenAI
# Check API key in .env
grep OPENROUTER_API_KEY .env
```

#### 3. Structured Output Errors
```bash
# Check job details in RQ dashboard
# http://localhost:9181

# Or via CLI
./bouy exec worker rq info --failed

# Requeue failed job
./bouy exec worker rq requeue JOB_ID
```

#### 4. Rate Limiting / Quota Issues
```bash
# Check logs for quota messages
./bouy logs worker | grep -i quota

# Jobs will automatically retry with backoff
# Monitor retry status in RQ dashboard
```

## Best Practices

### 1. Provider Selection
- **Development**: Use Claude CLI for better quotas
- **Production**: Use API keys for predictability
- **Testing**: Use mock provider to avoid costs
- **Fallback**: Configure secondary provider

### 2. Job Configuration
- Include content hashes for deduplication
- Set appropriate token limits
- Use structured output for consistency
- Include known fields to reduce hallucination

### 3. Error Handling
- Let workers handle retries automatically
- Monitor failed job queue regularly
- Use validation loops for quality
- Log with sufficient context

### 4. Performance
- Use content store for caching
- Batch similar requests when possible
- Scale workers based on queue size
- Monitor token usage and costs

### 5. Development Workflow
```bash
# 1. Test LLM alignment locally
./bouy shell worker
python -m app.llm.hsds_aligner

# 2. Run tests
./bouy test --pytest tests/test_llm/

# 3. Monitor processing
./bouy logs worker -f

# 4. Check results
./bouy exec app python -m app.reconciler
```
