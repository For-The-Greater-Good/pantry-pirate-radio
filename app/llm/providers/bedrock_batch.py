"""Claude Messages API functions for Bedrock batch inference.

Provides request/response handling for the InvokeModel (Messages API) format
used by batch inference. Distinct from the Converse API functions in bedrock.py
because Converse batch serialization drops toolUse.input content.

Used by:
- Batcher Lambda: build_messages_api_request() to construct JSONL input
- Result Processor Lambda: parse_messages_api_response() to parse output
"""

import json
from typing import Any

from app.core.logging import get_logger
from app.llm.providers.types import LLMInput, LLMResponse

logger = get_logger().bind(module="bedrock_batch")


def build_messages_api_request(
    prompt: LLMInput,
    format_schema: dict[str, Any] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    """Build a Claude Messages API request body for Bedrock InvokeModel.

    Used by the Batcher Lambda for batch inference, which requires the
    InvokeModel format (not Converse) because Converse batch serialization
    drops toolUse.input content.

    Args:
        prompt: String or list of chat messages
        format_schema: Optional JSON schema for structured output
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens to generate

    Returns:
        Dict in Claude Messages API format (anthropic_version, messages, etc.)
    """
    # Build messages
    messages: list[dict[str, Any]] = []
    system_text: str | None = None

    if isinstance(prompt, str):
        messages = [{"role": "user", "content": prompt}]
    else:
        system_parts = []
        for msg in prompt:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                messages.append({"role": role, "content": content})
        if system_parts:
            system_text = "\n".join(system_parts)

    params: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }

    if system_text:
        params["system"] = system_text

    if format_schema is not None:
        # Unwrap pipeline's json_schema wrapper if present
        inner_schema = format_schema
        if (
            isinstance(format_schema, dict)
            and format_schema.get("type") == "json_schema"
            and "json_schema" in format_schema
        ):
            json_schema = format_schema["json_schema"]
            inner_schema = json_schema.get("schema", json_schema)

        params["tools"] = [
            {
                "name": "structured_output",
                "description": "Output structured data matching the schema",
                "input_schema": inner_schema,
            }
        ]
        params["tool_choice"] = {"type": "tool", "name": "structured_output"}

    return params


def parse_messages_api_response(
    response: dict[str, Any],
    model_id: str,
    format_schema: dict[str, Any] | None = None,
) -> LLMResponse:
    """Parse a Claude Messages API response into an LLMResponse.

    Used by the Result Processor Lambda for batch inference output, which
    uses InvokeModel format (not Converse).

    Args:
        response: Raw Messages API response dict
        model_id: Model identifier for the response
        format_schema: Optional JSON schema (enables structured output parsing)

    Returns:
        LLMResponse with text, model, usage, and optionally parsed data

    Raises:
        ValueError: If the response contains no content
    """
    content_blocks = response.get("content", [])
    stop_reason = response.get("stop_reason", "")
    raw_usage = response.get("usage", {})
    usage = {
        "prompt_tokens": raw_usage.get("input_tokens", 0),
        "completion_tokens": raw_usage.get("output_tokens", 0),
        "total_tokens": (
            raw_usage.get("input_tokens", 0) + raw_usage.get("output_tokens", 0)
        ),
    }

    # Handle tool_use (structured output)
    if stop_reason == "tool_use" and format_schema:
        for block in content_blocks:
            if block.get("type") == "tool_use":
                parsed_data = block.get("input", {})
                return LLMResponse(
                    text=json.dumps(parsed_data),
                    model=model_id,
                    usage=usage,
                    parsed=parsed_data,
                )

    # Handle text response
    text_parts = []
    for block in content_blocks:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    if not text_parts:
        raise ValueError("Empty response from Bedrock")

    text = "".join(text_parts)

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
