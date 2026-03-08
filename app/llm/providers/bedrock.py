"""AWS Bedrock provider implementation using the Converse API.

Provides both a provider class (BedrockProvider) and reusable module-level
functions (build_converse_request, parse_converse_response) for constructing
and parsing Bedrock Converse API requests/responses. The module-level functions
are used by both the provider and the batch inference Lambdas.
"""

import asyncio
import json
from typing import Any

from app.core.logging import get_logger
from app.llm.config import LLMConfig
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig, LLMInput, LLMResponse

logger = get_logger().bind(module="bedrock_provider")


# ---------------------------------------------------------------------------
# Module-level reusable functions for Converse API request/response handling.
# Used by BedrockProvider.generate() and by batch inference Lambdas.
# ---------------------------------------------------------------------------


def _build_messages(prompt: LLMInput) -> list[dict[str, Any]]:
    """Convert LLMInput into Bedrock message format.

    Bedrock requires content as [{"text": "..."}] arrays.
    System messages are excluded here (handled by _extract_system_prompt).

    Args:
        prompt: String or list of chat messages

    Returns:
        List of Bedrock-format messages
    """
    if isinstance(prompt, str):
        return [{"role": "user", "content": [{"text": prompt}]}]

    messages: list[dict[str, Any]] = []
    for msg in prompt:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            continue  # Handled separately
        messages.append({"role": role, "content": [{"text": content}]})
    return messages


def _extract_system_prompt(prompt: LLMInput) -> list[dict[str, str]] | None:
    """Extract system messages into Bedrock's separate system parameter.

    Args:
        prompt: String or list of chat messages

    Returns:
        System prompt list for Bedrock, or None
    """
    if isinstance(prompt, str):
        return None

    system_parts: list[dict[str, str]] = []
    for msg in prompt:
        if msg.get("role") == "system":
            system_parts.append({"text": msg.get("content", "")})

    return system_parts if system_parts else None


def _build_tool_config(
    schema: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build Bedrock toolConfig for structured output via forced tool use.

    Handles the pipeline's wrapper format:
    {"type": "json_schema", "json_schema": {"name": ..., "schema": {...}}}

    Args:
        schema: JSON schema or None

    Returns:
        Bedrock toolConfig dict, or None if no schema
    """
    if schema is None:
        return None

    # Unwrap pipeline's json_schema wrapper if present
    inner_schema = schema
    if (
        isinstance(schema, dict)
        and schema.get("type") == "json_schema"
        and "json_schema" in schema
    ):
        json_schema = schema["json_schema"]
        inner_schema = json_schema.get("schema", json_schema)

    # Validate the unwrapped schema has minimum required structure
    if not isinstance(inner_schema, dict):
        logger.warning(
            "Bedrock schema is not a dict, skipping tool config",
            schema_type=type(inner_schema).__name__,
        )
        return None

    if "type" not in inner_schema:
        logger.warning(
            "Bedrock schema missing 'type' field",
            schema_keys=list(inner_schema.keys()),
        )

    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "structured_output",
                    "description": "Output structured data matching the schema",
                    "inputSchema": {"json": inner_schema},
                }
            }
        ],
        "toolChoice": {"tool": {"name": "structured_output"}},
    }


def _map_usage(bedrock_usage: dict[str, int]) -> dict[str, int]:
    """Map Bedrock usage fields to standard format.

    Args:
        bedrock_usage: Bedrock's {inputTokens, outputTokens} dict

    Returns:
        Standard {prompt_tokens, completion_tokens, total_tokens} dict
    """
    prompt = bedrock_usage.get("inputTokens", 0)
    completion = bedrock_usage.get("outputTokens", 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def build_converse_request(
    prompt: LLMInput,
    format_schema: dict[str, Any] | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Build a Converse API request body from an LLM prompt.

    This is the public entry point used by both BedrockProvider.generate()
    and the Batcher Lambda to construct request bodies.

    Args:
        prompt: String or list of chat messages
        format_schema: Optional JSON schema for structured output
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens to generate (omitted if None)

    Returns:
        Dict with messages, inferenceConfig, and optionally system/toolConfig.
        Does NOT include modelId (caller sets that).
    """
    messages = _build_messages(prompt)
    system = _extract_system_prompt(prompt)

    params: dict[str, Any] = {
        "messages": messages,
        "inferenceConfig": {
            "temperature": temperature,
        },
    }

    if max_tokens is not None:
        params["inferenceConfig"]["maxTokens"] = max_tokens

    if system:
        params["system"] = system

    tool_config = _build_tool_config(format_schema)
    if tool_config:
        params["toolConfig"] = tool_config

    return params


def parse_converse_response(
    response: dict[str, Any],
    model_id: str,
    format_schema: dict[str, Any] | None = None,
) -> LLMResponse:
    """Parse a Bedrock Converse API response into an LLMResponse.

    This is the public entry point used by both BedrockProvider.generate()
    and the Result Processor Lambda to parse Converse responses.

    Args:
        response: Raw Converse API response dict
        model_id: Model identifier for the response
        format_schema: Optional JSON schema (enables structured output parsing)

    Returns:
        LLMResponse with text, model, usage, and optionally parsed data

    Raises:
        ValueError: If the response contains no content
    """
    output = response.get("output", {})
    message = output.get("message", {})
    content_blocks = message.get("content", [])
    stop_reason = response.get("stopReason", "")
    usage = _map_usage(response.get("usage", {}))

    # Handle tool_use (structured output)
    if stop_reason == "tool_use" and format_schema:
        for block in content_blocks:
            if "toolUse" in block:
                parsed_data = block["toolUse"]["input"]
                return LLMResponse(
                    text=json.dumps(parsed_data),
                    model=model_id,
                    usage=usage,
                    parsed=parsed_data,
                )

    # Handle text response
    text_parts = [block["text"] for block in content_blocks if "text" in block]
    if not text_parts:
        raise ValueError("Empty response from Bedrock")

    text = "".join(text_parts)

    # Try to parse JSON if format was requested
    parsed = None
    if format_schema and text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as parse_err:
            logger.warning(
                "Failed to parse JSON from Bedrock text response",
                error=str(parse_err),
                content_length=len(text),
                content_preview=text[:500],
                model=model_id,
            )

    response_data: dict[str, Any] = {
        "text": text,
        "model": model_id,
        "usage": usage,
    }
    if parsed is not None:
        response_data["parsed"] = parsed

    return LLMResponse(**response_data)


# ---------------------------------------------------------------------------
# BedrockProvider class
# ---------------------------------------------------------------------------


class BedrockConfig(LLMConfig):
    """Configuration for AWS Bedrock provider."""

    def __init__(
        self,
        model_name: str = "anthropic.claude-sonnet-4-6",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        region_name: str | None = None,
    ) -> None:
        """Initialize Bedrock config.

        Args:
            model_name: Bedrock model identifier (e.g. anthropic.claude-sonnet-4-6)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum number of tokens to generate
            region_name: AWS region for Bedrock endpoint
        """
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            supports_structured=True,
        )
        self.region_name = region_name


