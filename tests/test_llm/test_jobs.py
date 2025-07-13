"""Tests for LLM job processing."""

import logging
from typing import Any, Dict
from uuid import uuid4

import pytest
from redis import Redis
from rq import SimpleWorker

# Job import removed - not used
from app.llm.jobs import JobProcessor
from app.llm.providers.base import BaseLLMProvider, BaseModelConfig
from app.llm.providers.types import GenerateConfig, LLMInput, LLMResponse
from app.llm.queue.models import JobStatus
from app.llm.queue.queues import llm_queue

pytest_plugins = ["tests.fixtures.cache"]

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
        logger.debug("MockProvider.generate called with prompt: %s", prompt)
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


def test_job_submission_and_retrieval(
    processor: JobProcessor,
    worker: SimpleWorker,
    job_request: Dict[str, Any],
) -> None:
    """Test submitting and retrieving a job."""
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
    assert result.status == JobStatus.COMPLETED
    assert result.result is not None
    assert result.result.text == "Test response"


def test_job_not_found(processor: JobProcessor) -> None:
    """Test retrieving non-existent job."""
    result = processor.get_result(str(uuid4()), wait=False)
    assert result is None


class ErrorProvider(MockProvider):
    """Provider that raises errors."""

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: Dict[str, Any] | None = None,
        **kwargs: Dict[str, Any],
    ) -> LLMResponse:
        """Mock generate method that raises an error."""
        raise ValueError("Test error")


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


def test_multiple_jobs(
    processor: JobProcessor,
    worker: SimpleWorker,
    job_request: Dict[str, Any],
) -> None:
    """Test processing multiple jobs."""
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
