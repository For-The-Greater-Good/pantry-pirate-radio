# LLM Module Documentation

## Overview

The LLM module provides HSDS (Human Services Data Specification) data alignment capabilities through an asynchronous job processing system. It supports multiple LLM providers, handles streaming responses, and includes comprehensive monitoring.

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
- **Models**: GPT-4o, GPT-4 Turbo, Claude via OpenRouter, etc.
- **Authentication**: API key via `OPENROUTER_API_KEY` environment variable
- **Features**: Structured output, streaming, function calling

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
- **Models**: Claude Sonnet 4, Claude Haiku, Claude Opus
- **Authentication**:
  - **Option 1**: API key via `ANTHROPIC_API_KEY` environment variable
  - **Option 2**: CLI authentication (recommended for Claude Max accounts)
- **Features**: Native structured output, high-quality responses, quota management

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
Set the `ANTHROPIC_API_KEY` environment variable:
```bash
export ANTHROPIC_API_KEY=your-api-key-here
```

##### Method 2: CLI Authentication (Recommended)
For Claude Max accounts or interactive authentication:

1. **Container Setup**: Authentication is shared across scaled worker containers via Docker volumes
2. **One-time Setup**: Authenticate once, use across all workers
3. **Intelligent Retry**: Jobs automatically retry when authentication expires

**Quick Setup:**
```bash
# Start containers
docker compose up -d

# Check authentication status
curl http://localhost:8080/health

# If authentication needed
docker compose exec worker python -m app.claude_auth_manager setup

# Verify authentication
curl http://localhost:8080/health
```

**Available Commands:**
```bash
# Interactive setup
docker compose exec worker python -m app.claude_auth_manager setup

# Check status
docker compose exec worker python -m app.claude_auth_manager status

# Test request
docker compose exec worker python -m app.claude_auth_manager test

# View config files
docker compose exec worker python -m app.claude_auth_manager config
```

**Scaling Workers:**
```bash
# Scale to multiple workers (shared authentication)
docker compose up -d --scale worker=3

# All workers share the same Claude authentication
# Health checks available on ports 8080-8089
curl http://localhost:8080/health
curl http://localhost:8081/health
curl http://localhost:8082/health
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

#### Provider Selection

Set the LLM provider via environment variable:

```bash
# Use Claude provider
LLM_PROVIDER=claude

# Use OpenAI provider
LLM_PROVIDER=openai
```

The system automatically selects the appropriate provider based on configuration.

#### Health Monitoring

Each provider implements health check endpoints:

```bash
# Provider health (includes authentication status)
curl http://localhost:8080/health

# Authentication status
curl http://localhost:8080/auth

# Example health response
{
  "provider": "claude",
  "status": "healthy",
  "authenticated": true,
  "model": "claude-sonnet-4-20250514",
  "message": "Ready to process requests"
}
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

#### Best Practices

1. **Claude Max Users**: Use CLI authentication for quota advantages
2. **Production**: Use API keys for predictable billing
3. **Development**: CLI authentication for experimentation
4. **Scaling**: Shared volumes ensure consistent authentication
5. **Monitoring**: Use health endpoints for system status
6. **Resilience**: Let the retry system handle temporary failures

[Previous content continues unchanged...]
