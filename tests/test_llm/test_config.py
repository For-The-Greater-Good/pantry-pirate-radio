"""Tests for LLM provider configurations."""

import pytest

from app.llm.config import LLMConfig


@pytest.mark.parametrize(
    "model_name,temperature,timeout,max_tokens",
    [
        ("mistral-small", 0.7, 30, 64768),  # Default values
        ("mistral", 0.5, 60, 64768),  # Custom values
        ("codellama", 0.9, 120, 8192),  # Large values
    ],
)
async def test_llm_config(
    model_name: str,
    temperature: float,
    timeout: int,
    max_tokens: int,
) -> None:
    """Test LLM configuration with various parameters."""
    config = LLMConfig(
        model_name=model_name,
        temperature=temperature,
        timeout=timeout,
        max_tokens=max_tokens,
    )

    assert config.model_name == model_name
    assert config.temperature == temperature
    assert config.timeout == timeout
    assert config.max_tokens == max_tokens
    assert config.supports_structured is False


async def test_llm_config_defaults() -> None:
    """Test LLM configuration default values."""
    config = LLMConfig()

    assert config.model_name == "mistral-small"
    assert config.temperature == 0.7
    assert config.timeout == 30
    assert config.max_tokens is None
    assert config.system_prompt is None
    assert config.stop_sequences is None
    assert config.retries == 3
    assert config.supports_structured is False


async def test_llm_config_custom_features() -> None:
    """Test LLM configuration with custom feature flags."""
    config = LLMConfig(
        model_name="mistral-small",
        temperature=0.7,
        supports_structured=True,
        system_prompt="Test prompt",
        stop_sequences=["stop1", "stop2"],
    )

    assert config.supports_structured is True
    assert config.system_prompt == "Test prompt"
    assert config.stop_sequences == ["stop1", "stop2"]


async def test_llm_config_invalid_values() -> None:
    """Test LLM configuration with invalid values."""
    with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
        LLMConfig(temperature=-0.1)

    with pytest.raises(ValueError, match="Input should be less than or equal to 1"):
        LLMConfig(temperature=1.5)

    with pytest.raises(ValueError, match="Input should be greater than 0"):
        LLMConfig(timeout=0)

    with pytest.raises(ValueError, match="Input should be greater than 0"):
        LLMConfig(max_tokens=0)

    with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
        LLMConfig(retries=-1)


async def test_llm_config_boundary_values() -> None:
    """Test LLM configuration with boundary values."""
    # Test valid boundary values
    config_min = LLMConfig(temperature=0.0, timeout=1, retries=0)
    assert config_min.temperature == 0.0
    assert config_min.timeout == 1
    assert config_min.retries == 0

    config_max = LLMConfig(temperature=1.0, max_tokens=1)
    assert config_max.temperature == 1.0
    assert config_max.max_tokens == 1


async def test_llm_config_inheritance() -> None:
    """Test LLM configuration inheritance from BaseModelConfig."""
    config = LLMConfig()

    # Test inherited properties
    assert config.context_length == 64768
    assert config.default_temp == 0.7
    assert config.supports_json is True
