"""Integration tests for OpenAI provider with real API."""

import os
import pytest
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.types import GenerateConfig
from app.core.config import settings


@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"), reason="OpenRouter API key not available"
)
@pytest.mark.asyncio
async def test_openai_structured_output_real_api():
    """Test native structured output with real OpenRouter API."""

    # Use gpt-4o-mini for testing structured outputs
    # (Claude via OpenRouter doesn't support response_format yet)
    provider = OpenAIProvider(
        OpenAIConfig(
            model_name="openai/gpt-4o-mini",
            temperature=0.1,  # Low temperature for consistent results
            max_tokens=200,
        )
    )

    # Create a simple HSDS-like schema
    schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "test_organization",
            "description": "Test organization data",
            "schema": {
                "type": "object",
                "properties": {
                    "organization": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["active", "inactive"],
                            },
                        },
                        "required": ["name", "description", "status"],
                        "additionalProperties": False,
                    }
                },
                "required": ["organization"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }

    config = GenerateConfig(format=schema_format, temperature=0.1)

    # Simple prompt that should generate valid structured output
    prompt = """Extract organization data from this text:
    The Maryland Food Bank is an active nonprofit organization that provides food assistance to families in need across Maryland."""

    response = await provider.generate(prompt, config=config)

    # Verify we got a valid response
    assert response is not None
    assert response.text is not None

    # Should have parsed JSON
    assert response.parsed is not None
    assert "organization" in response.parsed

    org = response.parsed["organization"]
    assert "name" in org
    assert "description" in org
    assert "status" in org

    # Verify the content makes sense
    assert "Maryland" in org["name"] or "Food Bank" in org["name"]
    assert org["status"] == "active"  # We said "active" in the prompt

    print(f"\nReceived structured output: {response.parsed}")


@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"), reason="OpenRouter API key not available"
)
@pytest.mark.asyncio
async def test_openai_without_structured_output():
    """Test that regular generation still works without structured output."""

    # Use gpt-4o-mini for testing structured outputs
    # (Claude via OpenRouter doesn't support response_format yet)
    provider = OpenAIProvider(
        OpenAIConfig(model_name="openai/gpt-4o-mini", temperature=0.7, max_tokens=50)
    )

    prompt = "Say hello in exactly 3 words"

    response = await provider.generate(prompt)

    # Should get a text response
    assert response is not None
    assert response.text is not None
    assert len(response.text) > 0

    # Should NOT have parsed data when no format specified
    assert response.parsed is None

    print(f"\nReceived text response: {response.text}")


@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"), reason="OpenRouter API key not available"
)
@pytest.mark.asyncio
async def test_shortened_prompt_with_structured_output():
    """Test that our shortened prompts work with real API."""

    # Use gpt-4o-mini for testing structured outputs
    # (Claude via OpenRouter doesn't support response_format yet)
    provider = OpenAIProvider(
        OpenAIConfig(model_name="openai/gpt-4o-mini", temperature=0.3, max_tokens=500)
    )

    # Load our shortened prompt
    from pathlib import Path

    prompt_path = Path("/app/app/llm/hsds_aligner/prompts/food_pantry_mapper.prompt")
    shortened_prompt = prompt_path.read_text()

    # Create a realistic HSDS schema
    schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "hsds_data",
            "description": "HSDS compliant data",
            "schema": {
                "type": "object",
                "properties": {
                    "organization": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["name", "description"],
                            "additionalProperties": False,
                        },
                    },
                    "service": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "status": {"type": "string"},
                            },
                            "required": ["name", "description", "status"],
                            "additionalProperties": False,
                        },
                    },
                    "location": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "location_type": {"type": "string"},
                            },
                            "required": ["name", "location_type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["organization", "service", "location"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }

    config = GenerateConfig(format=schema_format, temperature=0.3)

    # Combine shortened prompt with test data
    full_prompt = f"""{shortened_prompt}

Input Data:
St. Mary's Food Bank
Address: 123 Main Street, Baltimore, MD 21201
Phone: (410) 555-1234
Services: Food distribution every Monday and Wednesday from 9am-12pm
Status: Currently operational and accepting clients"""

    response = await provider.generate(full_prompt, config=config)

    # Verify structured output was generated
    assert response is not None
    assert response.parsed is not None

    # Check basic HSDS structure
    assert "organization" in response.parsed
    assert "service" in response.parsed
    assert "location" in response.parsed

    # Verify arrays
    assert isinstance(response.parsed["organization"], list)
    assert isinstance(response.parsed["service"], list)
    assert isinstance(response.parsed["location"], list)

    # Check that data was extracted
    assert len(response.parsed["organization"]) > 0
    assert len(response.parsed["service"]) > 0
    assert len(response.parsed["location"]) > 0

    # Verify content
    org = response.parsed["organization"][0]
    assert "Mary" in org["name"] or "Food Bank" in org["name"]

    print("\nShortened prompt generated valid HSDS data!")
    print(f"Organizations: {len(response.parsed['organization'])}")
    print(f"Services: {len(response.parsed['service'])}")
    print(f"Locations: {len(response.parsed['location'])}")
