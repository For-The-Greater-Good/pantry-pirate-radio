"""Queue models and types."""

from typing import Any, Generic, TypeVar, cast

import redis
from rq import Queue

from app.core.config import settings
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus

T = TypeVar("T")

# Type alias for queue processing result
QueueResult = tuple[T, bytes]


class RedisQueue(Generic[T]):
    """Redis-backed queue implementation."""

    def __init__(self, redis: redis.Redis, max_retries: int = 3) -> None:
        """Initialize queue.

        Args:
            redis: Redis client
            max_retries: Maximum number of retries per job
        """
        self.redis = redis
        self.max_retries = max_retries
        self.queue = Queue("llm", connection=redis)

    async def setup(self) -> None:
        """Set up queue."""
        pass  # No setup needed for RQ

    def enqueue(self, job: T, provider: BaseLLMProvider[Any, Any] | None = None) -> str:
        """Enqueue a job.

        Args:
            job: Job to enqueue

        Returns:
            Job ID
        """
        # Use RQ to enqueue job
        rq_job = self.queue.enqueue_call(
            func="app.llm.queue.processor.process_llm_job",
            args=(job, provider),
            job_id=getattr(job, "id", None),
            meta={"job": job.model_dump() if hasattr(job, "model_dump") else job},
            result_ttl=settings.REDIS_TTL_SECONDS,  # Keep results for configured TTL
            failure_ttl=settings.REDIS_TTL_SECONDS,  # Keep failed jobs for configured TTL
        )
        return str(rq_job.id)

    def process_next(self) -> QueueResult[T] | None:
        """Process next job in queue.

        Returns:
            Tuple of (job, message_id) if job available, None otherwise
        """
        # Not needed with RQ
        return None

    def complete_job(
        self,
        job_id: str,
        _message_id: bytes,
        result: LLMResponse | None = None,
        error: str | None = None,
    ) -> None:
        """Complete a job.

        Args:
            job_id: Job ID
            _message_id: Message ID
            result: Optional job result
            error: Optional error message
        """
        # Not needed with RQ
        pass

    def retry_job(self, job_id: str, _message_id: bytes) -> None:
        """Retry a failed job.

        Args:
            job_id: Job ID
            _message_id: Message ID
        """
        # Not needed with RQ
        pass

    def get_status(self, job_id: str) -> JobResult | None:
        """Get job status.

        Args:
            job_id: Job ID

        Returns:
            Job status if available
        """
        # Get job from RQ
        rq_job = self.queue.fetch_job(job_id)
        if not rq_job:
            return None

        # Get job data from meta
        job_data = cast(dict[str, Any], rq_job.meta.get("job", {}))
        if not job_data:
            return None

        # Create base job
        llm_job = LLMJob(**job_data)

        # Map RQ status to our status with proper transitions
        rq_status = str(rq_job.get_status())

        # Handle all possible RQ job states
        if rq_status == "finished":
            status = JobStatus.COMPLETED
        elif rq_status == "failed":
            status = JobStatus.FAILED
        elif rq_status == "started":
            status = JobStatus.PROCESSING
        elif rq_status == "deferred":
            status = JobStatus.QUEUED
        elif rq_status == "queued":
            status = JobStatus.QUEUED
        else:
            # Default to processing if job has started, otherwise queued
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
