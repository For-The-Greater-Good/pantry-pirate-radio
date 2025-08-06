"""Tests for OpenAI native structured output implementation."""

import pytest
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.types import GenerateConfig


def test_build_api_params_with_native_structured_output():
    """Test that _build_api_params correctly handles native structured output."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="gpt-4"),
        api_key="test-key"
    )
    
    # Test with the double-wrapped schema format (as it comes from schema_converter)
    messages = [{"role": "user", "content": "Convert this data"}]
    config = GenerateConfig(
        format={
            "type": "json_schema",
            "json_schema": {
                "name": "hsds_organization",
                "description": "HSDS organization data",
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"}
                    },
                    "required": ["name", "description"]
                },
                "strict": True
            }
        }
    )
    
    params = provider._build_api_params(messages, config)
    
    # Should have response_format parameter with unwrapped schema
    assert "response_format" in params
    assert params["response_format"]["type"] == "json_schema"
    assert "json_schema" in params["response_format"]
    assert params["response_format"]["json_schema"]["name"] == "hsds_organization"
    assert params["response_format"]["json_schema"]["strict"] is True
    
    # Schema should be properly unwrapped
    schema = params["response_format"]["json_schema"]["schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "name" in schema["properties"]
    

def test_build_api_params_without_structured_output():
    """Test that _build_api_params works without structured output."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="gpt-4"),
        api_key="test-key"
    )
    
    messages = [{"role": "user", "content": "Just chat"}]
    
    params = provider._build_api_params(messages, None)
    
    # Should NOT have response_format when no format specified
    assert "response_format" not in params
    assert "model" in params
    assert "messages" in params
    assert params["messages"] == messages


def test_build_api_params_with_invalid_format():
    """Test that _build_api_params handles invalid format gracefully."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="gpt-4"),
        api_key="test-key"
    )
    
    messages = [{"role": "user", "content": "Convert this data"}]
    
    # Test with wrong format structure
    config = GenerateConfig(
        format={"type": "something_else", "data": {}}
    )
    
    params = provider._build_api_params(messages, config)
    
    # Should NOT add response_format for invalid structure
    assert "response_format" not in params
    

def test_remove_json_formatting_from_messages():
    """Test that JSON formatting instructions are removed when using native structured output."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="gpt-4"),
        api_key="test-key"
    )
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant that always responds with valid JSON."},
        {"role": "user", "content": "Convert this data"}
    ]
    
    cleaned = provider._remove_json_formatting_from_messages(messages)
    
    # System message about JSON should be removed
    assert len(cleaned) == 1
    assert cleaned[0]["role"] == "user"
    assert cleaned[0]["content"] == "Convert this data"
    

def test_remove_json_formatting_preserves_non_json_messages():
    """Test that non-JSON related messages are preserved."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="gpt-4"),
        api_key="test-key"
    )
    
    messages = [
        {"role": "system", "content": "You are an expert at HSDS data conversion."},
        {"role": "user", "content": "Convert this data"}
    ]
    
    cleaned = provider._remove_json_formatting_from_messages(messages)
    
    # Both messages should be preserved
    assert len(cleaned) == 2
    assert cleaned[0]["content"] == "You are an expert at HSDS data conversion."
    

def test_format_messages_no_longer_adds_json_instructions():
    """Test that _format_messages doesn't add JSON instructions anymore."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="gpt-4"),
        api_key="test-key"
    )
    
    # With format parameter (used to add JSON instructions)
    format_schema = {"type": "object", "properties": {"test": {"type": "string"}}}
    messages = provider._format_messages("Test prompt", format_schema)
    
    # Should NOT add system message about JSON anymore
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Test prompt"
    assert "valid JSON" not in messages[0]["content"]
    

def test_full_flow_with_wrapped_schema():
    """Test the full flow with a wrapped schema as it comes from schema_converter."""
    provider = OpenAIProvider(
        OpenAIConfig(model_name="gpt-4"),
        api_key="test-key"
    )
    
    # This is how the schema comes from schema_converter (with TODO comment)
    wrapped_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "hsds_organization",
            "description": "Structured output schema for HSDS organization data",
            "schema": {
                "type": "object",
                "properties": {
                    "organization": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"}
                            }
                        }
                    }
                },
                "required": ["organization"]
            },
            "strict": True,
            "max_tokens": 64768,
            "temperature": 0.4
        }
    }
    
    config = GenerateConfig(format=wrapped_schema)
    messages = [{"role": "user", "content": "Convert food pantry data"}]
    
    params = provider._build_api_params(messages, config)
    
    # Verify the schema is properly unwrapped for OpenAI
    assert "response_format" in params
    assert params["response_format"]["type"] == "json_schema"
    
    # The inner json_schema should be properly extracted
    json_schema = params["response_format"]["json_schema"]
    assert json_schema["name"] == "hsds_organization"
    assert json_schema["strict"] is True
    assert "schema" in json_schema
    
    # The actual schema structure should be preserved
    schema = json_schema["schema"]
    assert schema["type"] == "object"
    assert "organization" in schema["properties"]
    assert schema["properties"]["organization"]["type"] == "array"