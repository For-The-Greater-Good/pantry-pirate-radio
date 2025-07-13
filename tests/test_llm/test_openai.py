"""Unit tests for OpenAI provider."""

import pytest
from pydantic import BaseModel

from app.llm.providers.openai import OpenAIConfig, OpenAIProvider


class TestModel(BaseModel):
    """Test model for structured output."""

    message: str
    count: int


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    """Create OpenAI provider with real config."""
    return OpenAIProvider(
        OpenAIConfig(model_name="google/gemini-2.0-flash-001"),
        api_key="***REMOVED***",
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )


def test_openai_config_defaults() -> None:
    """Test OpenAI config defaults."""
    config = OpenAIConfig(model_name="google/gemini-2.0-flash-001")
    assert config.model_name == "google/gemini-2.0-flash-001"
    assert config.temperature == 0.7
    assert config.max_tokens is None
    assert config.supports_structured is True


def test_openai_provider_init() -> None:
    """Test OpenAI provider initialization."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="google/gemini-2.0-flash-001"),
        api_key="***REMOVED***",
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )
    assert provider.model_name == "google/gemini-2.0-flash-001"
    assert (
        provider.api_key
        == "***REMOVED***"
    )
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.headers == {
        "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
        "X-Title": "Pantry Pirate Radio",
    }


@pytest.mark.asyncio
async def test_openai_generate_text(openai_provider: OpenAIProvider) -> None:
    """Test text generation."""
    response = await openai_provider.generate("Say hello in a friendly way.")

    assert response.text is not None
    assert isinstance(response.text, str)
    assert len(response.text) > 0


@pytest.mark.asyncio
async def test_openai_generate_structured(openai_provider: OpenAIProvider) -> None:
    """Test structured output generation."""
    response = await openai_provider.generate(
        "Return a message saying 'Hello' and count of 42",
        format=TestModel.model_json_schema(),
    )

    assert response.parsed is not None
    assert response.parsed["message"] == "Hello"
    assert response.parsed["count"] == 42


@pytest.mark.asyncio
async def test_openai_generate_structured_from_config(openai_provider: OpenAIProvider) -> None:
    """Test structured output generation with format in config (bug fix scenario)."""
    from app.llm.providers.types import GenerateConfig

    config = GenerateConfig(
        temperature=0.7,
        format=TestModel.model_json_schema(),
    )
    
    response = await openai_provider.generate(
        "Return a message saying 'Hello Config' and count of 123",
        config=config,
    )

    assert response.parsed is not None
    assert response.parsed["message"] == "Hello Config"
    assert response.parsed["count"] == 123


@pytest.mark.asyncio
async def test_openai_generate_structured_separate_format(openai_provider: OpenAIProvider) -> None:
    """Test structured output generation with separate format parameter (backward compatibility)."""
    response = await openai_provider.generate(
        "Return a message saying 'Hello Separate' and count of 456",
        format=TestModel.model_json_schema(),
    )

    assert response.parsed is not None
    assert response.parsed["message"] == "Hello Separate"
    assert response.parsed["count"] == 456


@pytest.mark.asyncio
async def test_openai_generate_invalid_model(openai_provider: OpenAIProvider) -> None:
    """Test handling invalid model."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="invalid-model"),
        api_key="***REMOVED***",
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )
    with pytest.raises(ValueError, match="not a valid model ID"):
        await provider.generate("Test")
