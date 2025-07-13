"""Tests for LLM queue implementation."""

from datetime import UTC, datetime
from typing import Any, Dict
from uuid import uuid4

import pytest
import redis
from rq import SimpleWorker

from app.llm.providers.base import BaseLLMProvider, BaseModelConfig
from app.llm.providers.types import GenerateConfig, LLMInput, LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.models import JobStatus, RedisQueue

pytest_plugins = ["tests.fixtures.cache"]


class MockConfig(BaseModelConfig):
    """Mock provider configuration."""

    pass


class MockProvider(BaseLLMProvider[Dict[str, Any], MockConfig]):
    """Mock LLM provider for testing."""

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: Dict[str, Any] | None = None,
        **kwargs: Dict[str, Any],
    ) -> LLMResponse:
        """Mock generate method."""
        return LLMResponse(
            text="Test response",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def _init_config(self, **kwargs: Dict[str, Any]) -> MockConfig:
        """Mock config initialization."""
        return MockConfig(
            context_length=1024,
            max_tokens=512,
            supports_structured=True,
        )

    @property
    def environment_key(self) -> str:
        """Mock environment key."""
        return "TEST_API_KEY"

    @property
    def model(self) -> Dict[str, Any]:
        """Mock model instance."""
        return {}


class ErrorProvider(MockProvider):
    """Mock provider that raises errors."""

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: Dict[str, Any] | None = None,
        **kwargs: Dict[str, Any],
    ) -> LLMResponse:
        """Mock generate method that raises an error."""
        raise ValueError("Test error")


@pytest.fixture
def provider() -> MockProvider:
    """Create test provider."""
    return MockProvider(model_name="test-model")


@pytest.fixture
def error_provider() -> ErrorProvider:
    """Create test error provider."""
    return ErrorProvider(model_name="test-model")


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


def test_queue_enqueue_and_process(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
    provider: MockProvider,
) -> None:
    """Test enqueueing and processing a job."""
    # Enqueue job
    job_id = queue.enqueue(llm_job, provider=provider)
    assert job_id == llm_job.id

    # Get initial status
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.QUEUED
    assert status.retry_count == 0

    # Process job with SimpleWorker
    worker = SimpleWorker([queue.queue], connection=queue.redis)
    worker.work(burst=True)  # Process all jobs and exit

    # Check final status
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.COMPLETED
    assert status.result is not None
    assert isinstance(status.result, LLMResponse)
    assert status.result.text == "Test response"


def test_queue_retry_handling(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
    provider: MockProvider,
) -> None:
    """Test job retry handling."""
    # Enqueue job
    job_id = queue.enqueue(llm_job, provider=provider)

    # Process job with SimpleWorker
    worker = SimpleWorker([queue.queue], connection=queue.redis)
    worker.work(burst=True)  # Process all jobs and exit

    # Check status
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.COMPLETED
    assert status.retry_count == 0


def test_worker_job_processing(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
    provider: MockProvider,
) -> None:
    """Test worker job processing."""
    # Enqueue job
    job_id = queue.enqueue(llm_job, provider=provider)

    # Process job with SimpleWorker
    worker = SimpleWorker([queue.queue], connection=queue.redis)
    worker.work(burst=True)  # Process all jobs and exit

    # Check final result
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.COMPLETED
    assert status.result is not None
    assert isinstance(status.result, LLMResponse)
    assert status.result.text == "Test response"


def test_worker_error_handling(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
    error_provider: ErrorProvider,
) -> None:
    """Test worker error handling."""
    # Create error worker
    worker = SimpleWorker(
        [queue.queue],
        connection=queue.redis,
    )

    # Enqueue job with error provider
    job_id = queue.enqueue(llm_job, provider=error_provider)

    # Process job
    worker.work(burst=True)  # Process all jobs and exit

    # Check result
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.FAILED
    assert "ValueError: Test error" in status.error


def test_queue_cleanup(
    queue: RedisQueue[LLMJob],
    llm_job: LLMJob,
    provider: MockProvider,
) -> None:
    """Test queue cleanup of old jobs."""
    # Enqueue job
    job_id = queue.enqueue(llm_job, provider=provider)

    # Process job with SimpleWorker
    worker = SimpleWorker([queue.queue], connection=queue.redis)
    worker.work(burst=True)  # Process all jobs and exit

    # Check result exists
    status = queue.get_status(job_id)
    assert status is not None
    assert status.status == JobStatus.COMPLETED

    # Force cleanup of job
    queue.redis.delete(f"rq:job:{job_id}")

    # Verify cleanup
    status = queue.get_status(job_id)
    assert status is None  # Result should be gone
