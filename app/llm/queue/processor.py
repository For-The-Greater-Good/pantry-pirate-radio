"""Job processor for RQ."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Coroutine
from datetime import datetime, timedelta
from typing import Any, cast

from rq import get_current_job

from app.core.config import settings
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse
from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.queue.queues import reconciler_queue, recorder_queue

logger = logging.getLogger(__name__)


def process_llm_job(job: LLMJob, provider: BaseLLMProvider[Any, Any]) -> LLMResponse:
    """Process an LLM job.

    Args:
        job: The LLM job to process
        provider: The LLM provider to use

    Returns:
        Job result

    Raises:
        ValueError: If job processing fails
        Retry: If quota exceeded, schedules retry with exponential backoff
    """
    logger.info(f"Starting to process LLM job {job.id} with provider {provider.model_name}")

    # Run async generate in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Call generate with proper type handling
        result = provider.generate(
            prompt=job.prompt,
            format=job.format,
            config=None,  # Use default config
        )

        # Handle coroutine or generator result
        if asyncio.iscoroutine(result):
            # For coroutine result
            coro = cast(Coroutine[Any, Any, LLMResponse], result)
            llm_result = loop.run_until_complete(coro)
        else:
            # For async generator result
            gen = cast(AsyncGenerator[LLMResponse, None], result)
            llm_result = loop.run_until_complete(anext(gen))

        # Create job result
        job_result = JobResult(
            job_id=job.id,
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_result,
            error=None,
            completed_at=datetime.now(),
            processing_time=0.0,
        )

        # Enqueue follow-up jobs for reconciler and recorder
        try:
            reconciler_job = reconciler_queue.enqueue_call(
                func="app.reconciler.job_processor.process_job_result",
                args=(job_result,),
                result_ttl=settings.REDIS_TTL_SECONDS,  # Keep results for configured TTL
                failure_ttl=settings.REDIS_TTL_SECONDS,  # Keep failed jobs for configured TTL
            )
            logger.info(f"Successfully enqueued reconciler job {reconciler_job.id} for LLM job {job.id}")
        except Exception as e:
            logger.error(f"Failed to enqueue reconciler job for LLM job {job.id}: {e}")
            # Re-raise to ensure the LLM job fails and can be retried
            raise ValueError(f"Failed to enqueue reconciler job: {e}") from e

        try:
            recorder_job = recorder_queue.enqueue_call(
                func="app.recorder.utils.record_result",
                args=(
                    {
                        "job_id": job.id,
                        "job": job.model_dump(),
                        "result": llm_result,
                        "error": None,
                    },
                ),
                result_ttl=settings.REDIS_TTL_SECONDS,  # Keep results for configured TTL
                failure_ttl=settings.REDIS_TTL_SECONDS,  # Keep failed jobs for configured TTL
            )
            logger.info(f"Successfully enqueued recorder job {recorder_job.id} for LLM job {job.id}")
        except Exception as e:
            logger.error(f"Failed to enqueue recorder job for LLM job {job.id}: {e}")
            # Re-raise to ensure the LLM job fails and can be retried
            raise ValueError(f"Failed to enqueue recorder job: {e}") from e

        # Store result in content store if available
        from app.content_store.config import get_content_store

        content_store = get_content_store()
        if content_store and "content_hash" in job.metadata:
            content_hash = job.metadata["content_hash"]
            content_store.store_result(content_hash, llm_result.text, job.id)

        return llm_result
    except Exception as e:
        # Handle Claude-specific errors with intelligent retry
        from app.llm.providers.claude import (
            ClaudeQuotaExceededException,
            ClaudeNotAuthenticatedException,
        )

        if isinstance(e, ClaudeNotAuthenticatedException):
            current_job = get_current_job()
            if current_job:
                # Get current retry count for auth errors
                retry_count = getattr(current_job.meta, "auth_retry_count", 0)

                # For auth errors, use shorter delays (5 minutes)
                delay = 300  # 5 minutes
                max_auth_retries = 12  # Try for 1 hour total (12 * 5 min)

                if retry_count < max_auth_retries:
                    # Update retry count in job metadata
                    current_job.meta["auth_retry_count"] = retry_count + 1
                    current_job.save_meta()

                    logger.warning(
                        f"Claude not authenticated (attempt {retry_count + 1}/{max_auth_retries}). "
                        f"Retrying in {delay} seconds. Please run: docker compose exec worker claude"
                    )

                    # Schedule retry by enqueuing the job again with delay
                    from app.llm.queue.queues import llm_queue

                    retry_job = llm_queue.enqueue_in(
                        timedelta(seconds=delay),
                        "app.llm.queue.processor.process_llm_job",
                        job,
                        provider,
                        job_id=f"{job.id}_auth_retry_{retry_count + 1}",
                        meta={"auth_retry_count": retry_count + 1},
                        result_ttl=settings.REDIS_TTL_SECONDS,
                        failure_ttl=settings.REDIS_TTL_SECONDS,
                    )

                    logger.info(
                        f"Scheduled auth retry job {retry_job.id} for {delay} seconds"
                    )

                    # Return a special response indicating auth retry scheduled
                    return LLMResponse(
                        text=f"Authentication required, retry scheduled in {delay}s. Please run: docker compose exec worker claude",
                        model=provider.model_name or "claude",
                        usage={
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                        },
                        raw={"auth_retry_scheduled": True, "retry_delay": delay},
                    )
                else:
                    logger.error(
                        f"Claude authentication failed after {max_auth_retries} attempts. Giving up."
                    )
                    raise e
            else:
                logger.error("Claude not authenticated and no job context available")
                raise e

        elif isinstance(e, ClaudeQuotaExceededException):
            current_job = get_current_job()
            if current_job:
                # Get current retry count
                retry_count = getattr(current_job.meta, "quota_retry_count", 0)

                # Calculate exponential backoff delay
                base_delay = getattr(settings, "CLAUDE_QUOTA_RETRY_DELAY", 3600)
                max_delay = getattr(
                    settings, "CLAUDE_QUOTA_MAX_DELAY", 14400
                )  # 4 hours
                multiplier = getattr(settings, "CLAUDE_QUOTA_BACKOFF_MULTIPLIER", 1.5)

                # Calculate delay with exponential backoff
                delay = int(min(base_delay * (multiplier**retry_count), max_delay))

                # Update retry count in job metadata
                current_job.meta["quota_retry_count"] = retry_count + 1
                current_job.save_meta()

                logger.warning(
                    f"Claude quota exceeded (attempt {retry_count + 1}). "
                    f"Retrying in {delay:.0f} seconds ({delay/3600:.1f} hours)"
                )

                # Schedule retry by enqueuing the job again with delay
                from app.llm.queue.queues import llm_queue

                # Re-enqueue the job with the calculated delay
                retry_job = llm_queue.enqueue_in(
                    timedelta(seconds=int(delay)),
                    "app.llm.queue.processor.process_llm_job",
                    job,
                    provider,
                    job_id=f"{job.id}_retry_{retry_count + 1}",
                    meta={"quota_retry_count": retry_count + 1},
                    result_ttl=settings.REDIS_TTL_SECONDS,
                    failure_ttl=settings.REDIS_TTL_SECONDS,
                )

                logger.info(
                    f"Scheduled retry job {retry_job.id} for {delay:.0f} seconds"
                )

                # Return a special response indicating retry scheduled
                return LLMResponse(
                    text=f"Quota exceeded, retry scheduled in {delay:.0f}s",
                    model=provider.model_name or "claude",
                    usage={
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    },
                    raw={"retry_scheduled": True, "retry_delay": delay},
                )
            else:
                # Fallback if no current job context
                logger.error("Claude quota exceeded but no job context available")
                raise e
        else:
            # Re-raise other exceptions
            raise e
    finally:
        loop.close()
