"""Test that scraper utils correctly passes schema for structured outputs."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.scraper.utils import ScraperUtils

# Ensure required env vars for testing
import os

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def test_scraper_passes_full_schema_structure(monkeypatch):
    """Test that ScraperUtils passes the full schema structure to LLMJob."""

    # Mock the schema converter to return the correct double-wrapped format
    mock_schema = {
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
                                "description": {"type": "string"},
                            },
                            "required": ["name", "description"],
                        },
                    }
                },
                "required": ["organization"],
            },
            "strict": True,
            "max_tokens": 64768,
            "temperature": 0.4,
        },
    }

    # Mock SchemaConverter to avoid file system dependency
    from app.llm.hsds_aligner.schema_converter import SchemaConverter

    monkeypatch.setattr(SchemaConverter, "__init__", lambda self, schema_path: None)
    monkeypatch.setattr(
        SchemaConverter,
        "convert_to_llm_schema",
        lambda self, entity_type: mock_schema,
    )

    # Mock other dependencies
    with patch("app.llm.hsds_aligner.validation.ValidationConfig"):
        with patch("pathlib.Path.read_text", return_value="Test prompt"):
            with patch("app.llm.queue.queues.llm_queue") as mock_queue:
                with patch(
                    "app.content_store.config.get_content_store", return_value=None
                ):
                    with patch("app.core.events.get_setting") as mock_get_setting:
                        # Mock settings
                        mock_get_setting.side_effect = lambda key, *args, **kwargs: {
                            "llm_provider": "openai",
                            "llm_model_name": "gpt-4",
                            "llm_temperature": 0.7,
                            "llm_max_tokens": None,
                        }.get(key)

                        # Mock queue
                        mock_job = MagicMock()
                        mock_job.id = "test-job-id"
                        mock_queue.enqueue_call.return_value = mock_job

                        # Create scraper utils
                        utils = ScraperUtils("test_scraper")

                        # Queue content for processing
                        job_id = utils.queue_for_processing("Test content")

                        # Verify the job was created correctly
                        assert job_id == "test-job-id"

                        # Check that enqueue_call was called
                        assert mock_queue.enqueue_call.called

                        # Get the LLMJob that was passed to enqueue_call
                        call_args = mock_queue.enqueue_call.call_args
                        llm_job = call_args[1]["args"][
                            0
                        ]  # First argument to process_llm_job

                        # Verify the format is the full schema structure
                        assert llm_job.format == mock_schema
                        assert llm_job.format["type"] == "json_schema"
                        assert "json_schema" in llm_job.format
                        assert (
                            llm_job.format["json_schema"]["name"] == "hsds_organization"
                        )
                        assert llm_job.format["json_schema"]["strict"] is True
                        assert "schema" in llm_job.format["json_schema"]


def test_openai_provider_unwraps_schema_correctly():
    """Test that OpenAI provider correctly unwraps the schema for response_format."""
    from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
    from app.llm.providers.types import GenerateConfig

    # Create provider
    provider = OpenAIProvider(OpenAIConfig(model_name="gpt-4"), api_key="test-key")

    # Create the format as it comes from ScraperUtils (full structure)
    format_from_scraper = {
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
                                "description": {"type": "string"},
                            },
                            "required": ["name", "description"],
                        },
                    }
                },
                "required": ["organization"],
            },
            "strict": True,
        },
    }

    # Create config with the format
    config = GenerateConfig(format=format_from_scraper)

    # Build API params
    messages = [{"role": "user", "content": "Convert this data"}]
    params = provider._build_api_params(messages, config)

    # Verify response_format is correctly set
    assert "response_format" in params
    assert params["response_format"]["type"] == "json_schema"
    assert "json_schema" in params["response_format"]

    # Check that the schema was properly unwrapped
    json_schema = params["response_format"]["json_schema"]
    assert json_schema["name"] == "hsds_organization"
    assert json_schema["strict"] is True
    assert "schema" in json_schema

    # Verify the actual schema structure
    schema = json_schema["schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "organization" in schema["properties"]
    assert schema["properties"]["organization"]["type"] == "array"
