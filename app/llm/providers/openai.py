"""OpenAI provider implementation with structured output support."""

import json
import re
from typing import Any, NotRequired, TypedDict, cast

from openai import AsyncOpenAI
from openai._exceptions import OpenAIError
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.completion_usage import CompletionUsage

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.config import LLMConfig
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig, LLMInput, LLMResponse

logger = get_logger().bind(module="openai_provider")


def _extract_openrouter_error(error_dict: dict[str, Any | dict[str, Any]]) -> str:
    """Extract error message from OpenRouter error format.

    Args:
        error_dict: Dictionary containing error data

    Returns:
        str: Error message
    """
    if "metadata" not in error_dict or "raw" not in error_dict["metadata"]:
        return str(error_dict)

    try:
        raw = json.loads(error_dict["metadata"]["raw"])
        if "error" in raw and "message" in raw["error"]:
            return raw["error"]["message"]
    except (json.JSONDecodeError, KeyError):
        return str(error_dict)
    return str(error_dict)


def _extract_direct_error(error_dict: dict[str, Any | str]) -> str:
    """Extract direct error message from dictionary.

    Args:
        error_dict: Dictionary containing error data

    Returns:
        str: Error message
    """
    return str(error_dict["message"]) if "message" in error_dict else str(error_dict)


def _extract_nested_error(error_dict: dict[str, Any | dict[str, str]]) -> str:
    """Extract error message from nested error object.

    Args:
        error_dict: Dictionary containing error data

    Returns:
        str: Error message
    """
    if "error" in error_dict and isinstance(error_dict["error"], dict):
        if "message" in error_dict["error"]:
            return str(error_dict["error"]["message"])
    return str(error_dict)


def _extract_error_message(error: Any) -> str:
    """Extract error message from API error response.

    Args:
        error: API error response

    Returns:
        str: Error message
    """
    error_dict = error if isinstance(error, dict) else {"message": str(error)}

    extractors = [
        _extract_openrouter_error,
        _extract_direct_error,
        _extract_nested_error,
    ]

    for extractor in extractors:
        try:
            return extractor(error_dict)
        except (KeyError, json.JSONDecodeError, AttributeError) as e:
            logger.debug(
                "Error extraction failed with %s: %s", extractor.__name__, str(e)
            )
            continue

    # If all extractors fail, return string representation
    return str(error_dict)


def _extract_json_from_markdown(text: str) -> str:
    """Extract JSON content from markdown code blocks.

    Args:
        text: Text that may contain markdown code blocks

    Returns:
        str: Extracted JSON content or original text if no code blocks found
    """
    # Look for ```json ... ``` blocks
    json_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if json_block_match:
        return json_block_match.group(1).strip()
    return text


def _validate_usage(usage: CompletionUsage | dict[str, Any]) -> dict[str, int]:
    """Validate and convert usage statistics.

    Args:
        usage: Raw usage statistics from API response

    Returns:
        dict[str, int]: Validated usage statistics
    """
    if isinstance(usage, CompletionUsage):
        usage = usage.model_dump()
    return {
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }


def _validate_json_schema(schema: dict[str, Any]) -> None:
    """Validate JSON schema format.

    Args:
        schema: JSON schema to validate

    Raises:
        ValueError: If schema is invalid
    """
    if "type" not in schema:
        raise ValueError("Invalid JSON schema: missing 'type' field")

    valid_types = ["object", "array", "string", "number", "integer", "boolean", "null"]
    schema_type = str(schema.get("type"))

    if schema_type not in valid_types:
        raise ValueError(
            f"Invalid JSON schema: type '{schema_type}' not in {valid_types}"
        )

    # Recursively validate nested properties
    if schema_type == "object" and "properties" in schema:
        properties = cast(dict[str, Any], schema.get("properties", {}))
        if not isinstance(properties, dict):
            raise ValueError("Invalid JSON schema: 'properties' must be a dictionary")

        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                raise ValueError(
                    f"Invalid JSON schema: property '{prop_name}' schema must be a dictionary"
                )
            if "type" not in prop_schema:
                raise ValueError(
                    f"Invalid JSON schema: property '{prop_name}' missing 'type' field"
                )
            prop_type = str(prop_schema.get("type"))
            if prop_type not in valid_types:
                raise ValueError(
                    f"Invalid JSON schema: invalid property type '{prop_type}' for '{prop_name}'"
                )


class ResponseDict(TypedDict):
    """Response dictionary."""

    text: str
    model: str
    usage: NotRequired[dict[str, int]]
    parsed: NotRequired[Any]


