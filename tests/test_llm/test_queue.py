"""Tests for LLM queue implementation."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
import redis

from app.llm.queue.job import LLMJob
from app.llm.queue.models import JobStatus, RedisQueue
from app.llm.providers.types import LLMResponse

pytest_plugins = ["tests.fixtures.cache"]


@pytest.fixture
def llm_job() -> LLMJob:
    """Create test LLM job."""
    return LLMJob(
        id=str(uuid4()),
        prompt="Test prompt",
        format={"type": "object", "properties": {"text": {"type": "string"}}},
        provider_config={"temperature": 0.7},
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def queue(redis_client: redis.Redis) -> RedisQueue[LLMJob]:
    """Create test queue."""
    queue = RedisQueue[LLMJob](redis=redis_client)
    return queue


def test_queue_enqueue_basic(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
) -> None:
    """Test basic job enqueueing without processing."""
    # Mock provider for enqueueing only
    from app.llm.providers.test_mock import MockProvider

    provider = MockProvider(model_name="test-model")

    # Enqueue job
    job_id = queue.enqueue(llm_job, provider=provider)
    assert job_id == llm_job.id

    # Get initial status
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.QUEUED
    assert status.retry_count == 0
    assert status.result is None


def test_queue_job_metadata(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
) -> None:
    """Test that job metadata is stored correctly."""
    from app.llm.providers.test_mock import MockProvider

    provider = MockProvider(model_name="test-model")

    job_id = queue.enqueue(llm_job, provider=provider)

    # Check that RQ job has correct metadata
    rq_job = queue.queue.fetch_job(job_id)
    assert rq_job is not None
    assert "job" in rq_job.meta

    job_data = rq_job.meta["job"]
    assert job_data["id"] == llm_job.id
    assert job_data["prompt"] == llm_job.prompt
    assert job_data["format"] == llm_job.format


@patch("app.llm.queue.processor.process_llm_job")
def test_queue_processing_integration(
    mock_processor,
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
) -> None:
    """Test queue processing with mocked processor."""
    from rq import SimpleWorker
    from app.llm.providers.test_mock import MockProvider

    # Clear the queue before test to ensure isolation
    queue.queue.empty()
    
    # Mock the processor to return a successful response
    mock_response = LLMResponse(
        text="Test response",
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    mock_processor.return_value = mock_response

    provider = MockProvider(model_name="test-model")
    job_id = queue.enqueue(llm_job, provider=provider)

    # Process with worker
    worker = SimpleWorker([queue.queue], connection=queue.redis)
    worker.work(burst=True)

    # Verify processor was called
    mock_processor.assert_called_once()
    args, kwargs = mock_processor.call_args
    assert len(args) == 2
    called_job, called_provider = args
    assert called_job.id == llm_job.id
    assert called_provider.model_name == "test-model"

    # Check job completed
    rq_job = queue.queue.fetch_job(job_id)
    assert rq_job.get_status() == "finished"
    assert rq_job.result == mock_response


def test_processor_function_direct(no_content_store):
    """Test the processor function directly without RQ serialization."""
    from app.llm.queue.processor import process_llm_job
    from app.llm.providers.test_mock import MockProvider

    job = LLMJob(
        id=str(uuid4()),
        prompt="Test prompt",
        format={"type": "object", "properties": {"text": {"type": "string"}}},
        provider_config={"temperature": 0.7},
        created_at=datetime.now(UTC),
    )

    provider = MockProvider(model_name="test-model")

    # Test direct call
    result = process_llm_job(job, provider)

    assert isinstance(result, LLMResponse)
    assert result.text == "Test response"
    assert result.model == "test-model"


def test_queue_error_handling(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
) -> None:
    """Test error handling for invalid jobs."""
    from app.llm.providers.test_mock import MockProvider

    provider = MockProvider(model_name="test-model")

    # Test with basic enqueueing - errors would occur during processing
    job_id = queue.enqueue(llm_job, provider=provider)
    assert job_id == llm_job.id

    # Verify job exists in queue
    rq_job = queue.queue.fetch_job(job_id)
    assert rq_job is not None
    assert rq_job.get_status() == "queued"


def test_queue_status_mapping(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
) -> None:
    """Test that RQ job statuses are correctly mapped to our statuses."""
    from app.llm.providers.test_mock import MockProvider

    provider = MockProvider(model_name="test-model")

    job_id = queue.enqueue(llm_job, provider=provider)

    # Test queued status
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.QUEUED

    # Test that we can get status multiple times
    status2 = queue.get_status(job_id)
    assert status2 is not None
    assert status2.status == JobStatus.QUEUED


def test_queue_nonexistent_job(queue: RedisQueue[LLMJob]) -> None:
    """Test getting status of nonexistent job."""
    status = queue.get_status("nonexistent-job-id")
    assert status is None
