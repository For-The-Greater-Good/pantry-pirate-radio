"""Job processing utilities."""

import logging
from datetime import datetime
from typing import Any, cast

from redis import Redis

from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse
from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.queue.queues import llm_queue

logger = logging.getLogger(__name__)


class JobProcessor:
    """Process LLM jobs."""

    def __init__(
        self,
        provider: BaseLLMProvider[Any, Any],
        redis: Redis | None = None,
    ) -> None:
        """Initialize processor.

        Args:
            provider: LLM provider instance
            redis: Optional Redis client
        """
        self.provider = provider
        self.redis = redis

    def enqueue(
        self,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        format: dict[str, Any] | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> str:
        """Enqueue a job for processing.

        Args:
            prompt: Input prompt
            metadata: Optional metadata
            format: Optional format configuration
            provider_config: Optional provider configuration

        Returns:
            Job ID
        """
        # Create job
        job = LLMJob(
            id=str(datetime.now().timestamp()),
            prompt=prompt,
            metadata=metadata or {},
            format=format or {},
            provider_config=provider_config or {},
            created_at=datetime.now(),
        )

        # Submit job using RQ
        rq_job = llm_queue.enqueue_call(
            func="app.llm.queue.processor.process_llm_job",
            args=(job, self.provider),
            job_id=job.id,
            meta={"job": job.model_dump()},
            result_ttl=86400,  # Keep results for 24 hours
            failure_ttl=86400,  # Keep failed jobs for 24 hours
        )

        return str(rq_job.id)

    def get_result(self, job_id: str, wait: bool = True) -> JobResult | None:
        """Get job result.

        Args:
            job_id: Job ID to get result for
            wait: Whether to wait for job completion

        Returns:
            Job result if available, None otherwise
        """
        # Get job from RQ
        rq_job = llm_queue.fetch_job(job_id)
        if not rq_job:
            return None

        # Get job data from meta
        job_data = cast(dict[str, Any], rq_job.meta.get("job", {}))
        if not job_data:
            return None

        # Create base job
        job = LLMJob(**job_data)

        # Wait for result if requested and refresh job status
        if wait:
            rq_job.refresh()
            # Ensure we get the latest status
            rq_job = llm_queue.fetch_job(job_id)
            if not rq_job:
                return None

        # Check job status and refresh one more time to be sure
        rq_job.refresh()
        if rq_job.is_finished:
            result = cast(LLMResponse, rq_job.result)
            return JobResult(
                job_id=job_id,
                job=job,
                status=JobStatus.COMPLETED,
                result=result,
                error=None,
                completed_at=rq_job.ended_at,
                processing_time=(
                    float((rq_job.ended_at - rq_job.started_at).total_seconds())
                    if rq_job.started_at and rq_job.ended_at
                    else None
                ),
            )
        elif rq_job.is_failed:
            return JobResult(
                job_id=job_id,
                job=job,
                status=JobStatus.FAILED,
                result=None,
                error=str(rq_job.exc_info),
                completed_at=rq_job.ended_at,
                processing_time=(
                    float((rq_job.ended_at - rq_job.started_at).total_seconds())
                    if rq_job.started_at and rq_job.ended_at
                    else None
                ),
            )
        else:
            return JobResult(
                job_id=job_id,
                job=job,
                status=JobStatus.QUEUED,
                result=None,
                error=None,
                completed_at=None,
                processing_time=None,
            )