class OpenAIConfig(LLMConfig):
    """Configuration for OpenAI provider"""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> None:
        """Initialize OpenAI config.

        Args:
            model_name: Name of the model to use
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum number of tokens to generate
        """
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            supports_structured=True,
        )


class OpenAIProvider(BaseLLMProvider[AsyncOpenAI, OpenAIConfig]):
    """OpenAI provider implementation"""

    def __init__(
        self,
        config: OpenAIConfig,
        api_key: str | None = None,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize the provider

        Args:
            config: Provider configuration
            api_key: API key for authentication
            base_url: Base URL for API endpoint
            headers: Additional HTTP headers
        """
        self.config = config
        self._client: AsyncOpenAI | None = None
        super().__init__(
            model_name=config.model_name,
            api_key=api_key,
            base_url=base_url or "https://openrouter.ai/api/v1",
            headers=headers
            or {
                "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
                "X-Title": "Pantry Pirate Radio",
                "X-Provider-Preferences": json.dumps(
                    {
                        "require_parameters": True  # Only use providers that support all parameters
                    }
                ),
            },
        )

    def _init_config(self, **kwargs: Any) -> OpenAIConfig:
        """Initialize provider configuration.

        Args:
            **kwargs: Configuration parameters

        Returns:
            OpenAIConfig: Provider configuration
        """
        # Get model_name from kwargs or self
        model_name = kwargs.get("model_name", self.model_name)
        if not model_name:
            raise ValueError("model_name is required")

        # Get temperature from kwargs or default
        temperature = kwargs.get("temperature", 0.7)

        # Get max_tokens from kwargs
        max_tokens = kwargs.get("max_tokens")

        return OpenAIConfig(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @property
    def environment_key(self) -> str:
        """Get the environment variable name for the API key."""
        return "OPENROUTER_API_KEY"

    @property
    def api_key(self) -> str | None:
        """Get the API key from settings or environment."""
        if self._api_key is not None:
            return self._api_key

        # Try to get from settings first (reads .env file properly)
        api_key = getattr(settings, "OPENROUTER_API_KEY", None)
        if api_key and api_key not in ("your_api_key_here", "", "sk-"):
            return api_key

        # Fall back to environment variable
        import os

        return os.environ.get(self.environment_key)

    @property
    def model(self) -> AsyncOpenAI:
        """Get or create the OpenAI client instance."""
        if self._client is None:
            api_key = self.api_key
            if not api_key:
                raise ValueError("API key is required")

            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.base_url,
                default_headers=self.headers,
            )
        return self._client

    def _format_messages(
        self,
        prompt: LLMInput,
        format: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        """Format input prompt into messages list.

        Args:
            prompt: The prompt to format
            format: Optional JSON schema for structured output

        Returns:
            list[dict[str, str]]: Formatted messages
        """
        if isinstance(prompt, str):
            # No need to add JSON formatting instructions when using native structured output
            # The response_format parameter will handle this
            return [{"role": "user", "content": prompt}]
        return cast(list[dict[str, str]], prompt)

    def _remove_json_formatting_from_messages(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Remove JSON formatting instructions from messages when using native structured output.

        Args:
            messages: List of messages potentially containing JSON formatting instructions

        Returns:
            list[dict[str, str]]: Messages with JSON formatting removed
        """
        cleaned_messages = []
        for msg in messages:
            if msg.get("role") == "system" and "valid JSON" in msg.get("content", ""):
                # Skip system messages that are purely about JSON formatting
                continue
            cleaned_messages.append(msg)
        return cleaned_messages if cleaned_messages else messages

    def _build_api_params(
        self,
        messages: list[dict[str, str]],
        config: GenerateConfig | None = None,
        format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build parameters for API call.

        Args:
            messages: Formatted messages
            config: Generation configuration
            format: Optional JSON schema for structured output

        Returns:
            dict[str, Any]: API parameters
        """
        params: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": config.temperature if config else self.config.temperature,
        }
        if self.config.max_tokens is not None:
            params["max_tokens"] = self.config.max_tokens

        # Use format parameter directly, fall back to config.format if not provided
        schema_format = format
        if not schema_format and config and config.format:
            schema_format = config.format
        
        # TODO: Remove schema wrapper unwrapping once downstream services updated
        # Currently schema comes wrapped as {"type": "json_schema", "json_schema": {...}}
        # OpenAI expects just the inner json_schema part for response_format
        if schema_format:
            if (
                isinstance(schema_format, dict)
                and schema_format.get("type") == "json_schema"
            ):
                # Extract inner schema for OpenAI response_format
                json_schema = schema_format.get("json_schema", {})
                if "schema" in json_schema:
                    params["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": json_schema.get("name", "response"),
                            "schema": json_schema["schema"],
                            "strict": json_schema.get("strict", True),
                        },
                    }
                    # Remove JSON formatting from system message since we're using native structured output
                    messages = self._remove_json_formatting_from_messages(messages)

        return params

    def _process_json_content(
        self,
        content: str,
        format: dict[str, Any] | None = None,
    ) -> tuple[str, Any | None]:
        """Process and parse JSON content.

        Args:
            content: Raw content string
            format: Optional JSON schema

        Returns:
            tuple[str, Any | None]: Processed content and parsed JSON if applicable
        """
        content = _extract_json_from_markdown(content)
        parsed = None
        if format and content:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                if "cannot" in content.lower() or "refuse" in content.lower():
                    return content, None
                return "Invalid JSON response", None
        return content.strip(), parsed

    def _process_api_response(
        self,
        result: ChatCompletion,
        format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Process API response.

        Args:
            result: API response
            format: Optional JSON schema

        Returns:
            LLMResponse: Processed response
        """
        # Handle API errors
        error = getattr(result, "error", None)
        if error:
            error_msg = _extract_error_message(error)
            base_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            usage = _validate_usage(result.usage) if result.usage else base_usage
            return LLMResponse(
                text=error_msg,
                model=self.config.model_name,
                usage=usage,
            )

        # Handle empty response
        if not result.choices or not result.choices[0].message:
            return LLMResponse(
                text=(
                    "No response from model"
                    if not result.choices
                    else "Empty response from model"
                ),
                model=self.config.model_name,
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

        # Process content
        content = str(result.choices[0].message.content or "")
        processed_content, parsed = self._process_json_content(content, format)

        # Build response
        base_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        usage = _validate_usage(result.usage) if result.usage else base_usage

        response_data: dict[str, Any] = {
            "text": processed_content,
            "model": self.config.model_name,
            "usage": usage,
        }
        if parsed is not None:
            response_data["parsed"] = parsed

        return LLMResponse(**response_data)

    def _handle_api_error(self, error: Exception) -> None:
        """Handle API errors.

        Args:
            error: The error to handle

        Raises:
            ValueError: With appropriate error message
        """
        if isinstance(error, OpenAIError):
            logger.error("Error in API call", exc_info=error)
            error_msg = str(error)
            raise ValueError(f"Error generating completion: {error_msg}")
        elif isinstance(error, ValueError):
            if "API key is required" in str(error):
                raise ValueError("API key is required")
            if "Invalid JSON schema" in str(error):
                raise ValueError(str(error))
            raise ValueError(f"Error generating completion: {error!s}")
        else:
            logger.error("Error in API call", exc_info=error)
            error_msg = _extract_error_message(error)
            raise ValueError(f"Error generating completion: {error_msg}")

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text from a prompt

        Args:
            prompt: The prompt to generate from
            config: Generation configuration
            format: JSON schema for structured output
            **kwargs: Additional arguments passed to the model

        Returns:
            LLMResponse: The generated response

        Raises:
            ValueError: If there is an error in generation
        """
        try:
            # Check if format is embedded in config when format parameter is None
            if (
                format is None
                and config is not None
                and hasattr(config, "format")
                and config.format
            ):
                format = config.format
            # Format messages
            messages = self._format_messages(prompt, format)

            # Build API parameters
            params = self._build_api_params(messages, config, format)

            # Log request details
            logger.info("Making API request to %s", self.base_url)
            logger.info(
                "Request parameters: %s",
                json.dumps({k: v for k, v in params.items() if k != "messages"}),
            )
            logger.debug("Full request parameters: %s", json.dumps(params))

            # Make API call
            result = cast(
                ChatCompletion, await self.model.chat.completions.create(**params)
            )

            # Log response
            logger.info("Received API response from %s", self.base_url)
            logger.debug("Raw response: %s", json.dumps(result.model_dump()))

            # Process response
            return self._process_api_response(result, format)

        except Exception as e:
            self._handle_api_error(e)
            # Ensure we always return or raise
            raise ValueError("Error in API call")

    async def health_check(self) -> bool:
        """Check if the OpenAI provider is healthy.

        Returns:
            bool: True if the provider is healthy, False otherwise

        Raises:
            Exception: If the health check fails
        """
        try:
            # Make a minimal API call to test connectivity
            result = await self.model.chat.completions.create(
                model=self.config.model_name,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                temperature=0,
            )
            return result is not None
        except Exception as e:
            logger.error("Health check failed", exc_info=e)
            raise
