"""Tests for AWS Bedrock LLM provider."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.llm.providers.bedrock import (
    BedrockConfig,
    BedrockProvider,
    build_converse_request,
    parse_converse_response,
)


class TestBedrockConfig:
    """Tests for BedrockConfig."""

    def test_defaults(self):
        """Test default config values."""
        config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        assert config.model_name == "anthropic.claude-sonnet-4-6"
        assert config.temperature == 0.7
        assert config.max_tokens is None
        assert config.region_name is None
        assert config.supports_structured is True

    def test_custom_values(self):
        """Test config with custom values."""
        config = BedrockConfig(
            model_name="anthropic.claude-sonnet-4-6",
            temperature=0.3,
            max_tokens=4096,
            region_name="us-west-2",
        )
        assert config.temperature == 0.3
        assert config.max_tokens == 4096
        assert config.region_name == "us-west-2"


class TestBedrockProviderInit:
    """Tests for BedrockProvider initialization."""

    def test_init(self):
        """Test provider initialization."""
        config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        provider = BedrockProvider(config)
        assert provider.config.model_name == "anthropic.claude-sonnet-4-6"

    def test_environment_key(self):
        """Test environment key returns AWS region var."""
        config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        provider = BedrockProvider(config)
        assert provider.environment_key == "AWS_DEFAULT_REGION"

    def test_should_raise_clear_error_when_boto3_missing(self):
        """Test that a clear ImportError is raised when boto3 is not installed."""
        config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        provider = BedrockProvider(config)
        provider._client = None
        with patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ImportError, match="boto3 is required"):
                _ = provider.model


class TestBuildMessages:
    """Tests for message building."""

    def setup_method(self):
        self.config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        self.provider = BedrockProvider(self.config)

    def test_string_input(self):
        """Test converting string input to messages."""
        messages = self.provider._build_messages("Hello world")
        assert messages == [{"role": "user", "content": [{"text": "Hello world"}]}]

    def test_chat_format_input(self):
        """Test converting chat-format input to messages."""
        chat_input = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        messages = self.provider._build_messages(chat_input)
        # System messages are handled separately, so they should be excluded
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": [{"text": "Hello"}]}
        assert messages[1] == {"role": "assistant", "content": [{"text": "Hi there"}]}


class TestExtractSystemPrompt:
    """Tests for system prompt extraction."""

    def setup_method(self):
        self.config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        self.provider = BedrockProvider(self.config)

    def test_extract_system_from_messages(self):
        """Test extracting system messages."""
        chat_input = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        system = self.provider._extract_system_prompt(chat_input)
        assert system == [
            {"text": "You are helpful", "cacheControl": {"type": "ephemeral"}}
        ]

    def test_no_system_prompt(self):
        """Test when no system messages exist."""
        chat_input = [{"role": "user", "content": "Hello"}]
        system = self.provider._extract_system_prompt(chat_input)
        assert system is None

    def test_string_input_no_system(self):
        """Test string input returns None for system."""
        system = self.provider._extract_system_prompt("Hello")
        assert system is None


class TestBuildToolConfig:
    """Tests for structured output tool config construction."""

    def setup_method(self):
        self.config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        self.provider = BedrockProvider(self.config)

    def test_schema_unwrapping(self):
        """Test unwrapping pipeline's json_schema wrapper."""
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
        }
        tool_config = self.provider._build_tool_config(schema)
        assert tool_config is not None
        assert tool_config["toolChoice"] == {"tool": {"name": "structured_output"}}
        tool_spec = tool_config["tools"][0]["toolSpec"]
        assert tool_spec["name"] == "structured_output"
        assert tool_spec["inputSchema"]["json"]["type"] == "object"

    def test_direct_schema(self):
        """Test passing a direct JSON schema."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        tool_config = self.provider._build_tool_config(schema)
        assert tool_config is not None
        tool_spec = tool_config["tools"][0]["toolSpec"]
        assert tool_spec["inputSchema"]["json"]["type"] == "object"

    def test_none_schema(self):
        """Test None schema returns None."""
        tool_config = self.provider._build_tool_config(None)
        assert tool_config is None

    def test_build_tool_config_warns_on_non_dict_schema(self):
        """Test that a non-dict inner schema returns None with a warning."""
        # Wrap a string inside the pipeline json_schema format
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": "not-a-dict",
            },
        }
        result = self.provider._build_tool_config(schema)
        assert result is None

    def test_build_tool_config_warns_on_missing_type_field(self):
        """Test that a schema missing 'type' logs a warning but still builds config."""
        schema = {"properties": {"name": {"type": "string"}}}
        tool_config = self.provider._build_tool_config(schema)
        assert tool_config is not None
        tool_spec = tool_config["tools"][0]["toolSpec"]
        assert tool_spec["inputSchema"]["json"] == schema

    def test_build_tool_config_handles_empty_schema(self):
        """Test that an empty dict schema warns but returns valid config."""
        tool_config = self.provider._build_tool_config({})
        assert tool_config is not None
        tool_spec = tool_config["tools"][0]["toolSpec"]
        assert tool_spec["inputSchema"]["json"] == {}


class TestMapUsage:
    """Tests for usage statistics mapping."""

    def setup_method(self):
        self.config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        self.provider = BedrockProvider(self.config)

    def test_map_usage(self):
        """Test camelCase to snake_case mapping."""
        bedrock_usage = {"inputTokens": 100, "outputTokens": 50}
        usage = self.provider._map_usage(bedrock_usage)
        assert usage == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

    def test_map_usage_missing_fields(self):
        """Test mapping with missing fields defaults to 0."""
        usage = self.provider._map_usage({})
        assert usage == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }


class TestBedrockGenerate:
    """Tests for generate method."""

    def setup_method(self):
        self.config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        self.provider = BedrockProvider(self.config)

    @pytest.mark.asyncio
    async def test_generate_text_response(self):
        """Test generating a text response."""
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "Hello from Bedrock!"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }

        with patch.object(
            BedrockProvider,
            "model",
            new_callable=lambda: property(lambda self: mock_client),
        ):
            response = await self.provider.generate("Say hello")

        assert response.text == "Hello from Bedrock!"
        assert response.model == "anthropic.claude-sonnet-4-6"
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 5
        assert response.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_generate_structured_response(self):
        """Test generating a structured (tool use) response."""
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "structured_output",
                                "input": {"name": "Test Food Bank", "city": "Portland"},
                                "toolUseId": "tool-123",
                            }
                        }
                    ]
                }
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 20, "outputTokens": 15},
        }

        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "city": {"type": "string"},
                    },
                },
            },
        }

        with patch.object(
            BedrockProvider,
            "model",
            new_callable=lambda: property(lambda self: mock_client),
        ):
            response = await self.provider.generate("Parse this data", format=schema)

        assert response.parsed == {"name": "Test Food Bank", "city": "Portland"}
        assert response.usage["total_tokens"] == 35

    @pytest.mark.asyncio
    async def test_generate_error_handling(self):
        """Test error handling wraps ClientError in ValueError."""
        mock_boto3 = MagicMock()
        # Simulate a botocore ClientError
        from botocore.exceptions import ClientError

        error_response = {
            "Error": {"Code": "ValidationException", "Message": "Bad request"}
        }
        mock_client = MagicMock()
        mock_client.converse.side_effect = ClientError(error_response, "Converse")

        with patch.object(
            BedrockProvider,
            "model",
            new_callable=lambda: property(lambda self: mock_client),
        ):
            with pytest.raises(ValueError, match="Bedrock validation error"):
                await self.provider.generate("test")

    @pytest.mark.asyncio
    async def test_generate_empty_response(self):
        """Test handling of empty response."""
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": []}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 5, "outputTokens": 0},
        }

        with patch.object(
            BedrockProvider,
            "model",
            new_callable=lambda: property(lambda self: mock_client),
        ):
            with pytest.raises(ValueError, match="Empty response from Bedrock"):
                await self.provider.generate("test")


class TestBuildConverseRequest:
    """Tests for the module-level build_converse_request function."""

    def test_build_converse_request_string_prompt(self):
        """String input produces Bedrock user message format."""
        result = build_converse_request(prompt="Hello world")
        assert result["messages"] == [
            {"role": "user", "content": [{"text": "Hello world"}]}
        ]
        assert result["inferenceConfig"]["temperature"] == 0.7
        assert "system" not in result
        assert "toolConfig" not in result

    def test_build_converse_request_with_system_prompt(self):
        """Chat messages with system role extract system prompt correctly."""
        prompt = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        result = build_converse_request(prompt=prompt)
        assert result["system"] == [
            {"text": "You are helpful", "cacheControl": {"type": "ephemeral"}}
        ]
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"

    def test_build_converse_request_with_tool_config(self):
        """Schema produces toolConfig with forced tool use."""
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
        }
        result = build_converse_request(prompt="test", format_schema=schema)
        assert "toolConfig" in result
        assert result["toolConfig"]["toolChoice"] == {
            "tool": {"name": "structured_output"}
        }

    def test_build_converse_request_custom_temperature_and_max_tokens(self):
        """Custom temperature and max_tokens are set in inferenceConfig."""
        result = build_converse_request(prompt="test", temperature=0.3, max_tokens=1024)
        assert result["inferenceConfig"]["temperature"] == 0.3
        assert result["inferenceConfig"]["maxTokens"] == 1024

    def test_build_converse_request_no_max_tokens_by_default(self):
        """maxTokens is not set when not provided."""
        result = build_converse_request(prompt="test")
        assert "maxTokens" not in result["inferenceConfig"]


class TestParseConverseResponse:
    """Tests for the module-level parse_converse_response function."""

    def test_parse_converse_response_text(self):
        """Text response extracts text and maps usage."""
        response = {
            "output": {"message": {"content": [{"text": "Hello from Bedrock!"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }
        result = parse_converse_response(
            response=response,
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
        )
        assert result.text == "Hello from Bedrock!"
        assert result.model == "anthropic.claude-haiku-4-5-20251001-v1:0"
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5
        assert result.usage["total_tokens"] == 15

    def test_parse_converse_response_tool_use(self):
        """Structured output from tool_use blocks is parsed correctly."""
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "city": {"type": "string"},
                    },
                },
            },
        }
        response = {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "structured_output",
                                "input": {
                                    "name": "Test Food Bank",
                                    "city": "Portland",
                                },
                                "toolUseId": "tool-123",
                            }
                        }
                    ]
                }
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 20, "outputTokens": 15},
        }
        result = parse_converse_response(
            response=response,
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
            format_schema=schema,
        )
        assert result.parsed == {"name": "Test Food Bank", "city": "Portland"}
        assert result.text == json.dumps(result.parsed)
        assert result.usage["total_tokens"] == 35

    def test_parse_converse_response_empty_content(self):
        """Empty content blocks raise ValueError."""
        response = {
            "output": {"message": {"content": []}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 5, "outputTokens": 0},
        }
        with pytest.raises(ValueError, match="Empty response from Bedrock"):
            parse_converse_response(
                response=response,
                model_id="test-model",
            )

    def test_parse_converse_response_json_text_with_schema(self):
        """Text response with format_schema attempts JSON parse."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        response = {
            "output": {"message": {"content": [{"text": '{"name": "Food Bank"}'}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }
        result = parse_converse_response(
            response=response,
            model_id="test-model",
            format_schema=schema,
        )
        assert result.parsed == {"name": "Food Bank"}


class TestGenerateStillWorks:
    """Verify generate() still works after refactoring to use module-level functions."""

    def setup_method(self):
        self.config = BedrockConfig(model_name="anthropic.claude-sonnet-4-6")
        self.provider = BedrockProvider(self.config)

    @pytest.mark.asyncio
    async def test_generate_uses_extracted_functions(self):
        """generate() should produce the same results as before extraction."""
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "Hello!"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }

        with patch.object(
            BedrockProvider,
            "model",
            new_callable=lambda: property(lambda self: mock_client),
        ):
            response = await self.provider.generate("Say hello")

        assert response.text == "Hello!"
        assert response.model == "anthropic.claude-sonnet-4-6"
        assert response.usage["total_tokens"] == 15

        # Verify converse was called with expected params
        call_kwargs = mock_client.converse.call_args[1]
        assert call_kwargs["modelId"] == "anthropic.claude-sonnet-4-6"
        assert call_kwargs["messages"] == [
            {"role": "user", "content": [{"text": "Say hello"}]}
        ]


class TestBedrockFactoryRegistration:
    """Test that Bedrock is registered in the provider factory."""

    def test_bedrock_in_registry(self):
        """Test that bedrock is registered in the factory."""
        from app.llm.providers.factory import _PROVIDER_REGISTRY

        assert "bedrock" in _PROVIDER_REGISTRY

    def test_create_bedrock_via_factory(self):
        """Test creating a Bedrock provider via the factory."""
        from app.llm.providers.factory import create_provider

        provider = create_provider("bedrock", "anthropic.claude-sonnet-4-6", 0.7, None)
        assert isinstance(provider, BedrockProvider)
        assert provider.config.model_name == "anthropic.claude-sonnet-4-6"
