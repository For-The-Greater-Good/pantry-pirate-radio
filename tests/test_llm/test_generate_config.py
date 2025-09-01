"""Tests for LLM generation configuration."""

import pytest

from app.llm.providers.types import GenerateConfig


@pytest.mark.parametrize(
    "temperature,top_p,top_k,max_tokens",
    [
        (0.7, 0.9, 40, 8192),  # Default values
        (0.0, 1.0, 1, 1),  # Minimum valid values
        (1.0, 0.5, 100, 8192),  # Mixed values
    ],
)
async def test_generate_config_valid(
    temperature: float,
    top_p: float,
    top_k: int,
    max_tokens: int,
) -> None:
    """Test valid generation configurations."""
    config = GenerateConfig(
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        max_tokens=max_tokens,
    )

    assert config.temperature == temperature
    assert config.top_p == top_p
    assert config.top_k == top_k
    assert config.max_tokens == max_tokens
    assert config.stop is None
    assert config.stream is False
    assert config.format is None


async def test_generate_config_defaults() -> None:
    """Test generation configuration default values."""
    import os
    
    config = GenerateConfig()

    assert config.temperature == 0.7
    assert config.top_p == 0.9
    assert config.top_k == 40
    # max_tokens defaults to LLM_MAX_TOKENS env var or 8192
    expected_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
    assert config.max_tokens == expected_max_tokens
    assert config.stop is None
    assert config.stream is False
    assert config.format is None


@pytest.mark.parametrize(
    "stop",
    [
        ["."],
        [".", "\n"],
        ["STOP", "END", "FINISH"],
    ],
)
async def test_generate_config_stop_sequences(stop: list[str]) -> None:
    """Test generation configuration with stop sequences."""
    config = GenerateConfig(stop=stop)
    assert config.stop == stop


async def test_generate_config_format() -> None:
    """Test generation configuration with structured output format."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name", "age"],
    }
    config = GenerateConfig(format=schema)
    assert config.format == schema


async def test_generate_config_invalid_values() -> None:
    """Test generation configuration with invalid values."""
    with pytest.raises(ValueError, match="Temperature must be between 0 and 1"):
        GenerateConfig(temperature=1.5)

    with pytest.raises(ValueError, match="Temperature must be between 0 and 1"):
        GenerateConfig(temperature=-0.1)

    with pytest.raises(ValueError, match="Top-p must be between 0 and 1"):
        GenerateConfig(top_p=1.5)

    with pytest.raises(ValueError, match="Top-p must be between 0 and 1"):
        GenerateConfig(top_p=-0.1)

    with pytest.raises(ValueError, match="Top-k must be positive"):
        GenerateConfig(top_k=0)

    with pytest.raises(ValueError, match="Max tokens must be positive"):
        GenerateConfig(max_tokens=0)

    with pytest.raises(ValueError, match="Stop sequences cannot be empty"):
        GenerateConfig(stop=[""])
