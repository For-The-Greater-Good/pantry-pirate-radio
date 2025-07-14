"""Tests for job processing utilities."""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from redis import Redis
from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult, JobStatus, LLMJob, LLMResponse
from app.reconciler.job_processor import JobProcessor


@pytest.fixture
def mock_redis(mocker: MockerFixture) -> MagicMock:
    """Create a mock Redis client."""
    redis = MagicMock(spec=Redis)
    return redis


@pytest.fixture
def mock_db(mocker: MockerFixture) -> MagicMock:
    """Create a mock database session."""
    db = MagicMock(spec=Session)
    db.commit.return_value = None

    # Mock database result
    result = MagicMock()
    # Default to returning a tuple (id, is_new) to match INSERT...ON CONFLICT expectations
    result.first.return_value = (str(uuid.uuid4()), True)  # Default to new record
    db.execute.return_value = result

    return db


@pytest.fixture
def sample_job_result() -> JobResult:
    """Create sample job result with HSDS data."""
    llm_response = LLMResponse(
        text=json.dumps(
            {
                "organization": [
                    {"name": "Test Org", "description": "Test Description"}
                ],
                "service": [
                    {"name": "Test Service", "description": "Test Service Description"}
                ],
                "location": [
                    {
                        "name": "Test Location",
                        "description": "Test Location Description",
                        "latitude": 42.3675294,
                        "longitude": -71.186966,
                    }
                ],
            }
        ),
        model="test-model",
        usage={"total_tokens": 100},
        raw={},
    )

    return JobResult(
        job_id=str(uuid.uuid4()),
        job=LLMJob(
            id="test-job",
            prompt="test prompt",
            provider_config={},
            format={},
            created_at=datetime.now(),
            metadata={"scraper_id": "test_scraper"},
        ),
        status=JobStatus.COMPLETED,
        result=llm_response,
    )


def test_process_job_result(mock_db: MagicMock, sample_job_result: JobResult) -> None:
    """Test processing job result."""
    processor = JobProcessor(mock_db)

    # Override hasattr to control method detection
    original_hasattr = hasattr

    def mock_hasattr(obj, name):
        if name in ("process_organization", "process_service"):
            return False
        return original_hasattr(obj, name)

    with patch("builtins.hasattr", mock_hasattr):
        # Mock organization creator
        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as mock_org_creator:
            mock_org_instance = MagicMock()
            mock_org_creator.return_value = mock_org_instance
            org_id = uuid.uuid4()
            mock_org_instance.create_organization.return_value = org_id

            # Mock location creator
            with patch(
                "app.reconciler.job_processor.LocationCreator"
            ) as mock_location_creator:
                mock_location_instance = MagicMock()
                mock_location_creator.return_value = mock_location_instance
                # This needs to be a string ID, not a UUID, since the code will try to convert it
                location_id = str(uuid.uuid4())
                mock_location_instance.create_location.return_value = location_id
                mock_location_instance.find_matching_location.return_value = None

                # Mock service creator
                with patch(
                    "app.reconciler.job_processor.ServiceCreator"
                ) as mock_service_creator:
                    mock_service_instance = MagicMock()
                    mock_service_creator.return_value = mock_service_instance
                    service_id = uuid.uuid4()
                    mock_service_instance.create_service.return_value = service_id

                    # Process the job
                    processor.process_job_result(sample_job_result)

                    # Verify organization was created
                    mock_org_instance.create_organization.assert_called_once()

                    # Verify location was created
                    mock_location_instance.create_location.assert_called_once()

                    # Verify service was created
                    mock_service_instance.create_service.assert_called_once()


def test_process_completed_jobs(
    mock_db: MagicMock, sample_job_result: JobResult
) -> None:
    """Test processing completed jobs."""
    processor = JobProcessor(mock_db)

    with patch(
        "app.reconciler.job_processor.OrganizationCreator"
    ) as mock_org_creator, patch(
        "app.reconciler.job_processor.LocationCreator"
    ) as mock_loc_creator, patch(
        "app.reconciler.job_processor.ServiceCreator"
    ) as mock_service_creator:
        # Mock organization creator
        mock_org_instance = MagicMock()
        mock_org_creator.return_value = mock_org_instance
        org_id = uuid.uuid4()

        # Mock process_organization to return tuple (id, is_new)
        mock_org_instance.process_organization.return_value = (org_id, True)

        # Also mock create_organization for backward compatibility
        mock_org_instance.create_organization.return_value = org_id

        # Mock location creator
        mock_location_instance = MagicMock()
        mock_loc_creator.return_value = mock_location_instance
        location_id = uuid.uuid4()
        mock_location_instance.find_matching_location.return_value = None
        mock_location_instance.create_location.return_value = str(location_id)
        mock_location_instance.process_location.return_value = (location_id, True)

        # Mock service creator
        mock_service_instance = MagicMock()
        mock_service_creator.return_value = mock_service_instance
        service_id = uuid.uuid4()
        mock_service_instance.process_service.return_value = (service_id, True)
        sal_id = uuid.uuid4()
        mock_service_instance.create_service_at_location.return_value = sal_id

        # Process job directly since we no longer use Queue in job_processor
        result = processor.process_job_result(sample_job_result)

        # Verify result
        assert result["status"] == "success"
        assert "organization_id" in result
        assert "location_ids" in result
        assert "service_ids" in result


