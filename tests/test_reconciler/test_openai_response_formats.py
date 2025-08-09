"""Tests for OpenAI response format handling in job processor."""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from datetime import datetime

from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus
from app.llm.providers.types import LLMResponse
from app.reconciler.job_processor import JobProcessor


class TestOpenAIResponseFormats:
    """Test cases for different OpenAI response formats."""

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    def test_should_handle_array_at_top_level(
        self, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that array responses from OpenAI are handled correctly."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # OpenAI sometimes returns an array at the top level
        llm_response = LLMResponse(
            text="""[
{
    "metadata": {
        "version": "3.1.1",
        "last_action_date": "2023-10-27",
        "source": "freshtrak_api",
        "id": "org_1"
    },
    "organization": {
        "name": "Salvation Army Marion",
        "description": "A Salvation Army branch providing food pantry services."
    },
    "locations": [],
    "services": []
}
]""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "freshtrak",
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
        mock_location_instance = mock_location_creator.return_value

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        assert result["status"] == "success"
        assert result["scraper_id"] == "freshtrak"

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    def test_should_handle_organization_as_object_not_array(
        self, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that organization object (not array) responses are handled correctly."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # OpenAI sometimes returns organization as a single object instead of array
        llm_response = LLMResponse(
            text="""{
    "organization": {
        "id": "org_1",
        "name": "SDA Community Service Chillicothe",
        "description": "SDA Community Service Chillicothe is a food pantry."
    },
    "services": [],
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
                "scraper_id": "freshtrak",
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
        mock_location_instance = mock_location_creator.return_value

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        assert result["status"] == "success"
        assert result["scraper_id"] == "freshtrak"
        # Verify that the organization was processed (meaning it was converted to array format)
        mock_org_instance.process_organization.assert_called_once()

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    def test_should_handle_claude_format_unchanged(
        self, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that standard Claude format still works correctly."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Standard Claude format that was already working
        llm_response = LLMResponse(
            text="""{
    "organization": [{
        "id": "test-123",
        "name": "Food Bank",
        "description": "Test food bank"
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
        mock_location_instance = mock_location_creator.return_value

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        assert result["status"] == "success"
        assert result["scraper_id"] == "test_scraper"
        # Verify that the organization was processed normally
        mock_org_instance.process_organization.assert_called_once()
