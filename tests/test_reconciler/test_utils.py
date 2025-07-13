"""Tests for reconciler utilities."""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult, JobStatus, LLMJob, LLMResponse
from app.reconciler.utils import ReconcilerUtils


@pytest.fixture
def mock_db(mocker: MockerFixture) -> MagicMock:
    """Mock database session."""
    db = MagicMock(spec=Session)
    db.commit.return_value = None

    # Mock database result
    result = MagicMock()
    result.first.return_value = None
    db.execute.return_value = result

    return db


@pytest.fixture
def sample_job_result() -> JobResult:
    """Create sample job result with HSDS data."""
    job = LLMJob(
        id="test-job",
        prompt="test prompt",
        provider_config={},
        format={},
        metadata={"scraper_id": "test-scraper"},
        created_at=datetime.now(),
    )
    result = LLMResponse(
        text=json.dumps(
            {
                "organization": [
                    {
                        "name": "Example Organization Inc.",
                        "alternate_name": "Example Org",
                        "description": "Example Org is a non-profit organization dedicated to providing services to qualified beneficiaries",
                        "email": "email@example.com",
                        "website": "http://example.com",
                        "tax_status": "tax_status",
                        "year_incorporated": 2011,
                        "legal_status": "Limited Company",
                        "uri": "http://example.com",
                        "phones": [
                            {
                                "number": "+44 1234 234567",
                                "extension": 100,
                                "type": "voice",
                                "description": "Our main reception phone number",
                                "languages": [
                                    {
                                        "name": "Urdu",
                                        "code": "ur",
                                        "note": "Translation services available",
                                    }
                                ],
                            }
                        ],
                        "organization_identifiers": [
                            {
                                "identifier_scheme": "GB-COH",
                                "identifier_type": "Company number",
                                "identifier": "1234567",
                            }
                        ],
                    }
                ],
                "location": [
                    {
                        "name": "MyCity Civic Center",
                        "alternate_name": "Civic Center",
                        "description": "MyCity Civic Center is located on Main Street",
                        "location_type": "physical",
                        "transportation": "Bus and Metro access",
                        "latitude": 100,
                        "longitude": 101,
                        "addresses": [
                            {
                                "address_1": "1-30 Main Street",
                                "city": "MyCity",
                                "state_province": "MyState",
                                "postal_code": "ABC 1234",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "phones": [
                            {
                                "number": "+44 1234 234567",
                                "extension": 100,
                                "type": "voice",
                            }
                        ],
                        "schedules": [
                            {
                                "freq": "WEEKLY",
                                "wkst": "MO",
                                "opens_at": "09:00",
                                "closes_at": "17:00",
                                "byday": "MO,TU,WE,TH,FR",
                            }
                        ],
                        "accessibility": [
                            {
                                "description": "Wheelchair accessible",
                                "details": "Ramp at entrance",
                            }
                        ],
                    }
                ],
                "service": [
                    {
                        "name": "Community Counselling",
                        "alternate_name": "MyCity Counselling Services",
                        "description": "Counselling Services provided by trained professionals",
                        "status": "active",
                        "url": "http://example.com/counselling",
                        "email": "email@example.com",
                        "phones": [
                            {
                                "number": "+44 1234 234567",
                                "extension": 100,
                                "type": "voice",
                            }
                        ],
                        "schedules": [
                            {
                                "freq": "WEEKLY",
                                "wkst": "MO",
                                "opens_at": "09:00",
                                "closes_at": "17:00",
                                "byday": "MO,TU,WE,TH,FR",
                            }
                        ],
                        "languages": [{"name": "Urdu", "code": "ur"}],
                    }
                ],
            }
        ),
        model="test-model",
        usage={"total_tokens": 100},
        raw={},
    )
    return JobResult(
        job_id="test-job",
        job=job,
        status=JobStatus.COMPLETED,
        result=result,
        retry_count=0,
        error=None,
        completed_at=datetime.now(),
        processing_time=None,
        metadata={},
    )


def test_find_matching_location(mock_db: Session) -> None:
    """Test finding matching location by coordinates."""
    # Set up consistent UUID for testing
    location_id = "08565124-084b-45f9-8703-150f6348c5d5"

    # Create mock instance with pre-configured methods
    mock_creator_instance = MagicMock()
    mock_creator_instance.find_matching_location = MagicMock()
    mock_creator_instance.find_matching_location.side_effect = [location_id, None]

    # Mock LocationCreator class
    with patch(
        "app.reconciler.utils.LocationCreator", return_value=mock_creator_instance
    ):
        reconciler = ReconcilerUtils(mock_db)

        # Test finding a match
        result = reconciler.find_matching_location(40.7128, -74.0060, 0.0001)
        assert result == uuid.UUID(location_id)

        # Verify location creator was called
        mock_creator_instance.find_matching_location.assert_called_with(
            40.7128, -74.0060, 0.0001
        )

        # Test no match found
        result = reconciler.find_matching_location(40.7128, -74.0060, 0.0001)
        assert result is None


def test_create_location(mock_db: Session) -> None:
    """Test creating new location."""
    name = "Test Location"
    description = "Test Description"
    latitude = 40.7128
    longitude = -74.0060
    metadata = {"source": "test"}

    # Set up consistent UUID for testing
    location_id = "e60e5e23-ac2a-46ef-88ff-dabaa3c060cd"

    # Create mock instance with pre-configured methods
    mock_creator_instance = MagicMock()
    mock_creator_instance.create_location = MagicMock()
    mock_creator_instance.create_location.return_value = location_id

    # Mock LocationCreator class
    with patch(
        "app.reconciler.utils.LocationCreator", return_value=mock_creator_instance
    ):
        reconciler = ReconcilerUtils(mock_db)

        result = reconciler.create_location(
            name, description, latitude, longitude, metadata
        )

        assert result == uuid.UUID(location_id)
        mock_creator_instance.create_location.assert_called_once_with(
            name, description, latitude, longitude, metadata
        )


def test_create_service(mock_db: Session) -> None:
    """Test creating new service."""
    name = "Test Service"
    description = "Test Description"
    org_id = uuid.uuid4()
    metadata = {"source": "test"}

    # Set up consistent UUID for testing
    service_id = uuid.UUID("77050a02-a284-40c4-bbb6-d990120a7dd6")

    # Create mock instance with pre-configured methods
    mock_creator_instance = MagicMock()
    mock_creator_instance.create_service = MagicMock()
    mock_creator_instance.create_service.return_value = service_id

    # Mock ServiceCreator class
    with patch(
        "app.reconciler.utils.ServiceCreator", return_value=mock_creator_instance
    ):
        reconciler = ReconcilerUtils(mock_db)

        result = reconciler.create_service(name, description, org_id, metadata)

        assert result == service_id
        mock_creator_instance.create_service.assert_called_once_with(
            name, description, org_id, metadata
        )


def test_create_service_at_location(mock_db: Session) -> None:
    """Test creating new service at location."""
    service_id = uuid.uuid4()
    location_id = uuid.uuid4()
    description = "Test Description"
    metadata = {"source": "test"}

    # Set up consistent UUID for testing
    sal_id = uuid.UUID("6777ff92-c379-4e2c-9a6c-81648ad5e720")

    # Create mock instance with pre-configured methods
    mock_creator_instance = MagicMock()
    mock_creator_instance.create_service_at_location = MagicMock()
    mock_creator_instance.create_service_at_location.return_value = sal_id

    # Mock ServiceCreator class
    with patch(
        "app.reconciler.utils.ServiceCreator", return_value=mock_creator_instance
    ):
        reconciler = ReconcilerUtils(mock_db)

        result = reconciler.create_service_at_location(
            service_id, location_id, description, metadata
        )

        assert result == sal_id
        mock_creator_instance.create_service_at_location.assert_called_once_with(
            service_id, location_id, description, metadata
        )


def test_process_job_result(mock_db: Session, sample_job_result: JobResult) -> None:
    """Test processing job result with HSDS data."""
    # Create mock instance with pre-configured method
    mock_processor_instance = MagicMock()
    mock_processor_instance.process_job_result = MagicMock()
    mock_processor_instance.process_job_result.return_value = None

    # Mock JobProcessor class
    with patch(
        "app.reconciler.utils.JobProcessor", return_value=mock_processor_instance
    ):
        reconciler = ReconcilerUtils(mock_db)
        reconciler.process_job_result(sample_job_result)

        # Verify job processor was called
        assert mock_processor_instance.process_job_result.call_count == 1
        mock_processor_instance.process_job_result.assert_called_once_with(
            sample_job_result
        )


def test_process_completed_jobs(mock_db: Session, sample_job_result: JobResult) -> None:
    """Test processing completed jobs from queue."""
    # Create mock instance with pre-configured method
    mock_processor_instance = MagicMock()
    mock_processor_instance.process_completed_jobs = MagicMock()
    mock_processor_instance.process_completed_jobs.return_value = ["test-job"]

    # Mock JobProcessor class
    with patch(
        "app.reconciler.utils.JobProcessor", return_value=mock_processor_instance
    ):
        reconciler = ReconcilerUtils(mock_db)
        processed = reconciler.process_completed_jobs()

        assert len(processed) == 1
        assert processed[0] == "test-job"
        assert mock_processor_instance.process_completed_jobs.call_count == 1


def test_process_completed_jobs_error_handling(
    mock_db: Session, sample_job_result: JobResult
) -> None:
    """Test error handling in job processing."""
    # Create mock instance with pre-configured method
    mock_processor_instance = MagicMock()
    mock_processor_instance.process_completed_jobs = MagicMock()
    mock_processor_instance.process_completed_jobs.return_value = []

    # Mock JobProcessor class
    with patch(
        "app.reconciler.utils.JobProcessor", return_value=mock_processor_instance
    ):
        reconciler = ReconcilerUtils(mock_db)
        processed = reconciler.process_completed_jobs()

        assert len(processed) == 0  # No jobs should be marked as processed
        assert mock_processor_instance.process_completed_jobs.call_count == 1