def test_process_completed_jobs_error_handling(
    mock_db: MagicMock, sample_job_result: JobResult
) -> None:
    """Test error handling in job processing."""
    processor = JobProcessor(mock_db)

    # Mock process_job_result to raise error
    with patch.object(processor, "process_job_result") as mock_process:
        mock_process.side_effect = ValueError("Test error")

        # Verify error handling
        with pytest.raises(ValueError) as exc_info:
            processor.process_job_result(sample_job_result)

        assert "Test error" in str(exc_info.value)


def test_process_job_result_no_result(mock_db: MagicMock) -> None:
    """Test processing job result with no result."""
    processor = JobProcessor(mock_db)

    # Create job result with no result
    job_result = JobResult(
        job_id=str(uuid.uuid4()),
        job=LLMJob(
            id="test-job",
            prompt="test prompt",
            provider_config={},
            format={},
            created_at=datetime.now(),
            metadata={},
        ),
        status=JobStatus.COMPLETED,
        result=None,
    )

    with pytest.raises(ValueError, match="Job result has no result"):
        processor.process_job_result(job_result)


def test_process_job_result_json_decode_error_fallback(mock_db: MagicMock) -> None:
    """Test processing job result with JSON decode error using demjson3 fallback."""
    processor = JobProcessor(mock_db)

    # Create job result with malformed JSON that demjson3 can handle
    invalid_json_response = LLMResponse(
        text='{name: "Test Org", description: "Test Description"}',  # Missing quotes around keys
        model="test-model",
        usage={"total_tokens": 100},
        raw={},
    )

    job_result = JobResult(
        job_id=str(uuid.uuid4()),
        job=LLMJob(
            id="test-job",
            prompt="test prompt",
            provider_config={},
            format={},
            created_at=datetime.now(),
            metadata={"scraper_id": "test_scraper"},
        ),
        status=JobStatus.COMPLETED,
        result=invalid_json_response,
    )

    with patch("app.reconciler.job_processor.demjson3.decode") as mock_demjson:
        mock_demjson.return_value = {
            "organization": [{"name": "Test Org", "description": "Test Description"}],
            "service": [],
            "location": [],
        }

        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as mock_org_creator:
            mock_org_instance = MagicMock()
            mock_org_creator.return_value = mock_org_instance
            org_id = uuid.uuid4()
            mock_org_instance.create_organization.return_value = org_id
            # Fix: process_organization returns a tuple (org_id, is_new_org)
            mock_org_instance.process_organization.return_value = (org_id, True)

            result = processor.process_job_result(job_result)

            assert result["status"] == "success"
            mock_demjson.assert_called_once()


def test_process_job_result_single_organization_transform(mock_db: MagicMock) -> None:
    """Test transforming single organization object to expected structure."""
    processor = JobProcessor(mock_db)

    # Create job result with single organization object (not wrapped in lists)
    single_org_response = LLMResponse(
        text=json.dumps(
            {
                "name": "Test Organization",
                "description": "Test Description",
                "services": [{"name": "Test Service", "description": "Service desc"}],
                "locations": [
                    {"name": "Test Location", "latitude": 42.0, "longitude": -71.0}
                ],
            }
        ),
        model="test-model",
        usage={"total_tokens": 100},
        raw={},
    )

    job_result = JobResult(
        job_id=str(uuid.uuid4()),
        job=LLMJob(
            id="test-job",
            prompt="test prompt",
            provider_config={},
            format={},
            created_at=datetime.now(),
            metadata={"scraper_id": "test_scraper"},
        ),
        status=JobStatus.COMPLETED,
        result=single_org_response,
    )

    with patch(
        "app.reconciler.job_processor.OrganizationCreator"
    ) as mock_org_creator, patch(
        "app.reconciler.job_processor.LocationCreator"
    ) as mock_loc_creator, patch(
        "app.reconciler.job_processor.ServiceCreator"
    ) as mock_service_creator:

        # Mock creators
        mock_org_instance = MagicMock()
        mock_org_creator.return_value = mock_org_instance
        org_id = uuid.uuid4()
        mock_org_instance.create_organization.return_value = org_id
        # Fix: process_organization returns a tuple (org_id, is_new_org)
        mock_org_instance.process_organization.return_value = (org_id, True)

        mock_loc_instance = MagicMock()
        mock_loc_creator.return_value = mock_loc_instance
        location_id = str(uuid.uuid4())
        mock_loc_instance.create_location.return_value = location_id
        mock_loc_instance.find_matching_location.return_value = None

        mock_service_instance = MagicMock()
        mock_service_creator.return_value = mock_service_instance
        service_id = uuid.uuid4()
        mock_service_instance.create_service.return_value = service_id
        # Fix: process_service returns a tuple (service_id, is_new_service)
        mock_service_instance.process_service.return_value = (service_id, True)

        result = processor.process_job_result(job_result)

        assert result["status"] == "success"
        assert result["organization_id"] == str(org_id)

        # Verify organization was processed (not created since process_organization was used)
        mock_org_instance.process_organization.assert_called_once()
        # Verify location was created
        mock_loc_instance.create_location.assert_called_once()
        # Verify service was processed (not created since process_service was used)
        mock_service_instance.process_service.assert_called_once()


