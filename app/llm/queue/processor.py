"""Job processor for RQ."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Coroutine
from datetime import datetime
from typing import Any, cast

from app.core.config import settings
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse
from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.queue.queues import reconciler_queue, recorder_queue, llm_queue

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
    logger.info(
        f"Starting to process LLM job {job.id} with provider {provider.model_name}"
    )

    # DEBUG: Check metadata for content_hash
    print(f"DEBUG: Job {job.id} metadata: {job.metadata}")
    logger.warning(f"DEBUG: Job {job.id} metadata: {job.metadata}")

    # Run async generate in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Retry logic for transient failures
    max_retries = 3
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
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
            
            # Validate the response
            if llm_result.text == "Invalid JSON response":
                retry_count += 1
                last_error = "Received 'Invalid JSON response' from LLM"
                logger.warning(
                    f"LLM returned 'Invalid JSON response' for job {job.id}, "
                    f"retry {retry_count}/{max_retries}"
                )
                if retry_count < max_retries:
                    # Wait a bit before retrying (exponential backoff)
                    import time
                    time.sleep(2 ** retry_count)
                    continue
                else:
                    # Max retries reached, fail the job
                    raise ValueError(
                        f"LLM consistently returned 'Invalid JSON response' after {max_retries} attempts"
                    )
            
            # Response is valid, break out of retry loop
            break
            
        except Exception as e:
            retry_count += 1
            last_error = str(e)
            logger.error(
                f"Error generating LLM response for job {job.id}, "
                f"retry {retry_count}/{max_retries}: {e}"
            )
            if retry_count >= max_retries:
                raise ValueError(
                    f"Failed to generate valid LLM response after {max_retries} attempts: {last_error}"
                )
            # Wait before retrying
            import time
            time.sleep(2 ** retry_count)
    
    # Create job result (outside the retry loop)
    job_result = JobResult(
        job_id=job.id,
        job=job,
        status=JobStatus.COMPLETED,
        result=llm_result,
        error=None,
        completed_at=datetime.now(),
        processing_time=0.0,
    )

    # Validate response before storing in content store
    is_valid_response = (
        llm_result.text 
        and llm_result.text != "Invalid JSON response"
        and llm_result.text != "No response from model"
        and llm_result.text != "Empty response from model"
    )

    # Store result in content store ONLY if valid
    from app.content_store.config import get_content_store

    content_store = get_content_store()
    if content_store and is_valid_response:
        if "content_hash" in job.metadata:
            content_hash = job.metadata["content_hash"]
            logger.info(
                f"Storing result in content store for hash {content_hash[:8]}... (job {job.id})"
            )
            try:
                content_store.store_result(content_hash, llm_result.text, job.id)
                logger.info(
                    f"Successfully stored result for hash {content_hash[:8]}..."
                )
            except Exception as e:
                logger.error(f"Failed to store result in content store: {e}")
                # Don't fail the job, but log the error
        else:
            logger.debug(f"No content_hash in job metadata for job {job.id}")
    elif not is_valid_response:
        logger.warning(
            f"Not storing invalid response in content store for job {job.id}: '{llm_result.text[:50]}...'"
        )
    else:
        logger.debug("Content store not configured")

    # Enqueue follow-up jobs for reconciler and recorder
    try:
        reconciler_job = reconciler_queue.enqueue_call(
            func="app.reconciler.job_processor.process_job_result",
            args=(job_result,),
            result_ttl=settings.REDIS_TTL_SECONDS,  # Keep results for configured TTL
            failure_ttl=settings.REDIS_TTL_SECONDS,  # Keep failed jobs for configured TTL
        )
        logger.info(
            f"Successfully enqueued reconciler job {reconciler_job.id} for LLM job {job.id}"
        )
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
        logger.info(
            f"Successfully enqueued recorder job {recorder_job.id} for LLM job {job.id}"
        )
    except Exception as e:
        # Log error but don't fail the job - recording is optional
        logger.error(f"Failed to enqueue recorder job for LLM job {job.id}: {e}")

    return llm_result


def handle_claude_errors(e: Exception, job: LLMJob) -> None:
    """Handle Claude-specific errors with intelligent retry.
    
    Args:
        e: The exception to handle
        job: The job being processed
    """
    try:
        from app.llm.providers.claude import (
            ClaudeQuotaExceededException,
            ClaudeNotAuthenticatedException,
        )

        if isinstance(e, ClaudeNotAuthenticatedException):
            # Update auth state in Redis
            from app.llm.queue.auth_state import AuthStateManager

            auth_manager = AuthStateManager(llm_queue.connection)
            auth_manager.set_auth_failed(str(e), retry_after=e.retry_after)

            logger.error(
                f"Claude authentication failed: {e}. "
                f"Worker will pause job processing."
            )
            # Just re-raise - the worker will handle retries
            raise

        elif isinstance(e, ClaudeQuotaExceededException):
            # Update quota state in Redis
            from app.llm.queue.auth_state import AuthStateManager

            auth_manager = AuthStateManager(llm_queue.connection)
            auth_manager.set_quota_exceeded(str(e), retry_after=e.retry_after)

            logger.error(
                f"Claude quota exceeded: {e}. " f"Worker will pause job processing."
            )
            # Just re-raise - the worker will handle retries
            raise

        else:
            # Re-raise other exceptions
            raise
    finally:
        loop.close()
