"""Tests for LLM base types."""

import pytest

from app.llm.base import BaseModelConfig


class TestBaseModelConfig:
    """Test BaseModelConfig validation."""

    def test_valid_config(self):
        """Test creating a valid configuration."""
        config = BaseModelConfig(
            context_length=4000,
            max_tokens=1000,
            default_temp=0.7,
        )
        assert config.context_length == 4000
        assert config.max_tokens == 1000
        assert config.default_temp == 0.7

    def test_invalid_context_length(self):
        """Test validation of context length."""
        with pytest.raises(ValueError, match="Context length must be positive"):
            BaseModelConfig(
                context_length=0,
                max_tokens=1000,
            )

    def test_invalid_max_tokens(self):
        """Test validation of max tokens."""
        with pytest.raises(ValueError, match="Max tokens must be positive"):
            BaseModelConfig(
                context_length=4000,
                max_tokens=0,
            )

    def test_invalid_temperature_low(self):
        """Test validation of temperature (too low)."""
        with pytest.raises(ValueError, match="Temperature must be between 0 and 1"):
            BaseModelConfig(
                context_length=4000,
                max_tokens=1000,
                default_temp=-0.1,
            )

    def test_invalid_temperature_high(self):
        """Test validation of temperature (too high)."""
        with pytest.raises(ValueError, match="Temperature must be between 0 and 1"):
            BaseModelConfig(
                context_length=4000,
                max_tokens=1000,
                default_temp=1.1,
            )

    def test_none_max_tokens(self):
        """Test that None max_tokens is valid."""
        config = BaseModelConfig(
            context_length=4000,
            max_tokens=None,
        )
        assert config.max_tokens is None
