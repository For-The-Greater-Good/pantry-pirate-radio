"""RQ worker implementation."""

import asyncio
import logging
import os
from typing import Any, Generic, TypeVar

import redis
from rq.defaults import DEFAULT_RESULT_TTL, DEFAULT_WORKER_TTL
from rq.worker import Worker

from app.llm.providers.base import BaseLLMProvider
from app.llm.queue.queues import llm_queue

T = TypeVar("T")

logger = logging.getLogger(__name__)


class QueueWorker(Generic[T]):
    """Worker for processing LLM jobs."""

    def __init__(
        self,
        provider: BaseLLMProvider[Any, Any],
        redis: redis.Redis | redis.asyncio.Redis | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Initialize worker.

        Args:
            provider: LLM provider instance
            redis: Optional Redis client (not used with RQ)
            worker_id: Optional worker ID (default: auto-generated)
        """
        self.provider = provider
        self.redis = redis
        self.worker_id = worker_id
        self.worker = Worker(
            [llm_queue],
            connection=llm_queue.connection,
            name=worker_id,
            default_result_ttl=DEFAULT_RESULT_TTL,
            default_worker_ttl=DEFAULT_WORKER_TTL,
            prepare_for_work=False,  # Don't try to set client name
            job_monitoring_interval=1,  # Check jobs more frequently
        )
        # Set worker PID
        self.worker.pid = os.getpid()

    async def setup(self) -> None:
        """Initialize worker."""
        pass  # No setup needed for RQ

    async def run(self) -> None:
        """Run worker loop."""
        # Register worker
        self.worker.register_birth()
        try:
            # Process jobs in test mode
            # Run in a separate thread to not block the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._work)
        finally:
            try:
                self.worker.register_death()
            except Exception as e:
                logger.warning(f"Error registering worker death: {e}")

    def _work(self) -> None:
        """Internal method to run the worker in a separate thread."""
        self.worker.work(
            burst=True,  # Run in burst mode for tests
            max_jobs=1,  # Process one job at a time
        )

    async def stop(self) -> None:
        """Stop worker gracefully."""
        try:
            self.worker.register_death()
        except Exception as e:
            logger.warning(f"Error registering worker death: {e}")
