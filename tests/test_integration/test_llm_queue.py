"""Integration tests for LLM queue system."""

import asyncio
import logging
from contextlib import contextmanager
from typing import Any

import pytest
from redis import Redis
from rq import Queue, SimpleWorker

from app.llm.config import LLMConfig
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig, LLMResponse
from app.llm.queue.queues import llm_queue, reconciler_queue, recorder_queue

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.integration]


@contextmanager
def patch_queues(redis: Redis):
    """Context manager to patch global queues with test Redis connection."""
    # Create test queues
    test_llm_queue = Queue("llm", connection=redis)
    test_reconciler_queue = Queue("reconciler", connection=redis)
    test_recorder_queue = Queue("recorder", connection=redis)

    # Monkey patch the global queues
    import app.llm.queue.queues as queues_module

    original_reconciler_queue = queues_module.reconciler_queue
    original_recorder_queue = queues_module.recorder_queue

    queues_module.reconciler_queue = test_reconciler_queue
    queues_module.recorder_queue = test_recorder_queue

    # Also update the global references in this module
    global reconciler_queue, recorder_queue
    original_local_reconciler = reconciler_queue
    original_local_recorder = recorder_queue
    reconciler_queue = test_reconciler_queue
    recorder_queue = test_recorder_queue

    try:
        yield test_llm_queue, test_reconciler_queue, test_recorder_queue
    finally:
        # Restore original queues
        queues_module.reconciler_queue = original_reconciler_queue
        queues_module.recorder_queue = original_recorder_queue
        reconciler_queue = original_local_reconciler
        recorder_queue = original_local_recorder


@pytest.fixture
def redis() -> Redis:
    """Create Redis connection."""
    redis = Redis.from_url(
        "redis://cache:6379",
        decode_responses=False,
    )
    # Verify Redis connection
    try:
        redis.ping()
        logger.info("Redis connection successful")
        # Clean up queues
        redis.delete("rq:queue:llm")
        redis.delete("rq:queue:reconciler")
        redis.delete("rq:queue:recorder")
        # Clean up jobs
        for key in redis.keys("rq:job:*"):
            redis.delete(key)
        logger.info("Queues and jobs cleaned")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise

    return redis


class MockProvider(BaseLLMProvider[Any, LLMConfig]):
    """Mock LLM provider for testing."""

    def __init__(self, config: LLMConfig, name: str = "mock") -> None:
        """Initialize provider."""
        self.config = config
        self.name = name

    @property
    def environment_key(self) -> str:
        """Get environment key."""
        return "MOCK_API_KEY"

    @property
    def model(self) -> Any:
        """Get model."""
        return None

    def _init_config(self, **kwargs: Any) -> LLMConfig:
        """Initialize provider configuration."""
        return self.config

    async def generate(
        self,
        prompt: str | list[dict[str, str]],
        config: GenerateConfig | None = None,
        format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate mock response."""
        response = {"text": "Test response", "data": {"test": "data"}}
        return LLMResponse(
            text=str(response),
            model=self.name,
            usage={"total_tokens": 10},
            parsed=response,
        )


def process_llm_job(
    prompt: str, format: dict[str, Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    """Process LLM job."""
    # Create mock provider
    config = LLMConfig(model_name="mock", temperature=0.7)
    provider = MockProvider(config)

    # Process with provider (run async in sync context)
    result = asyncio.run(provider.generate(prompt=prompt, format=format))

    # Return result with metadata for follow-up jobs
    return {
        "status": "completed",
        "result": result.model_dump(),
        "error": None,
        "follow_up_jobs": [
            {
                "queue": "reconciler",
                "job": "reconcile_data",
                "data": result.model_dump(),
            },
            {"queue": "recorder", "job": "record_result", "data": result.model_dump()},
        ],
    }


def test_job_lifecycle(redis: Redis) -> None:
    """Test complete job lifecycle."""
    with patch_queues(redis) as (
        test_llm_queue,
        test_reconciler_queue,
        test_recorder_queue,
    ):
        # Create test job
        job = test_llm_queue.enqueue(
            process_llm_job,
            args=(
                "Test prompt",
                {"type": "json"},
                {"scraper_id": "test"},
            ),
        )

        # Process job
        worker = SimpleWorker([test_llm_queue], connection=redis)
        worker.work(burst=True)

        # Check job status
        assert job.is_finished
        assert job.result is not None
        assert job.result["status"] == "completed"
        assert job.result["error"] is None

        # Check that follow-up job metadata is in the result
        follow_up_jobs = job.result.get("follow_up_jobs", [])
        assert len(follow_up_jobs) == 2

        # Verify follow-up job structure
        reconciler_follow_up = next(
            f for f in follow_up_jobs if f["queue"] == "reconciler"
        )
        recorder_follow_up = next(f for f in follow_up_jobs if f["queue"] == "recorder")

        assert reconciler_follow_up["job"] == "reconcile_data"
        assert recorder_follow_up["job"] == "record_result"
        assert "data" in reconciler_follow_up
        assert "data" in recorder_follow_up


def test_error_handling(redis: Redis) -> None:
    """Test error handling."""
    # Create invalid job (missing required args)
    job = llm_queue.enqueue(process_llm_job)

    # Process job
    worker = SimpleWorker([llm_queue], connection=redis)
    worker.work(burst=True)

    # Check job status
    assert job.is_failed
    assert job.exc_info is not None


def test_multiple_jobs(redis: Redis) -> None:
    """Test processing multiple jobs."""
    with patch_queues(redis) as (
        test_llm_queue,
        test_reconciler_queue,
        test_recorder_queue,
    ):
        # Create test jobs
        jobs = [
            test_llm_queue.enqueue(
                process_llm_job,
                args=(
                    f"Test prompt {i}",
                    {"type": "json"},
                    {"scraper_id": "test"},
                ),
            )
            for i in range(3)
        ]

        # Process jobs
        worker = SimpleWorker([test_llm_queue], connection=redis)
        worker.work(burst=True)

        # Check job statuses
        assert all(job.is_finished for job in jobs)
        assert all(job.result is not None for job in jobs)
        assert all(job.result["status"] == "completed" for job in jobs)

        # Check that all jobs have follow-up job metadata
        for job in jobs:
            follow_up_jobs = job.result.get("follow_up_jobs", [])
            assert len(follow_up_jobs) == 2
            assert any(f["queue"] == "reconciler" for f in follow_up_jobs)
            assert any(f["queue"] == "recorder" for f in follow_up_jobs)