class BedrockProvider(BaseLLMProvider[Any, BedrockConfig]):
    """AWS Bedrock provider using the Converse API."""

    def __init__(
        self,
        config: BedrockConfig,
        **kwargs: Any,
    ) -> None:
        """Initialize the Bedrock provider.

        Args:
            config: Provider configuration
            **kwargs: Additional configuration
        """
        self.config = config
        self._client: Any | None = None
        super().__init__(
            model_name=config.model_name,
            **kwargs,
        )

    def _init_config(self, **kwargs: Any) -> BedrockConfig:
        """Initialize provider configuration."""
        model_name = kwargs.get("model_name", self.model_name)
        if not model_name:
            raise ValueError("model_name is required")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens")
        region_name = kwargs.get("region_name")
        return BedrockConfig(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            region_name=region_name,
        )

    @property
    def environment_key(self) -> str:
        """AWS uses credential chain, not a single API key."""
        return "AWS_DEFAULT_REGION"

    @property
    def model(self) -> Any:
        """Get or create the Bedrock runtime client (lazy import of boto3)."""
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 is required for the Bedrock provider. "
                    "Install it with: pip install boto3"
                ) from None

            client_kwargs: dict[str, Any] = {
                "service_name": "bedrock-runtime",
            }
            if self.config.region_name:
                client_kwargs["region_name"] = self.config.region_name
            self._client = boto3.client(**client_kwargs)
        return self._client

    # Keep instance methods as thin wrappers for backward compatibility
    # with tests that call provider._build_messages(), etc.

    def _build_messages(self, prompt: LLMInput) -> list[dict[str, Any]]:
        """Convert LLMInput into Bedrock message format."""
        return _build_messages(prompt)

    def _extract_system_prompt(self, prompt: LLMInput) -> list[dict[str, str]] | None:
        """Extract system messages into Bedrock's separate system parameter."""
        return _extract_system_prompt(prompt)

    def _build_tool_config(
        self, schema: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Build Bedrock toolConfig for structured output."""
        return _build_tool_config(schema)

    def _map_usage(self, bedrock_usage: dict[str, int]) -> dict[str, int]:
        """Map Bedrock usage fields to standard format."""
        return _map_usage(bedrock_usage)

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response using Bedrock Converse API.

        Args:
            prompt: The input prompt or chat messages
            config: Optional generation configuration
            format: Optional JSON schema for structured output
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse: Generated response

        Raises:
            ValueError: If there is an error in generation
        """
        try:
            # Check if format is embedded in config
            if (
                format is None
                and config is not None
                and hasattr(config, "format")
                and config.format
            ):
                format = config.format

            temperature = config.temperature if config else self.config.temperature

            # Build request using shared function
            request_body = build_converse_request(
                prompt=prompt,
                format_schema=format,
                temperature=temperature,
                max_tokens=self.config.max_tokens,
            )

            # Add modelId (not included in build_converse_request)
            params = {"modelId": self.config.model_name, **request_body}

            logger.info(
                "Making Bedrock Converse request",
                model=self.config.model_name,
                has_format=format is not None,
            )

            # Run synchronous boto3 call in a thread
            client = self.model
            result = await asyncio.to_thread(client.converse, **params)

            # Parse response using shared function
            return parse_converse_response(
                response=result,
                model_id=self.config.model_name,
                format_schema=format,
            )

        except ValueError:
            raise
        except Exception as e:
            logger.error("Error in Bedrock generation", exc_info=e)
            raise ValueError(f"Error generating with Bedrock: {e}") from e
