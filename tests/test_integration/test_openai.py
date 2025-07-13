"""Integration tests for OpenAI provider."""

import os
from pathlib import Path
from typing import Any, Dict, cast

import pytest

from app.core.config import settings
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider


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
async def test_openai_generate_text(openai_provider: OpenAIProvider) -> None:
    """Test OpenAI text generation with live API."""
    response = await openai_provider.generate("Say hello in a friendly way.")

    # Just verify we get a non-empty text response
    assert response.text is not None
    assert isinstance(response.text, str)
    assert len(response.text.strip()) > 0, "Response text should not be empty"


@pytest.mark.integration
async def test_openai_generate_json(openai_provider: OpenAIProvider) -> None:
    """Test OpenAI JSON generation with live API."""
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
        "Return a JSON object with name 'John' and age 30.",
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
async def test_openai_generate_hsds(openai_provider: OpenAIProvider) -> None:
    """Test OpenAI HSDS generation with live API."""
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "organization": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "services": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["name", "services"],
                },
            },
            "service": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "organization": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "organization", "description"],
                },
            },
            "location": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "address": {"type": "object"},
                    },
                    "required": ["name", "address"],
                },
            },
        },
        "required": ["organization", "service", "location"],
        "additionalProperties": False,
    }

    response = await openai_provider.generate(
        """Convert this food pantry data to HSDS format:
        Name: "The Pantry" at St. Patrick's
        Organization: St. Patrick
        Description: Can visit once a month unless they are in need. walk in no appt necessary.
        Location: Ravena
        Address: 21 Main St.
        City: Ravena
        State: NY
        Zip: 12143""",
        format=schema,
    )

    assert response.parsed is not None
    parsed = cast(Dict[str, Any], response.parsed)
    assert isinstance(parsed, dict)
    assert "organization" in parsed
    assert "service" in parsed
    assert "location" in parsed
    assert len(parsed["organization"]) > 0
    assert len(parsed["service"]) > 0
    assert len(parsed["location"]) > 0
