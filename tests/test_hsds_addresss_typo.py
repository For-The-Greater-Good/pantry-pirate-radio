"""Test that the HSDS specification's 'addresss' field (with 3 s's) is handled correctly."""

import json
import pytest
from unittest.mock import MagicMock, patch, Mock
from uuid import uuid4
from datetime import datetime

from app.reconciler.job_processor import JobProcessor
from app.llm.queue.types import JobResult, JobStatus
from app.llm.queue.job import LLMJob
from app.llm.providers.types import LLMResponse


class TestHSDSAddresssTypo:
    """Test handling of HSDS 'addresss' field with 3 s's."""

    def test_should_process_addresss_with_three_s(self):
        """Test that location 'addresss' field with 3 s's is processed correctly."""
        # Arrange
        job_id = str(uuid4())
        job_data = {
            "organization": [
                {"name": "Test Food Bank", "description": "A test food bank"}
            ],
            "location": [
                {
                    "name": "Test Location",
                    "description": "Test location description",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "addresss": [
                        {  # Note: 3 s's as per HSDS spec
                            "address_1": "123 Main St",
                            "city": "New York",
                            "state_province": "NY",
                            "postal_code": "10001",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                }
            ],
        }

        # Create LLMJob
        llm_job = LLMJob(
            id=job_id,
            prompt="Test prompt",
            raw_data=job_data,
            metadata={"scraper_id": "test_scraper"},
            created_at=datetime.now(),
        )

        # Create LLMResponse
        llm_response = LLMResponse(
            text=json.dumps(job_data),
            model="test-model",
            usage={"total_tokens": 100},
        )

        # Create JobResult
        job_result = JobResult(
            job_id=job_id,
            job=llm_job,
            status=JobStatus.COMPLETED,
            result=llm_response,
            completed_at=datetime.now(),
            processing_time=1.0,
        )

        # Mock the database and creators
        mock_db = MagicMock()
        # Mock the database query for existing addresses
        mock_result = MagicMock()
        mock_result.first.return_value = [0]  # Return tuple with count=0
        mock_db.execute.return_value = mock_result
        mock_db.commit.return_value = None

        mock_org_creator = MagicMock()
        mock_location_creator = MagicMock()
        mock_service_creator = MagicMock()

        # Set up return values
        mock_org_creator.process_organization.return_value = (str(uuid4()), True)
        mock_location_creator.find_matching_location.return_value = None  # New location
        mock_location_creator.create_location.return_value = str(uuid4())
        mock_location_creator.create_address.return_value = None

        # Act
        with patch(
            "app.reconciler.job_processor.OrganizationCreator",
            return_value=mock_org_creator,
        ), patch(
            "app.reconciler.job_processor.LocationCreator",
            return_value=mock_location_creator,
        ), patch(
            "app.reconciler.job_processor.ServiceCreator",
            return_value=mock_service_creator,
        ):

            processor = JobProcessor(mock_db)
            processor.process_job_result(job_result)

        # Assert
        # Verify that create_address was called with the correct data
        mock_location_creator.create_address.assert_called_once()
        call_args = mock_location_creator.create_address.call_args[1]

        assert call_args["address_1"] == "123 Main St"
        assert call_args["city"] == "New York"
        assert call_args["state_province"] == "NY"
        assert call_args["postal_code"] == "10001"
        assert call_args["country"] == "US"
        assert call_args["address_type"] == "physical"

    def test_should_not_fail_when_addresss_field_missing(self):
        """Test that processing continues when 'addresss' field is missing."""
        # Arrange
        job_id = str(uuid4())
        job_data = {
            "organization": [
                {"name": "Test Food Bank", "description": "A test food bank"}
            ],
            "location": [
                {
                    "name": "Test Location",
                    "description": "Test location description",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    # No addresss field
                }
            ],
        }

        # Create LLMJob
        llm_job = LLMJob(
            id=job_id,
            prompt="Test prompt",
            raw_data=job_data,
            metadata={"scraper_id": "test_scraper"},
            created_at=datetime.now(),
        )

        # Create LLMResponse
        llm_response = LLMResponse(
            text=json.dumps(job_data),
            model="test-model",
            usage={"total_tokens": 100},
        )

        # Create JobResult
        job_result = JobResult(
            job_id=job_id,
            job=llm_job,
            status=JobStatus.COMPLETED,
            result=llm_response,
            completed_at=datetime.now(),
            processing_time=1.0,
        )

        # Mock the database and creators
        mock_db = MagicMock()
        mock_db.commit.return_value = None

        mock_org_creator = MagicMock()
        mock_location_creator = MagicMock()
        mock_service_creator = MagicMock()

        # Set up return values
        mock_org_creator.process_organization.return_value = (str(uuid4()), True)
        mock_location_creator.find_matching_location.return_value = None  # New location
        mock_location_creator.create_location.return_value = str(uuid4())

        # Act
        with patch(
            "app.reconciler.job_processor.OrganizationCreator",
            return_value=mock_org_creator,
        ), patch(
            "app.reconciler.job_processor.LocationCreator",
            return_value=mock_location_creator,
        ), patch(
            "app.reconciler.job_processor.ServiceCreator",
            return_value=mock_service_creator,
        ):

            processor = JobProcessor(mock_db)
            result = processor.process_job_result(job_result)

        # Assert
        # Verify that create_address was NOT called
        mock_location_creator.create_address.assert_not_called()

        # Verify that location was still created
        mock_location_creator.create_location.assert_called_once()

        # Verify the processing succeeded
        assert result["status"] == "success"

    def test_should_document_addresss_typo_in_type_hint(self):
        """Test that the LocationDict type properly documents the 'addresss' field."""
        from app.reconciler.job_processor import LocationDict

        # The type hint should include 'addresss' (with 3 s's)
        assert "addresss" in LocationDict.__annotations__
        # It should be a list of dictionaries
        # Note: The actual type check depends on Python version,
        # so we just verify the field exists
