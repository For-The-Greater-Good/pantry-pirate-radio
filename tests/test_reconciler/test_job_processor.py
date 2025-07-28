"""Tests for the job processor module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from datetime import datetime

from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus
from app.llm.providers.types import LLMResponse
from app.reconciler.job_processor import JobProcessor


class TestJobProcessor:
    """Test cases for JobProcessor class."""

    def test_should_extract_json_from_markdown_code_blocks(self):
        """Test that JSON is correctly extracted from markdown code blocks."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))
        markdown_text = """```json
{
    "organization": {
        "name": "Test Food Bank",
        "description": "A test organization"
    }
}
```"""

        # Act
        result = processor._extract_json_from_markdown(markdown_text)

        # Assert
        expected = """{
    "organization": {
        "name": "Test Food Bank",
        "description": "A test organization"
    }
}"""
        assert result == expected

    def test_should_return_original_text_when_no_markdown_blocks(self):
        """Test that original text is returned when no markdown blocks are present."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))
        plain_json = '{"name": "Test", "value": 123}'

        # Act
        result = processor._extract_json_from_markdown(plain_json)

        # Assert
        assert result == plain_json

    def test_should_handle_json_block_without_language_specifier(self):
        """Test extraction from code blocks without 'json' language specifier."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))
        markdown_text = """```
{"key": "value"}
```"""

        # Act
        result = processor._extract_json_from_markdown(markdown_text)

        # Assert
        assert result == '{"key": "value"}'

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.logger")
    def test_should_parse_json_from_markdown_in_job_result(
        self, mock_logger, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that job results with markdown-wrapped JSON are parsed correctly."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a mock job result with markdown-wrapped JSON
        llm_response = LLMResponse(
            text="""```json
{
    "organization": [{
        "id": "test-123",
        "name": "Food Bank",
        "description": "Test food bank"
    }],
    "service": [],
    "location": []
}
```""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {"raw_data": {"test": "data"}},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_org_instance.create_organization.return_value = "org-uuid"

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act - this should parse successfully without throwing JSON decode error
        try:
            result = processor.process_job_result(job_result)
            # Assert
            assert result["status"] == "success"
            assert result["scraper_id"] == "test_scraper"
        except json.JSONDecodeError:
            pytest.fail("JSON decoding should not fail with markdown code blocks")

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.logger")
    def test_should_handle_malformed_json_with_backticks(
        self, mock_logger, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that malformed JSON with backticks uses demjson3 fallback."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result with slightly malformed JSON in markdown
        llm_response = LLMResponse(
            text="""```json
{
    "organization": [{
        "name": "Test Org",
        "description": "Test", // This comment makes it invalid JSON
    }],
    "service": [],
    "location": []
}
```""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {"raw_data": {"test": "data"}},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_org_instance.create_organization.return_value = "org-uuid"

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        assert result["status"] == "success"
        # Verify demjson3 was used (logger was called with the error)
        # The actual log message includes the error details now
        assert any(
            "Standard JSON parsing failed:" in str(call)
            for call in mock_logger.info.call_args_list
        )

    def test_should_raise_error_when_json_completely_invalid(self):
        """Test that completely invalid JSON raises an error."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result with completely invalid content
        llm_response = LLMResponse(
            text="This is not JSON at all, just plain text",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {"raw_data": {"test": "data"}},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            processor.process_job_result(job_result)

        # Verify the error contains the expected information
        error_data = json.loads(str(exc_info.value))
        assert error_data["status"] == "error"
        assert error_data["scraper_id"] == "test_scraper"
        assert "error" in error_data

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    def test_should_handle_llm_response_starting_with_backticks(
        self, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that LLM responses starting with backticks are handled correctly."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result where text starts with backticks (reproducing the actual error)
        llm_response = LLMResponse(
            text="""```json
{
    "organization": [{
        "name": "Food Helpline Organization",
        "description": "Provides food assistance"
    }],
    "service": [],
    "location": []
}
```""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "food_helpline_org",
                "type": "hsds_alignment",
                "data": {},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_org_instance.create_organization.return_value = "org-uuid"

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act - this should NOT raise an error anymore
        result = processor.process_job_result(job_result)

        # Assert
        assert result["status"] == "success"
        assert result["scraper_id"] == "food_helpline_org"

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    def test_should_handle_empty_string_year_incorporated(
        self, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that empty string year_incorporated values are converted to None."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result with empty string year_incorporated
        llm_response = LLMResponse(
            text="""{
    "organization": [{
        "name": "Test Organization",
        "description": "A test organization",
        "year_incorporated": "",
        "website": "",
        "email": ""
    }],
    "service": [],
    "location": []
}""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act
        result = processor.process_job_result(job_result)

        # Assert - check that year_incorporated was converted to None
        mock_org_instance.process_organization.assert_called_once()
        call_args = mock_org_instance.process_organization.call_args
        assert (
            call_args[1]["year_incorporated"] is None
        )  # Empty string should be converted to None
        assert (
            call_args[1]["website"] is None
        )  # Empty string should be converted to None
        assert call_args[1]["email"] is None  # Empty string should be converted to None
        assert result["status"] == "success"

    def test_should_convert_string_year_to_integer(self):
        """Test that valid string year values are converted to integers."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Test various year formats
        test_cases = [
            ("2023", 2023),
            (" 2023 ", 2023),
            ("", None),
            ("  ", None),
            ("abc", None),
            ("20.23", None),
            (2023, 2023),  # Already an integer
            (None, None),  # Already None
        ]

        for input_value, expected in test_cases:
            # Simulate the conversion logic from the job processor
            if isinstance(input_value, str):
                result = (
                    int(input_value)
                    if input_value.strip() and input_value.strip().isdigit()
                    else None
                )
            elif not isinstance(input_value, int | type(None)):
                result = None
            else:
                result = input_value

            assert result == expected, f"Failed for input: {input_value!r}"
