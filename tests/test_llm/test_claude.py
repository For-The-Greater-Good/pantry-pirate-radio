"""Unit tests for Claude provider."""

import asyncio
import json
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.providers.claude import (
    ClaudeConfig,
    ClaudeProvider,
    ClaudeNotAuthenticatedException,
    ClaudeQuotaExceededException,
)


@pytest.fixture
def claude_config() -> ClaudeConfig:
    """Create Claude config for testing."""
    return ClaudeConfig(
        model_name="claude-sonnet-4-20250514",
        temperature=0.3,
        max_tokens=4000,
    )


@pytest.fixture
def claude_provider(claude_config: ClaudeConfig) -> ClaudeProvider:
    """Create Claude provider for testing."""
    return ClaudeProvider(claude_config)


@pytest.fixture
def claude_provider_with_api_key(claude_config: ClaudeConfig) -> ClaudeProvider:
    """Create Claude provider with API key for testing."""
    return ClaudeProvider(claude_config, api_key="test-api-key")


def test_claude_config_defaults() -> None:
    """Test Claude config defaults."""
    config = ClaudeConfig(model_name="claude-sonnet-4-20250514")
    assert config.model_name == "claude-sonnet-4-20250514"
    assert config.temperature == 0.7
    assert config.max_tokens is None
    assert config.supports_structured is True


def test_claude_provider_init(claude_provider: ClaudeProvider) -> None:
    """Test Claude provider initialization."""
    # Mock environment to ensure no API key is set
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
        # Clear any cached api_key
        claude_provider._api_key = None
        assert claude_provider.model_name == "claude-sonnet-4-20250514"
        assert claude_provider.api_key == ""  # Empty string from environment


def test_claude_provider_init_with_api_key(
    claude_provider_with_api_key: ClaudeProvider,
) -> None:
    """Test Claude provider initialization with API key."""
    assert claude_provider_with_api_key.model_name == "claude-sonnet-4-20250514"
    assert claude_provider_with_api_key.api_key == "test-api-key"


def test_format_prompt(claude_provider: ClaudeProvider) -> None:
    """Test prompt formatting."""
    # Test simple string prompt
    prompt = "Hello world"
    formatted = claude_provider._format_prompt(prompt)
    assert formatted == "Hello world"

    # Test prompt with format schema
    prompt_with_format = "Generate JSON"
    format_schema = {"type": "object", "properties": {"message": {"type": "string"}}}
    formatted_with_schema = claude_provider._format_prompt(
        prompt_with_format, format_schema
    )
    assert "Generate JSON" in formatted_with_schema
    assert "helpful assistant" in formatted_with_schema
    assert "valid JSON" in formatted_with_schema


def test_build_cli_args(claude_provider: ClaudeProvider) -> None:
    """Test CLI argument building."""
    prompt = "Test prompt"

    # Test basic args
    args = claude_provider._build_cli_args(prompt)
    assert args[0] == "claude"
    assert "-p" in args
    assert prompt in args

    # Test with JSON format
    format_schema = {"type": "object"}
    args_with_format = claude_provider._build_cli_args(prompt, format=format_schema)
    assert "--output-format" in args_with_format
    assert "json" in args_with_format

    # Test with model name
    config_with_model = ClaudeConfig(model_name="claude-haiku")
    provider_with_model = ClaudeProvider(config_with_model)
    args_with_model = provider_with_model._build_cli_args(prompt)
    assert "--model" in args_with_model
    assert "claude-haiku" in args_with_model


@pytest.mark.asyncio
async def test_check_authentication_success(claude_provider: ClaudeProvider) -> None:
    """Test successful authentication check."""
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b'{"result": "Hello", "is_error": false}',
        b"",
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch(
            "asyncio.wait_for",
            return_value=(b'{"result": "Hello", "is_error": false}', b""),
        ):
            is_authenticated = await claude_provider._check_authentication()
            assert is_authenticated is True


@pytest.mark.asyncio
async def test_check_authentication_failure(claude_provider: ClaudeProvider) -> None:
    """Test failed authentication check."""
    mock_process = AsyncMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = (b"", b"Auth error")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch("asyncio.wait_for", return_value=(b"", b"Auth error")):
            is_authenticated = await claude_provider._check_authentication()
            assert is_authenticated is False


