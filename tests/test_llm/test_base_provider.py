"""Tests for base LLM provider."""

import pytest
from unittest.mock import MagicMock, patch

from app.llm.providers.base import BaseLLMProvider
from app.llm.base import BaseModelConfig


class MockConfig(BaseModelConfig):
    """Mock configuration for testing."""

    def __init__(self, supports_structured: bool = True, **kwargs):
        # Provide required parameters for BaseModelConfig
        super().__init__(
            context_length=4096,
            max_tokens=1000,
            supports_structured=supports_structured,
            **kwargs
        )


class MockProvider(BaseLLMProvider[None, MockConfig]):
    """Mock provider for testing."""

    def _init_config(self, **kwargs) -> MockConfig:
        return MockConfig(**kwargs)

    @property
    def environment_key(self) -> str:
        return "MOCK_API_KEY"

    @property
    def model(self) -> None:
        return None

    async def generate(self, prompt, config=None, format=None, **kwargs):
        return None


def test_supports_structured_output_true():
    """Test supports_structured_output returns True when config supports it."""
    provider = MockProvider(model_name="test-model", supports_structured=True)
    assert provider.supports_structured_output() is True


def test_supports_structured_output_false():
    """Test supports_structured_output returns False when config doesn't support it."""
    provider = MockProvider(model_name="test-model", supports_structured=False)
    assert provider.supports_structured_output() is False


def test_from_name_classmethod():
    """Test from_name classmethod creates provider with model name."""
    provider = MockProvider.from_name("test-model-name")
    assert provider.model_name == "test-model-name"
    assert isinstance(provider, MockProvider)
