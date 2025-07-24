"""Tests for LLM job processing."""

import logging
from typing import Any, Dict
from uuid import uuid4

import pytest
from redis import Redis
from rq import SimpleWorker

# Job import removed - not used
from app.llm.jobs import JobProcessor
from app.llm.providers.test_mock import MockProvider, ErrorProvider
from app.llm.queue.models import JobStatus
from app.llm.queue.queues import llm_queue

pytest_plugins = ["tests.fixtures.cache"]

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.fixture
def processor(redis_client: Redis) -> JobProcessor:
    """Create test job processor."""
    logger.debug("Creating JobProcessor")
    processor = JobProcessor(
        redis=redis_client,
        provider=MockProvider(model_name="test-model"),
    )
    return processor


@pytest.fixture
def worker(redis_client: Redis) -> SimpleWorker:
    """Create test worker."""
    import sys
    import os

    # Ensure current directory is in path for RQ worker subprocess
    current_dir = os.getcwd()
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    # Create worker with queue
    worker = SimpleWorker(
        queues=[llm_queue],
        connection=redis_client,
    )
    return worker


@pytest.fixture
def job_request() -> Dict[str, Any]:
    """Create test job request."""
    return {
        "prompt": "Test prompt",
        "provider_config": {"temperature": 0.7},
        "format": {"type": "object", "properties": {"text": {"type": "string"}}},
    }


@pytest.mark.integration
@pytest.mark.xfail(
    reason="RQ worker subprocess cannot import test_mock module due to path issues"
)
def test_job_submission_and_retrieval(
    processor: JobProcessor,
    worker: SimpleWorker,
    job_request: Dict[str, Any],
) -> None:
    """Test submitting and retrieving a job (integration test)."""
    # Enqueue job
    logger.debug("Enqueueing job")
    job_id = processor.enqueue(**job_request)
    assert job_id is not None
    logger.debug("Job enqueued with ID: %s", job_id)

    # Process job
    worker.work(burst=True)

    # Get result
    result = processor.get_result(job_id)
    assert result is not None
    if result.status == JobStatus.FAILED:
        print(f"Job failed with error: {result.error}")
    assert result.status == JobStatus.COMPLETED
    assert result.result is not None
    assert result.result.text == "Test response"


def test_job_submission_unit(
    processor: JobProcessor,
    job_request: Dict[str, Any],
) -> None:
    """Test job submission without processing (unit test)."""
    # Enqueue job
    job_id = processor.enqueue(**job_request)
    assert job_id is not None

    # Check that job was queued
    result = processor.get_result(job_id, wait=False)
    assert result is not None
    assert result.status == JobStatus.QUEUED


def test_job_not_found(processor: JobProcessor) -> None:
    """Test retrieving non-existent job."""
    result = processor.get_result(str(uuid4()), wait=False)
    assert result is None


@pytest.mark.xfail(
    reason="RQ worker subprocess cannot import test_mock module due to path issues"
)
def test_job_failure(
    processor: JobProcessor,
    worker: SimpleWorker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handling failed jobs."""
    # Create new processor with error provider
    error_processor = JobProcessor(
        redis=processor.redis,
        provider=ErrorProvider(model_name="test-model"),
    )

    # Enqueue job with error provider
    logger.debug("Enqueueing job expected to fail")
    job_id = error_processor.enqueue("Test prompt")
    assert job_id is not None
    logger.debug("Failing job enqueued with ID: %s", job_id)

    # Process job
    worker.work(burst=True)

    # Get result
    result = processor.get_result(job_id)
    assert result is not None
    assert result.status == JobStatus.FAILED
    assert result.error is not None


@pytest.mark.integration
@pytest.mark.xfail(
    reason="RQ worker subprocess cannot import test_mock module due to path issues"
)
def test_multiple_jobs(
    processor: JobProcessor,
    worker: SimpleWorker,
    job_request: Dict[str, Any],
) -> None:
    """Test processing multiple jobs (integration test)."""
    # Submit multiple jobs
    logger.debug("Submitting multiple jobs")
    job_ids = [processor.enqueue(**job_request) for _ in range(4)]
    logger.debug("Submitted jobs with IDs: %s", job_ids)

    # Process all jobs
    worker.work(burst=True)

    # Get results for all jobs
    results = [processor.get_result(job_id) for job_id in job_ids]
    logger.debug("Got results for multiple jobs: %s", results)

    # Verify all jobs completed successfully
    assert all(result is not None for result in results)
    assert all(result.status == JobStatus.COMPLETED for result in results if result)
    assert all(
        result.result is not None and result.result.text == "Test response"
        for result in results
        if result
    )


def test_multiple_jobs_queuing(
    processor: JobProcessor,
    job_request: Dict[str, Any],
) -> None:
    """Test queuing multiple jobs without processing (unit test)."""
    # Submit multiple jobs
    job_ids = [processor.enqueue(**job_request) for _ in range(3)]

    # Verify all jobs were queued
    assert len(job_ids) == 3
    assert all(job_id is not None for job_id in job_ids)

    # Check that all jobs are in queued state
    results = [processor.get_result(job_id, wait=False) for job_id in job_ids]
    assert all(result is not None for result in results)
    assert all(result.status == JobStatus.QUEUED for result in results)