@pytest.mark.asyncio
async def test_check_authentication_timeout(claude_provider: ClaudeProvider) -> None:
    """Test authentication check timeout."""
    with patch("asyncio.create_subprocess_exec"):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            is_authenticated = await claude_provider._check_authentication()
            assert is_authenticated is False


def test_is_quota_exceeded_true(claude_provider: ClaudeProvider) -> None:
    """Test quota exceeded detection - positive case."""
    quota_response = json.dumps(
        {"result": "You've reached your usage limit for Claude", "is_error": True}
    )
    assert claude_provider._is_quota_exceeded(quota_response) is True


def test_is_quota_exceeded_false(claude_provider: ClaudeProvider) -> None:
    """Test quota exceeded detection - negative case."""
    normal_response = json.dumps({"result": "Hello world", "is_error": False})
    assert claude_provider._is_quota_exceeded(normal_response) is False


def test_is_quota_exceeded_various_indicators(claude_provider: ClaudeProvider) -> None:
    """Test quota exceeded detection with various indicators."""
    quota_indicators = [
        "usage limit",
        "quota exceeded",
        "rate limit",
        "too many requests",
        "throttle",
        "usage cap",
    ]

    for indicator in quota_indicators:
        response = json.dumps({"result": f"Error: {indicator} reached"})
        assert claude_provider._is_quota_exceeded(response) is True


def test_parse_cli_output(claude_provider: ClaudeProvider) -> None:
    """Test CLI output parsing."""
    # Test plain text output (no format)
    plain_output = "Just plain text"
    text, parsed, usage = claude_provider._parse_cli_output(plain_output)
    assert text == "Just plain text"
    assert parsed is None
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Test JSON output with format schema
    format_schema = {"type": "object", "properties": {"message": {"type": "string"}}}
    json_output = '{"result": "Hello world", "is_error": false}'
    text, parsed, usage = claude_provider._parse_cli_output(json_output, format_schema)
    assert text == "Hello world"
    assert parsed is None  # Not valid JSON structure
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Test with properly formatted JSON in result
    json_with_format = '{"result": "{\\"message\\": \\"Hello\\"}", "is_error": false}'
    text, parsed, usage = claude_provider._parse_cli_output(
        json_with_format, format_schema
    )
    assert text == '{"message": "Hello"}'
    assert parsed == {"message": "Hello"}


@pytest.mark.asyncio
async def test_health_check_authenticated(claude_provider: ClaudeProvider) -> None:
    """Test health check when authenticated."""
    with patch.object(claude_provider, "_check_authentication", return_value=True):
        health = await claude_provider.health_check()
        assert health["provider"] == "claude"
        assert health["status"] == "healthy"
        assert health["authenticated"] is True
        assert health["model"] == "claude-sonnet-4-20250514"
        assert "Ready" in health["message"]


@pytest.mark.asyncio
async def test_health_check_not_authenticated(claude_provider: ClaudeProvider) -> None:
    """Test health check when not authenticated."""
    with patch.object(claude_provider, "_check_authentication", return_value=False):
        health = await claude_provider.health_check()
        assert health["provider"] == "claude"
        assert health["status"] == "unhealthy"
        assert health["authenticated"] is False
        assert "Authentication required" in health["message"]


@pytest.mark.asyncio
async def test_health_check_exception(claude_provider: ClaudeProvider) -> None:
    """Test health check with exception."""
    with patch.object(
        claude_provider, "_check_authentication", side_effect=Exception("Test error")
    ):
        health = await claude_provider.health_check()
        assert health["provider"] == "claude"
        assert health["status"] == "unhealthy"
        assert health["authenticated"] is False
        assert "error" in health
        assert health["message"] == "Health check failed"


@pytest.mark.asyncio
async def test_generate_not_authenticated(claude_provider: ClaudeProvider) -> None:
    """Test generate when not authenticated."""
    with patch.object(claude_provider, "_check_authentication", return_value=False):
        with pytest.raises(ClaudeNotAuthenticatedException):
            await claude_provider.generate("Test prompt")


