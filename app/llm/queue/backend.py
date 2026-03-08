"""Queue backend abstraction for pluggable queue implementations.

This module provides a protocol for queue backends, enabling swapping between
Redis/RQ (development/local) and AWS SQS (production) backends.

Usage:
    from app.llm.queue.backend import get_queue_backend

    backend = get_queue_backend()
    job_id = backend.enqueue(job, provider=provider)
    status = backend.get_status(job_id)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable

import structlog

from app.llm.providers.base import BaseLLMProvider
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus

if TYPE_CHECKING:
    import redis
    from rq import Queue

logger = structlog.get_logger(__name__)

# Global singleton state
_queue_backend_instance: Optional[QueueBackend] = None
_queue_backend_initialized = False


@runtime_checkable
class QueueBackend(Protocol):
    """Protocol for queue backend implementations.

    Queue backends handle job enqueueing and status tracking for the LLM
    processing pipeline. Implementations may use Redis/RQ, AWS SQS, or
    other queuing systems.
    """

    @property
    def queue_name(self) -> str:
        """Name of the queue."""
        ...

    def setup(self) -> None:
        """Initialize the backend and verify connectivity.

        Raises:
            ConnectionError: If unable to connect to queue service.
        """
        ...

    def enqueue(
        self,
        job: LLMJob,
        provider: BaseLLMProvider[Any, Any] | None = None,
    ) -> str:
        """Enqueue a job for processing.

        Note:
            The SQS backend serializes provider_config differently from the
            Redis backend. SQS extracts only model_name into the message body
            for SQS message format compatibility, while Redis passes the full
            provider object to the RQ worker. This is intentional and each
            backend's workers know how to reconstruct the provider from their
            respective formats.

        Args:
            job: The LLM job to enqueue
            provider: Optional LLM provider for processing

        Returns:
            Job ID for tracking
        """
        ...

    def get_status(self, job_id: str) -> JobResult | None:
        """Get the status of a job.

        Args:
            job_id: ID of the job to check

        Returns:
            JobResult if job exists, None otherwise
        """
        ...


class RedisQueueBackend:
    """Redis/RQ-based queue backend implementation.

    Uses RQ (Redis Queue) for job management, suitable for local
    development and single-node deployments.

    Args:
        redis_client: Redis client connection
        queue_name: Name of the queue (default: "llm")
        result_ttl: TTL for job results in seconds
        failure_ttl: TTL for failed jobs in seconds
        max_retries: Maximum retry attempts per job
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        queue_name: str = "llm",
        result_ttl: int | None = None,
        failure_ttl: int | None = None,
        max_retries: int = 3,
    ) -> None:
        """Initialize RedisQueueBackend."""
        from app.core.config import settings

        self.redis_client = redis_client
        self._queue_name = queue_name
        self.result_ttl = result_ttl or settings.REDIS_TTL_SECONDS
        self.failure_ttl = failure_ttl or settings.REDIS_TTL_SECONDS
        self.max_retries = max_retries
        self._queue: Queue | None = None
        self._initialized = False

    @property
    def queue_name(self) -> str:
        """Name of the queue."""
        return self._queue_name

    @property
    def queue(self) -> Queue:
        """Get the RQ Queue instance."""
        if self._queue is None:
            from rq import Queue as _Queue

            self._queue = _Queue(self._queue_name, connection=self.redis_client)
        return self._queue

    def setup(self) -> None:
        """Initialize backend and verify Redis connectivity.

        Raises:
            ConnectionError: If Redis connection fails.
        """
        import redis as _redis

        if self._initialized:
            return

        try:
            self.redis_client.ping()
            logger.info(
                "redis_queue_backend_connected",
                queue_name=self._queue_name,
            )
            self._initialized = True
        except _redis.ConnectionError as e:
            logger.error(
                "redis_queue_backend_connection_failed",
                queue_name=self._queue_name,
                error=str(e),
            )
            raise ConnectionError(f"Failed to connect to Redis: {e}") from e

    def enqueue(
        self,
        job: LLMJob,
        provider: BaseLLMProvider[Any, Any] | None = None,
    ) -> str:
        """Enqueue a job for processing.

        Args:
            job: The LLM job to enqueue
            provider: LLM provider for processing

        Returns:
            Job ID for tracking
        """
        rq_job = self.queue.enqueue_call(
            func="app.llm.queue.processor.process_llm_job",
            args=(job, provider),
            job_id=job.id,
            meta={"job": job.model_dump()},
            result_ttl=self.result_ttl,
            failure_ttl=self.failure_ttl,
        )
        return str(rq_job.id)

    def get_status(self, job_id: str) -> JobResult | None:
        """Get the status of a job.

        Args:
            job_id: ID of the job to check

        Returns:
            JobResult if job exists, None otherwise
        """
        rq_job = self.queue.fetch_job(job_id)
        if not rq_job:
            return None

        # Get job data from meta
        job_data = rq_job.meta.get("job", {})
        if not job_data:
            return None

        # Create base job
        llm_job = LLMJob(**job_data)

        # Map RQ status to our status
        rq_status = str(rq_job.get_status())

        if rq_status == "finished":
            status = JobStatus.COMPLETED
        elif rq_status == "failed":
            status = JobStatus.FAILED
        elif rq_status == "started":
            status = JobStatus.PROCESSING
        elif rq_status in ("deferred", "queued"):
            status = JobStatus.QUEUED
        else:
            status = JobStatus.PROCESSING if rq_job.started_at else JobStatus.QUEUED

        # Calculate processing time
        processing_time = None
        if rq_job.started_at and rq_job.ended_at:
            processing_time = float(
                (rq_job.ended_at - rq_job.started_at).total_seconds()
            )

        return JobResult(
            job_id=job_id,
            job=llm_job,
            status=status,
            result=rq_job.result if rq_status == "finished" else None,
            error=str(rq_job.exc_info) if rq_job.exc_info else None,
            completed_at=rq_job.ended_at,
            processing_time=processing_time,
            retry_count=int(rq_job.meta.get("retry_count", 0)),
        )


