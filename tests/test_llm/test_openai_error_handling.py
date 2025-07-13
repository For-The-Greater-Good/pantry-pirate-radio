"""Tests for OpenAI provider error handling functions."""

import json
import pytest

from app.llm.providers.openai import (
    _extract_openrouter_error,
    _extract_direct_error,
    _extract_nested_error,
    _extract_error_message,
    _extract_json_from_markdown,
)


def test_extract_openrouter_error_missing_metadata():
    """Test _extract_openrouter_error with missing metadata."""
    error_dict = {"some": "error"}
    result = _extract_openrouter_error(error_dict)
    assert result == str(error_dict)


def test_extract_openrouter_error_missing_raw():
    """Test _extract_openrouter_error with missing raw in metadata."""
    error_dict = {"metadata": {"some": "data"}}
    result = _extract_openrouter_error(error_dict)
    assert result == str(error_dict)


def test_extract_openrouter_error_invalid_json():
    """Test _extract_openrouter_error with invalid JSON in raw."""
    error_dict = {"metadata": {"raw": "invalid json"}}
    result = _extract_openrouter_error(error_dict)
    assert result == str(error_dict)


def test_extract_openrouter_error_missing_error_message():
    """Test _extract_openrouter_error with valid JSON but missing error.message."""
    error_dict = {"metadata": {"raw": json.dumps({"some": "data"})}}
    result = _extract_openrouter_error(error_dict)
    assert result == str(error_dict)


def test_extract_openrouter_error_valid_error():
    """Test _extract_openrouter_error with valid error message."""
    error_data = {"error": {"message": "API quota exceeded"}}
    error_dict = {"metadata": {"raw": json.dumps(error_data)}}
    result = _extract_openrouter_error(error_dict)
    assert result == "API quota exceeded"


def test_extract_openrouter_error_json_decode_error():
    """Test _extract_openrouter_error handles JSON decode errors."""
    error_dict = {"metadata": {"raw": '{"invalid": json}'}}
    result = _extract_openrouter_error(error_dict)
    assert result == str(error_dict)


def test_extract_openrouter_error_key_error():
    """Test _extract_openrouter_error handles key errors in nested structure."""
    error_data = {"error": {"code": 401}}  # Missing message key
    error_dict = {"metadata": {"raw": json.dumps(error_data)}}
    result = _extract_openrouter_error(error_dict)
    assert result == str(error_dict)


def test_extract_direct_error_with_message():
    """Test _extract_direct_error with message present."""
    error_dict = {"message": "Direct error message"}
    result = _extract_direct_error(error_dict)
    assert result == "Direct error message"


def test_extract_direct_error_without_message():
    """Test _extract_direct_error without message."""
    error_dict = {"code": 500, "details": "some details"}
    result = _extract_direct_error(error_dict)
    assert result == str(error_dict)


def test_extract_nested_error_with_valid_structure():
    """Test _extract_nested_error with valid nested error."""
    error_dict = {"error": {"message": "Nested error message", "code": 400}}
    result = _extract_nested_error(error_dict)
    assert result == "Nested error message"


def test_extract_nested_error_with_invalid_structure():
    """Test _extract_nested_error with invalid structure."""
    error_dict = {"error": "not a dict"}
    result = _extract_nested_error(error_dict)
    assert result == str(error_dict)


def test_extract_nested_error_missing_error_key():
    """Test _extract_nested_error with missing error key."""
    error_dict = {"some": "data"}
    result = _extract_nested_error(error_dict)
    assert result == str(error_dict)


def test_extract_nested_error_missing_message():
    """Test _extract_nested_error with error dict but no message."""
    error_dict = {"error": {"code": 500}}
    result = _extract_nested_error(error_dict)
    assert result == str(error_dict)


def test_extract_error_message_with_dict():
    """Test _extract_error_message with dictionary input."""
    error_dict = {"message": "Test error"}
    result = _extract_error_message(error_dict)
    # Should use first extractor (openrouter) which returns string representation when no metadata found
    assert result == str(error_dict)


def test_extract_error_message_with_string():
    """Test _extract_error_message with string input."""
    error_str = "Simple error message"
    result = _extract_error_message(error_str)
    # Should convert string to dict and then return string representation
    expected_dict = {"message": error_str}
    assert result == str(expected_dict)


def test_extract_error_message_with_exception_in_extractor():
    """Test _extract_error_message handles exceptions in extractors."""
    # Create a malformed error dict that might cause issues
    error_dict = {"complex": {"nested": {"structure": None}}}
    result = _extract_error_message(error_dict)
    # Should return string representation as fallback
    assert result == str(error_dict)


def test_extract_json_from_markdown_with_json_block():
    """Test _extract_json_from_markdown with JSON code block."""
    markdown_text = """Here is some JSON:
```json
{"key": "value", "number": 42}
```
Some more text."""

    result = _extract_json_from_markdown(markdown_text)
    expected = '{"key": "value", "number": 42}'
    assert result == expected


def test_extract_json_from_markdown_with_plain_block():
    """Test _extract_json_from_markdown with plain code block containing JSON."""
    markdown_text = """Response:
```
{"status": "success", "data": [1, 2, 3]}
```"""

    result = _extract_json_from_markdown(markdown_text)
    expected = '{"status": "success", "data": [1, 2, 3]}'
    assert result == expected


def test_extract_json_from_markdown_no_code_blocks():
    """Test _extract_json_from_markdown with no code blocks."""
    markdown_text = "This is just plain text with no code blocks."
    result = _extract_json_from_markdown(markdown_text)
    assert result == markdown_text


def test_extract_json_from_markdown_empty_code_block():
    """Test _extract_json_from_markdown with empty code block."""
    markdown_text = """Text before
```json
```
Text after"""

    result = _extract_json_from_markdown(markdown_text)
    # Should return original text if code block is empty
    assert result == markdown_text