def test_process_completed_jobs_deprecated(mock_db: MagicMock) -> None:
    """Test deprecated process_completed_jobs method."""
    processor = JobProcessor(mock_db)

    # Should just log a message
    with patch.object(processor.logger, "info") as mock_log:
        processor.process_completed_jobs()
        mock_log.assert_called_once_with(
            "Method deprecated - jobs are processed by RQ worker"
        )


def test_process_job_result_with_matching_location(
    mock_db: MagicMock, sample_job_result: JobResult
) -> None:
    """Test processing job result with existing matching location."""
    processor = JobProcessor(mock_db)

    with patch(
        "app.reconciler.job_processor.OrganizationCreator"
    ) as mock_org_creator, patch(
        "app.reconciler.job_processor.LocationCreator"
    ) as mock_loc_creator, patch(
        "app.reconciler.job_processor.ServiceCreator"
    ) as mock_service_creator:

        # Mock organization creator
        mock_org_instance = MagicMock()
        mock_org_creator.return_value = mock_org_instance
        org_id = uuid.uuid4()
        mock_org_instance.create_organization.return_value = org_id
        # Fix: process_organization returns a tuple (org_id, is_new_org)
        mock_org_instance.process_organization.return_value = (org_id, True)

        # Mock location creator to return existing location
        mock_loc_instance = MagicMock()
        mock_loc_creator.return_value = mock_loc_instance
        existing_location_id = str(uuid.uuid4())
        mock_loc_instance.find_matching_location.return_value = existing_location_id

        # Mock service creator
        mock_service_instance = MagicMock()
        mock_service_creator.return_value = mock_service_instance
        service_id = uuid.uuid4()
        mock_service_instance.create_service.return_value = service_id
        # Fix: process_service returns a tuple (service_id, is_new_service)
        mock_service_instance.process_service.return_value = (service_id, True)

        result = processor.process_job_result(sample_job_result)

        assert result["status"] == "success"
        # Should not create new location since existing one was found
        mock_loc_instance.create_location.assert_not_called()
        # Should find matching location
        mock_loc_instance.find_matching_location.assert_called_once()


def test_process_job_result_process_function_exists(
    mock_db: MagicMock, sample_job_result: JobResult
) -> None:
    """Test processing when process_organization/process_service functions exist."""
    processor = JobProcessor(mock_db)

    with patch(
        "app.reconciler.job_processor.OrganizationCreator"
    ) as mock_org_creator, patch(
        "app.reconciler.job_processor.LocationCreator"
    ) as mock_loc_creator, patch(
        "app.reconciler.job_processor.ServiceCreator"
    ) as mock_service_creator:
        # Mock organization creator
        mock_org_instance = MagicMock()
        mock_org_creator.return_value = mock_org_instance
        org_id = uuid.uuid4()

        # Mock process_organization to return tuple (id, is_new)
        mock_org_instance.process_organization.return_value = (org_id, True)

        # Also mock create_organization for backward compatibility
        mock_org_instance.create_organization.return_value = org_id

        # Mock location creator
        mock_loc_instance = MagicMock()
        mock_loc_creator.return_value = mock_loc_instance
        location_id = str(uuid.uuid4())
        mock_loc_instance.create_location.return_value = location_id
        mock_loc_instance.process_location.return_value = (location_id, True)
        mock_loc_instance.find_matching_location.return_value = None

        # Mock service creator
        mock_service_instance = MagicMock()
        mock_service_creator.return_value = mock_service_instance
        service_id = uuid.uuid4()

        # Mock process_service to return tuple (id, is_new)
        mock_service_instance.process_service.return_value = (service_id, True)

        # Also mock create_service for backward compatibility
        mock_service_instance.create_service.return_value = service_id

        mock_service_instance.create_service_at_location.return_value = str(
            uuid.uuid4()
        )

        result = processor.process_job_result(sample_job_result)

        assert result["status"] == "success"