@pytest.mark.asyncio
async def test_generate_quota_exceeded(claude_provider: ClaudeProvider) -> None:
    """Test generate when quota is exceeded."""
    mock_process = AsyncMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = (
        b'{"result": "You\'ve reached your usage limit", "is_error": true}',
        b"Quota exceeded",
    )

    with patch.object(claude_provider, "_check_authentication", return_value=True):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(ClaudeQuotaExceededException) as exc_info:
                await claude_provider.generate("Test prompt")
            assert "quota exceeded" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_generate_success(claude_provider: ClaudeProvider) -> None:
    """Test successful generate call."""
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"Hello world", b"")  # Plain text response

    with patch.object(claude_provider, "_check_authentication", return_value=True):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_provider.generate("Test prompt")
            assert result.text == "Hello world"
            assert result.model == "claude-sonnet-4-20250514"
            assert result.usage["total_tokens"] == 0


@pytest.mark.asyncio
async def test_generate_with_api_key(
    claude_provider_with_api_key: ClaudeProvider,
) -> None:
    """Test generate with API key authentication."""
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b'{"result": "Hello world", "is_error": false}',
        b"",
    )

    with patch.object(
        claude_provider_with_api_key, "_check_authentication", return_value=True
    ):
        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await claude_provider_with_api_key.generate("Test prompt")
            # Verify that the subprocess was called with API key in environment
            mock_exec.assert_called_once()
            call_kwargs = mock_exec.call_args[1]
            assert "env" in call_kwargs
            assert call_kwargs["env"]["ANTHROPIC_API_KEY"] == "test-api-key"


@pytest.mark.asyncio
async def test_generate_structured_from_config(claude_provider: ClaudeProvider) -> None:
    """Test structured output generation with format in config (bug fix scenario)."""
    from app.llm.providers.types import GenerateConfig

    format_schema = {"type": "object", "properties": {"message": {"type": "string"}}}
    config = GenerateConfig(
        temperature=0.7,
        format=format_schema,
    )
    
    # Mock successful CLI execution with structured output
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b'{"result": "{\\"message\\": \\"Hello Config\\"}", "is_error": false}',
        b"",
    )

    with patch.object(claude_provider, "_check_authentication", return_value=True):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_provider.generate(
                "Return a JSON object with message: 'Hello Config'",
                config=config,
            )
            assert result.text == '{"message": "Hello Config"}'
            assert result.parsed == {"message": "Hello Config"}


@pytest.mark.asyncio
async def test_generate_structured_separate_format(claude_provider: ClaudeProvider) -> None:
    """Test structured output generation with separate format parameter (backward compatibility)."""
    format_schema = {"type": "object", "properties": {"message": {"type": "string"}}}
    
    # Mock successful CLI execution with structured output
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b'{"result": "{\\"message\\": \\"Hello Separate\\"}", "is_error": false}',
        b"",
    )

    with patch.object(claude_provider, "_check_authentication", return_value=True):
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_provider.generate(
                "Return a JSON object with message: 'Hello Separate'",
                format=format_schema,
            )
            assert result.text == '{"message": "Hello Separate"}'
            assert result.parsed == {"message": "Hello Separate"}


def test_claude_exceptions() -> None:
    """Test Claude-specific exceptions."""
    # Test ClaudeQuotaExceededException
    quota_exc = ClaudeQuotaExceededException("Quota exceeded")
    assert str(quota_exc) == "Quota exceeded"
    assert quota_exc.retry_after == 3600  # Default 1 hour

    quota_exc_custom = ClaudeQuotaExceededException("Quota exceeded", retry_after=7200)
    assert quota_exc_custom.retry_after == 7200  # Custom 2 hours

    # Test ClaudeNotAuthenticatedException
    auth_exc = ClaudeNotAuthenticatedException("Not authenticated")
    assert str(auth_exc) == "Not authenticated"
    assert auth_exc.retry_after == 300  # Default 5 minutes

    auth_exc_custom = ClaudeNotAuthenticatedException(
        "Not authenticated", retry_after=600
    )
    assert auth_exc_custom.retry_after == 600  # Custom 10 minutes
