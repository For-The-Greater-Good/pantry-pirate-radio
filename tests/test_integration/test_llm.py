"""Test LLM integration."""

import os
from pathlib import Path
from typing import Any, Dict, List, TypedDict, cast

import pytest

from app.llm.hsds_aligner.type_defs import (
    AlignmentInputDict,
)
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.types import GenerateConfig

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class JsonSchema(TypedDict):
    """Type for JSON schema format."""

    type: str
    schema: Dict[str, Any]
    name: str
    description: str
    strict: bool


class InputData(TypedDict):
    """Type for input data."""

    Name: str
    Entity_Id: int
    Category: str
    Subcategory: str
    Organization: str
    More_Information: str
    Counties: List[str]
    Location: str
    Address: str
    City: str
    State: str
    Zip: str
    Phone: str
    Hours_of_Operation: str
    Cost: str
    Accepts: str
    Website: str
    Coalition: int
    CFAN: int
    Latitude: str
    Longitude: str
    Last_Updated: str
    icon: str


def _read_env_file() -> str | None:
    """Read API key directly from .env file to bypass environment variable precedence."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    if key and key not in ("your_api_key_here", "", "sk-"):
                        return key
    return None


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    """Create OpenAI provider with API key from .env file or environment."""
    # First try reading directly from .env file to bypass container env vars
    api_key = _read_env_file()

    # Fall back to environment variable
    if not api_key:
        api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key or api_key in ("your_api_key_here", "", "sk-"):
        pytest.skip(
            "Valid OPENROUTER_API_KEY not available in .env file or environment"
        )

    return OpenAIProvider(
        OpenAIConfig(model_name="google/gemini-2.0-flash-001"),
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )


@pytest.mark.integration
async def test_openai_structured_output(openai_provider: OpenAIProvider) -> None:
    """Test OpenAI structured output with live API."""
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name", "age"],
        "additionalProperties": False,
    }

    response = await openai_provider.generate(
        "Return a JSON object with name 'John' and age 30. Your response must be a complete, properly formatted JSON object with commas between properties.",
        format=schema,
    )

    assert response.parsed is not None
    parsed = cast(Dict[str, Any], response.parsed)
    assert isinstance(parsed, dict)
    assert "name" in parsed
    assert "age" in parsed
    assert isinstance(parsed["name"], str)
    assert isinstance(parsed["age"], int)
    assert parsed["name"] == "John"
    assert parsed["age"] == 30


@pytest.mark.integration
async def test_openai_structured_output_with_config(
    openai_provider: OpenAIProvider,
) -> None:
    """Test OpenAI structured output with custom config using live API."""
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["summary", "keywords"],
        "additionalProperties": False,
    }

    response = await openai_provider.generate(
        "Return a JSON object with a summary of 'A quick brown fox jumps over a lazy dog' and keywords ['fox', 'jump', 'dog', 'quick', 'lazy']. Your response must be a complete, properly formatted JSON object with commas between properties and array items.",
        format=schema,
    )

    assert response.parsed is not None
    parsed = cast(Dict[str, Any], response.parsed)
    assert isinstance(parsed, dict)
    assert "summary" in parsed
    assert "keywords" in parsed
    assert isinstance(parsed["summary"], str)
    keywords = cast(List[str], parsed["keywords"])
    assert isinstance(keywords, list)
    assert len(keywords) > 0
    assert all(isinstance(k, str) for k in keywords)


@pytest.mark.integration
async def test_openai_stream(openai_provider: OpenAIProvider) -> None:
    """Test OpenAI streaming with live API."""
    response = await openai_provider.generate(
        "Count from 1 to 5 slowly.",
        config=GenerateConfig(
            temperature=0.7,
            max_tokens=50,
        ),
    )

    assert response is not None
    assert response.text is not None
    assert "1" in response.text
    assert "2" in response.text
    assert "3" in response.text
    assert "4" in response.text
    assert "5" in response.text


@pytest.mark.integration
async def test_openai_hsds_alignment(
    openai_provider: OpenAIProvider, project_root: Path
) -> None:
    """Test HSDS alignment with validation using live OpenAI API."""
    from app.llm.hsds_aligner import HSDSAligner
    from app.llm.hsds_aligner.validation import ValidationConfig

    schema_path = project_root / "docs/HSDS/schema/simple/schema.csv"

    validation_config = ValidationConfig(
        min_confidence=0.90,  # Set 90% confidence threshold
        retry_threshold=0.75,  # Higher retry threshold for better quality
    )

    # Cast provider to correct type for HSDSAligner
    typed_provider = cast(BaseLLMProvider[Any, OpenAIConfig], openai_provider)

    aligner = HSDSAligner[Any, OpenAIConfig](
        provider=typed_provider,
        schema_path=schema_path,
        validation_config=validation_config,
        validation_provider=typed_provider,
    )

    # Test data for alignment
    input_data: InputData = {
        "Name": '"The Pantry" at St. Patrick\'s',
        "Entity_Id": 97,
        "Category": "Food Pantry",
        "Subcategory": "Food Pantries within the Capital District",
        "Organization": "St. Patrick",
        "More_Information": "Can visit once a month unless they are in need. walk in no appt necessary. If a client is in need of food they will open to accommodate them",
        "Counties": ["Albany"],
        "Location": "Ravena",
        "Address": "21 Main St.",
        "City": "Ravena",
        "State": "NY",
        "Zip": "12143",
        "Phone": "(518) 756-3145",
        "Hours_of_Operation": "Tues 10:00-11:00am, Wed 6:00-7:00pm, Fri 10:00-11:00am",
        "Cost": "",
        "Accepts": "",
        "Website": "https://churchofsaintpatrick.wixsite.com/church-ravena",
        "Coalition": 1,
        "CFAN": 0,
        "Latitude": "42.4733363",
        "Longitude": "-73.8023108",
        "Last_Updated": "03-21-2024",
        "icon": "marker-F42000",
    }

    # Create alignment input
    alignment_input: AlignmentInputDict = {
        "raw_data": str(input_data),
        "source_format": "python_dict",
    }

    # Perform alignment with validation
    result = await aligner.align(alignment_input["raw_data"])

    # Verify validation results
    assert (
        result["confidence_score"] >= validation_config.min_confidence
    ), f"Validation confidence ({result['confidence_score']:.2%}) below {validation_config.min_confidence:.2%} threshold"

    # Verify basic HSDS structure
    hsds_data = result["hsds_data"]
    assert len(hsds_data["organization"]) > 0, "No organizations found"
    assert len(hsds_data["service"]) > 0, "No services found"
    assert len(hsds_data["location"]) > 0, "No locations found"

    # Verify organization has services
    org = hsds_data["organization"][0]
    assert len(org["services"]) > 0, "Organization missing services"