def get_queue_backend(queue_name: str = "llm") -> QueueBackend:
    """Get the configured queue backend instance.

    Reads configuration from environment variables:
    - QUEUE_BACKEND: Backend type ("redis" or "sqs", default: "redis")
    - REDIS_URL: Redis connection URL (required for redis backend)
    - SQS_QUEUE_URL: SQS queue URL (required for sqs backend)

    Args:
        queue_name: Name of the queue (default: "llm")

    Returns:
        Configured QueueBackend instance

    Raises:
        ValueError: If backend type is not supported
        NotImplementedError: If SQS backend requested (not yet implemented)
    """
    global _queue_backend_instance, _queue_backend_initialized

    if not _queue_backend_initialized:
        _queue_backend_instance = _create_queue_backend(queue_name)
        _queue_backend_initialized = True

    return _queue_backend_instance  # type: ignore


def reset_queue_backend() -> None:
    """Reset queue backend singleton. Used for testing."""
    global _queue_backend_instance, _queue_backend_initialized
    _queue_backend_instance = None
    _queue_backend_initialized = False


def _create_queue_backend(queue_name: str) -> QueueBackend:
    """Create queue backend based on environment configuration."""
    backend_type = os.environ.get("QUEUE_BACKEND", "redis").lower()

    backend: QueueBackend
    if backend_type == "redis":
        import redis as _redis

        redis_url = os.environ.get("REDIS_URL", "redis://cache:6379/0")
        redis_client = _redis.Redis.from_url(redis_url)

        backend = RedisQueueBackend(
            redis_client=redis_client,
            queue_name=queue_name,
        )
        backend.setup()
        return backend

    elif backend_type == "sqs":
        from app.llm.queue.backend_sqs import SQSQueueBackend

        # Get required SQS configuration from environment
        sqs_queue_url = os.environ.get("SQS_QUEUE_URL")
        sqs_jobs_table = os.environ.get("SQS_JOBS_TABLE")

        if not sqs_queue_url:
            raise ValueError(
                "SQS_QUEUE_URL is required when using SQS backend. "
                "Set QUEUE_BACKEND=redis for local development."
            )
        if not sqs_jobs_table:
            raise ValueError(
                "SQS_JOBS_TABLE is required when using SQS backend. "
                "Set QUEUE_BACKEND=redis for local development."
            )

        region_name = os.environ.get("AWS_DEFAULT_REGION")

        backend = SQSQueueBackend(
            queue_url=sqs_queue_url,
            dynamodb_table=sqs_jobs_table,
            region_name=region_name,
        )
        backend.setup()
        return backend

    else:
        raise ValueError(
            f"Unknown QUEUE_BACKEND: {backend_type}. " "Supported values: redis, sqs"
        )