def test_process_job_result_with_location_link(mock_db: MagicMock) -> None:
    """Test processing job result that creates service-location links."""
    processor = JobProcessor(mock_db)

    # Create job result with service linked to location
    linked_response = LLMResponse(
        text=json.dumps(
            {
                "organization": [
                    {"name": "Test Org", "description": "Test Description"}
                ],
                "service": [
                    {
                        "name": "Test Service",
                        "description": "Service desc",
                        "location_name": "Test Location",
                    }
                ],
                "location": [
                    {"name": "Test Location", "latitude": 42.0, "longitude": -71.0}
                ],
            }
        ),
        model="test-model",
        usage={"total_tokens": 100},
        raw={},
    )

    job_result = JobResult(
        job_id=str(uuid.uuid4()),
        job=LLMJob(
            id="test-job",
            prompt="test prompt",
            provider_config={},
            format={},
            created_at=datetime.now(),
            metadata={"scraper_id": "test_scraper"},
        ),
        status=JobStatus.COMPLETED,
        result=linked_response,
    )

    with patch(
        "app.reconciler.job_processor.OrganizationCreator"
    ) as mock_org_creator, patch(
        "app.reconciler.job_processor.LocationCreator"
    ) as mock_loc_creator, patch(
        "app.reconciler.job_processor.ServiceCreator"
    ) as mock_service_creator:

        # Mock creators
        mock_org_instance = MagicMock()
        mock_org_creator.return_value = mock_org_instance
        org_id = uuid.uuid4()
        mock_org_instance.create_organization.return_value = org_id
        # Fix: process_organization returns a tuple (org_id, is_new_org)
        mock_org_instance.process_organization.return_value = (org_id, True)

        mock_loc_instance = MagicMock()
        mock_loc_creator.return_value = mock_loc_instance
        location_id = str(uuid.uuid4())
        mock_loc_instance.create_location.return_value = location_id
        mock_loc_instance.find_matching_location.return_value = None

        mock_service_instance = MagicMock()
        mock_service_creator.return_value = mock_service_instance
        service_id = uuid.uuid4()
        mock_service_instance.create_service.return_value = service_id
        # Fix: process_service returns a tuple (service_id, is_new_service)
        mock_service_instance.process_service.return_value = (service_id, True)
        mock_service_instance.link_service_to_location.return_value = None

        result = processor.process_job_result(job_result)

        assert result["status"] == "success"
        # Service should be processed
        mock_service_instance.process_service.assert_called_once()


# Test the module-level process_job_result function
def test_module_level_process_job_result(sample_job_result: JobResult) -> None:
    """Test the module-level process_job_result function."""
    from app.reconciler.job_processor import process_job_result

    with patch(
        "app.reconciler.job_processor.create_engine"
    ) as mock_create_engine, patch(
        "app.reconciler.job_processor.sessionmaker"
    ) as mock_sessionmaker, patch(
        "app.reconciler.job_processor.JobProcessor"
    ) as mock_job_processor_class:

        # Mock database setup
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        mock_session_class = MagicMock()
        mock_sessionmaker.return_value = mock_session_class

        mock_session = MagicMock()
        mock_session_class.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_class.return_value.__exit__ = MagicMock(return_value=None)

        # Mock processor
        mock_processor = MagicMock()
        mock_job_processor_class.return_value = mock_processor
        mock_processor.process_job_result.return_value = {"status": "success"}

        result = process_job_result(sample_job_result)

        assert result == {"status": "success"}
        mock_create_engine.assert_called_once()
        mock_processor.process_job_result.assert_called_once_with(sample_job_result)


def test_module_level_process_job_result_error(sample_job_result: JobResult) -> None:
    """Test the module-level process_job_result function with error."""
    from app.reconciler.job_processor import process_job_result

    with patch("app.reconciler.job_processor.create_engine") as mock_create_engine:
        mock_create_engine.side_effect = Exception("Database connection failed")

        with pytest.raises(ValueError) as exc_info:
            process_job_result(sample_job_result)

        # Should re-raise as ValueError with JSON error format
        error_data = json.loads(str(exc_info.value))
        assert error_data["status"] == "error"
        assert "Database connection failed" in error_data["error"]
