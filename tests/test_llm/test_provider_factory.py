"""Tests for LLM provider factory."""

from unittest.mock import MagicMock

import pytest

from app.llm.config import LLMConfig
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.factory import (
    _PROVIDER_REGISTRY,
    create_provider,
    register_provider,
)
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.claude import ClaudeConfig, ClaudeProvider


class TestCreateProviderOpenAI:
    """Test factory creates OpenAI provider correctly."""

    def test_create_provider_openai(self):
        """Test creating an OpenAI provider via factory."""
        provider = create_provider("openai", "gpt-4o-mini", 0.7, 1000)
        assert isinstance(provider, OpenAIProvider)
        assert provider.config.model_name == "gpt-4o-mini"
        assert provider.config.temperature == 0.7
        assert provider.config.max_tokens == 1000

    def test_create_provider_openai_none_max_tokens(self):
        """Test creating an OpenAI provider with None max_tokens."""
        provider = create_provider("openai", "gpt-4o-mini", 0.7, None)
        assert isinstance(provider, OpenAIProvider)
        assert provider.config.max_tokens is None


class TestCreateProviderClaude:
    """Test factory creates Claude provider correctly."""

    def test_create_provider_claude(self):
        """Test creating a Claude provider via factory."""
        provider = create_provider("claude", "claude-sonnet-4-20250514", 0.5, 2000)
        assert isinstance(provider, ClaudeProvider)
        assert provider.config.model_name == "claude-sonnet-4-20250514"
        assert provider.config.temperature == 0.5
        assert provider.config.max_tokens == 2000


class TestCreateProviderUnsupported:
    """Test factory raises on unsupported provider."""

    def test_create_provider_unsupported(self):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            create_provider("unsupported", "model", 0.7, None)

    def test_error_lists_all_providers(self):
        """Test that error message dynamically lists registered providers."""
        with pytest.raises(ValueError) as exc_info:
            create_provider("bogus", "model", 0.7, None)
        error_msg = str(exc_info.value)
        # All default providers should be listed
        assert "openai" in error_msg
        assert "claude" in error_msg


class TestRegisterCustomProvider:
    """Test registering a custom provider."""

    def test_register_and_create_custom_provider(self):
        """Test registering a custom provider and creating it."""

        class CustomConfig(LLMConfig):
            pass

        class CustomProvider(BaseLLMProvider):
            def __init__(self, config, **kwargs):
                self.config = config
                super().__init__(model_name=config.model_name, **kwargs)

            def _init_config(self, **kwargs):
                return self.config

            @property
            def environment_key(self):
                return "CUSTOM_API_KEY"

            @property
            def model(self):
                return None

            async def generate(self, prompt, config=None, format=None, **kwargs):
                pass

        register_provider("custom_test", CustomConfig, CustomProvider)
        try:
            provider = create_provider("custom_test", "custom-model", 0.7, None)
            assert isinstance(provider, CustomProvider)
            assert provider.config.model_name == "custom-model"
        finally:
            # Clean up registry
            _PROVIDER_REGISTRY.pop("custom_test", None)
