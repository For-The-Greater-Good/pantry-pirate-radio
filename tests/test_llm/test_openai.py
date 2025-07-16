"""Unit tests for OpenAI provider."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from pydantic import BaseModel

from app.llm.providers.openai import OpenAIConfig, OpenAIProvider


class TestModel(BaseModel):
    """Test model for structured output."""

    message: str
    count: int


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    """Create OpenAI provider with test config."""
    return OpenAIProvider(
        OpenAIConfig(model_name="google/gemini-2.0-flash-001"),
        api_key="test-api-key-123",
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.beta = MagicMock()
    mock_client.beta.chat = MagicMock()
    mock_client.beta.chat.completions = MagicMock()
    return mock_client


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
        api_key="test-api-key-123",
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )
    assert provider.model_name == "google/gemini-2.0-flash-001"
    assert provider._api_key == "test-api-key-123"
    assert provider.base_url == "https://openrouter.ai/api/v1"
    # Headers should include the user-provided headers
    assert (
        provider.headers["HTTP-Referer"]
        == "https://github.com/openrouter-ai/openrouter-python"
    )
    assert provider.headers["X-Title"] == "Pantry Pirate Radio"


@pytest.mark.asyncio
async def test_openai_generate_text(
    openai_provider: OpenAIProvider, mock_openai_client
) -> None:
    """Test text generation with mocked API."""
    # Mock the response with proper structure
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Hello, friend!"))]
    mock_response.model_dump.return_value = {
        "choices": [{"message": {"content": "Hello, friend!"}}]
    }
    mock_response.error = None  # No error
    mock_response.usage = MagicMock(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Patch the model property
    with patch.object(OpenAIProvider, "model", new_callable=PropertyMock) as mock_model:
        mock_model.return_value = mock_openai_client

        response = await openai_provider.generate("Say hello in a friendly way.")

    assert response.text == "Hello, friend!"
    assert isinstance(response.text, str)
    assert len(response.text) > 0


@pytest.mark.asyncio
async def test_openai_generate_structured(
    openai_provider: OpenAIProvider, mock_openai_client
) -> None:
    """Test structured output generation with mocked API."""
    # Mock the response with JSON content
    json_content = '{"message": "Hello", "count": 42}'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=json_content))]
    mock_response.model_dump.return_value = {
        "choices": [{"message": {"content": json_content}}]
    }
    mock_response.error = None
    mock_response.usage = MagicMock(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Patch the model property
    with patch.object(OpenAIProvider, "model", new_callable=PropertyMock) as mock_model:
        mock_model.return_value = mock_openai_client

        response = await openai_provider.generate(
            "Return a message saying 'Hello' and count of 42",
            format=TestModel.model_json_schema(),
        )

    assert response.parsed is not None
    assert response.parsed["message"] == "Hello"
    assert response.parsed["count"] == 42


@pytest.mark.asyncio
async def test_openai_generate_structured_from_config(
    openai_provider: OpenAIProvider, mock_openai_client
) -> None:
    """Test structured output generation with format in config (bug fix scenario)."""
    from app.llm.providers.types import GenerateConfig

    # Mock the response with JSON content
    json_content = '{"message": "Hello Config", "count": 123}'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=json_content))]
    mock_response.model_dump.return_value = {
        "choices": [{"message": {"content": json_content}}]
    }
    mock_response.error = None
    mock_response.usage = MagicMock(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Patch the model property
    with patch.object(OpenAIProvider, "model", new_callable=PropertyMock) as mock_model:
        mock_model.return_value = mock_openai_client

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
async def test_openai_generate_structured_separate_format(
    openai_provider: OpenAIProvider, mock_openai_client
) -> None:
    """Test structured output generation with separate format parameter (backward compatibility)."""
    # Mock the response with JSON content
    json_content = '{"message": "Hello Separate", "count": 456}'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=json_content))]
    mock_response.model_dump.return_value = {
        "choices": [{"message": {"content": json_content}}]
    }
    mock_response.error = None
    mock_response.usage = MagicMock(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Patch the model property
    with patch.object(OpenAIProvider, "model", new_callable=PropertyMock) as mock_model:
        mock_model.return_value = mock_openai_client

        response = await openai_provider.generate(
            "Return a message saying 'Hello Separate' and count of 456",
            format=TestModel.model_json_schema(),
        )

    assert response.parsed is not None
    assert response.parsed["message"] == "Hello Separate"
    assert response.parsed["count"] == 456


@pytest.mark.asyncio
async def test_openai_generate_invalid_model() -> None:
    """Test handling invalid model - this should fail during validation, not API call."""
    # The invalid model should be caught during initialization/validation
    # before any API call is made
    provider = OpenAIProvider(
        OpenAIConfig(model_name="invalid-model"),
        api_key="test-api-key-123",
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )

    # Mock the model property to prevent actual API calls
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=ValueError("invalid-model is not a valid model ID")
    )

    with patch.object(OpenAIProvider, "model", new_callable=PropertyMock) as mock_model:
        mock_model.return_value = mock_client

        with pytest.raises(ValueError, match="not a valid model ID"):
            await provider.generate("Test")
