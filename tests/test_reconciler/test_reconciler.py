"""Tests for main reconciler functionality."""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult, JobStatus, LLMJob, LLMResponse
from app.reconciler.reconciler import Reconciler


@pytest.fixture
def mock_db(mocker: MockerFixture) -> MagicMock:
    """Create a mock database session."""
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


def test_reconcile_data(mock_db: MagicMock, sample_job_result: JobResult) -> None:
    """Test reconciling data."""
    reconciler = Reconciler(mock_db)

    # Mock job processor
    with patch.object(reconciler.job_processor, "process_job_result") as mock_process:
        mock_process.return_value = None

        # Process data
        reconciler.reconcile_data(sample_job_result)

        # Verify job was processed
        mock_process.assert_called_once_with(sample_job_result)


def test_error_handling(mock_db: MagicMock, sample_job_result: JobResult) -> None:
    """Test error handling."""
    reconciler = Reconciler(mock_db)

    # Mock job processor to raise error
    with patch.object(reconciler.job_processor, "process_job_result") as mock_process:
        mock_process.side_effect = ValueError("Test error")

        # Process data
        with pytest.raises(ValueError, match="Test error"):
            reconciler.reconcile_data(sample_job_result)


def test_multiple_jobs(mock_db: MagicMock) -> None:
    """Test processing multiple jobs."""
    reconciler = Reconciler(mock_db)

    # Mock job processor
    with patch.object(
        reconciler.job_processor, "process_completed_jobs"
    ) as mock_process:
        mock_process.return_value = ["job1", "job2", "job3"]

        # Process jobs
        processed = reconciler.process_completed_jobs()

        # Verify jobs were processed
        assert len(processed) == 3
        mock_process.assert_called_once()
