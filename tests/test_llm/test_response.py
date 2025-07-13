"""Tests for LLM response types."""

from typing import Any, Dict, List, Tuple, cast

import pytest

from app.llm.providers.types import LLMResponse, RawResponse
from tests.test_llm.test_constants import TEST_MODEL_NAME

# Test cases for invalid values
INVALID_CASES: List[Tuple[str, str, Dict[str, Any], str]] = [
    ("", TEST_MODEL_NAME, {"tokens": 1}, "Response text cannot be empty"),
    ("test", "", {"tokens": 1}, "Model name cannot be empty"),
    ("test", TEST_MODEL_NAME, {}, "Usage statistics cannot be empty"),
    ("test", TEST_MODEL_NAME, {"tokens": -1}, "Usage values must be non-negative"),
    ("test", TEST_MODEL_NAME, {"tokens": 1.5}, "Usage values must be integers"),
    # Edge cases
    ("\n", TEST_MODEL_NAME, {"tokens": 1}, "Response text cannot be empty"),
    ("test", " ", {"tokens": 1}, "Model name cannot be empty"),
    (
        "test",
        TEST_MODEL_NAME,
        cast(Dict[str, int], {"tokens": None}),
        "Usage values must be integers",
    ),
    (
        "test",
        TEST_MODEL_NAME,
        cast(Dict[str, int], {"tokens": "1"}),
        "Usage values must be integers",
    ),
]

# Test cases for valid usage statistics
VALID_USAGE_CASES: List[Dict[str, int]] = [
    {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    {"tokens": 100},
    {"input_tokens": 50, "output_tokens": 25, "total": 75},
    # Edge cases
    {"tokens": 0},  # Zero is valid as it's non-negative
    {"prompt": 0, "completion": 0, "total": 0},
    {"t1": 1, "t2": 2, "t3": 3, "t4": 4, "t5": 5},  # Many fields
]

# Test cases for raw data
RAW_DATA_CASES: List[RawResponse] = [
    {
        "extra": "data",
        "metadata": {"key": "value"},
        "choices": [{"index": 0, "text": "Test response"}],
    },
    {
        "model": "test-model",
        "created": 1234567890,
        "usage": {"total_tokens": 100},
    },
    {
        "id": "test-id",
        "object": "completion",
        "created": 1234567890,
        "model": "test-model",
        "choices": [{"text": "Test response", "index": 0, "logprobs": None}],
    },
    # Edge cases
    {
        "metadata": {},  # Empty metadata
        "choices": [],  # Empty choices
    },
    {
        "metadata": cast(
            Dict[str, Any],
            {
                "key": "value",
                "nested": {
                    "key1": "value1",
                    "key2": {"subkey": "subvalue"},
                },
            },
        ),
        # Multiple choices
        "choices": [{"index": i, "text": f"Choice {i}"} for i in range(5)],
    },
]

# Test cases for structured output
STRUCTURED_DATA_CASES: List[Dict[str, Any]] = [
    {
        "name": "John",
        "age": 30,
        "hobbies": ["reading", "coding"],
    },
    {
        "location": {
            "city": "New York",
            "coordinates": {"lat": 40.7128, "lon": -74.0060},
        },
        "population": 8400000,
    },
    # Edge cases
    {},  # Empty object
    {"key": None},  # Null value
    {"nested": {"deeply": {"nested": {"value": 42}}}},  # Deep nesting
]

pytestmark = pytest.mark.anyio


async def test_llm_response_valid() -> None:
    """Test valid LLM response creation."""
    usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    response = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage=usage,
    )

    assert response.text == "Test response"
    assert response.model == TEST_MODEL_NAME
    assert response.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    }
    assert response.raw == {}
    assert response.parsed is None
    assert response.content == response.text
    assert str(response) == response.text


@pytest.mark.parametrize("raw_data", RAW_DATA_CASES)
async def test_llm_response_with_raw(raw_data: RawResponse) -> None:
    """Test LLM response with various raw data formats."""
    response = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage={"prompt_tokens": 10},
        raw=raw_data,
    )

    assert response.raw == raw_data


@pytest.mark.parametrize("usage", VALID_USAGE_CASES)
async def test_llm_response_valid_usage(usage: Dict[str, int]) -> None:
    """Test LLM response with various valid usage statistics."""
    response = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage=usage,
    )
    assert response.usage == usage


@pytest.mark.parametrize("text,model,usage,expected_error", INVALID_CASES)
async def test_llm_response_invalid_values(
    text: str,
    model: str,
    usage: Dict[str, Any],
    expected_error: str,
) -> None:
    """Test LLM response with invalid values."""
    with pytest.raises(ValueError, match=expected_error):
        LLMResponse(text=text, model=model, usage=usage)


@pytest.mark.parametrize("parsed_data", STRUCTURED_DATA_CASES)
async def test_llm_response_with_parsed(parsed_data: Dict[str, Any]) -> None:
    """Test LLM response with structured output."""
    response = LLMResponse(
        text=str(parsed_data),
        model=TEST_MODEL_NAME,
        usage={"prompt_tokens": 10},
        parsed=parsed_data,
    )

    assert response.parsed == parsed_data
    assert response.text == str(parsed_data)


async def test_llm_response_equality() -> None:
    """Test LLM response equality comparison."""
    response1 = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage={"tokens": 1},
    )
    response2 = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage={"tokens": 1},
    )
    response3 = LLMResponse(
        text="Different response",
        model=TEST_MODEL_NAME,
        usage={"tokens": 1},
    )

    assert response1 == response2
    assert response1 != response3
    assert hash(response1) == hash(response2)
    assert hash(response1) != hash(response3)
    assert response1 != "not a response"  # Test comparison with different type


async def test_llm_response_immutability() -> None:
    """Test LLM response immutability."""
    # Test immutability of usage dictionary
    usage = {"tokens": 1}
    response = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage=usage,
    )
    usage["tokens"] = 2
    assert response.usage == {"tokens": 1}

    # Test immutability of raw dictionary with nested structures
    raw_data: RawResponse = {
        "metadata": cast(
            Dict[str, Any],
            {
                "key": "value",
                "nested": {"key1": "value1"},
            },
        ),
        "choices": [{"index": 0, "text": "Test"}],
    }
    response = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage={"tokens": 1},
        raw=raw_data,
    )

    # Modify nested structures
    metadata = cast(Dict[str, Any], raw_data["metadata"])
    metadata["key"] = "modified"
    nested = cast(Dict[str, Any], metadata["nested"])
    nested["key1"] = "modified"
    choices = cast(List[Dict[str, Any]], raw_data["choices"])
    choices[0]["text"] = "modified"

    # Response should maintain original values
    assert response.raw == {
        "metadata": {
            "key": "value",
            "nested": {"key1": "value1"},
        },
        "choices": [{"index": 0, "text": "Test"}],
    }

    # Test immutability of parsed data
    parsed_data = {"name": "John", "age": 30}
    response = LLMResponse(
        text=str(parsed_data),
        model=TEST_MODEL_NAME,
        usage={"tokens": 1},
        parsed=parsed_data,
    )
    parsed_data["name"] = "Jane"
    assert response.parsed == {"name": "John", "age": 30}


async def test_llm_response_hash_stability() -> None:
    """Test LLM response hash stability with different usage key orders."""
    response1 = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage={"a": 1, "b": 2},
    )
    response2 = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage={"b": 2, "a": 1},  # Different order, same content
    )

    assert hash(response1) == hash(response2)
    assert response1 == response2


async def test_llm_response_content_property() -> None:
    """Test LLM response content property."""
    response = LLMResponse(
        text="Test response",
        model=TEST_MODEL_NAME,
        usage={"tokens": 1},
    )
    assert response.content == response.text
    assert response.content == str(response)
