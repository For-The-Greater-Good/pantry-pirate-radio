"""Job processor for RQ and SQS backends."""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator, Coroutine
from datetime import datetime
from typing import Any, cast

from app.core.config import settings
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse
from app.llm.queue.models import JobResult, JobStatus, LLMJob

logger = logging.getLogger(__name__)


def _is_sqs_backend() -> bool:
    """Check if the queue backend is SQS."""
    return os.environ.get("QUEUE_BACKEND", "redis").lower() == "sqs"


def get_next_queue(current_queue: str) -> str:
    """Get the next queue in the pipeline.

    Args:
        current_queue: Current queue name

    Returns:
        Name of the next queue
    """
    if current_queue == "llm":
        if should_use_validator():
            return "validator"
        else:
            return "reconciler"
    elif current_queue == "validator":
        return "reconciler"
    else:
        return ""  # Return empty string instead of None


def should_use_validator() -> bool:
    """Check if validator should be used.

    Returns:
        Whether to use validator
    """
    return getattr(settings, "VALIDATOR_ENABLED", False)


def enqueue_to_validator(job_result: JobResult) -> str:
    """Enqueue job to validator queue.

    Uses SQS when QUEUE_BACKEND=sqs, otherwise falls back to RQ.

    Args:
        job_result: Job result to enqueue

    Returns:
        Job ID or SQS message ID
    """
    if _is_sqs_backend():
        from app.pipeline.sqs_sender import send_to_sqs

        queue_url = os.environ.get("VALIDATOR_QUEUE_URL", "")
        scraper_id = "default"
        if job_result.job and job_result.job.metadata:
            scraper_id = job_result.job.metadata.get("scraper_id", "default")

        return send_to_sqs(
            queue_url=queue_url,
            message_body=job_result.model_dump(mode="json"),
            message_group_id=scraper_id,
            deduplication_id=job_result.job_id,
            source="llm-worker",
        )

    from app.validator.queues import get_validator_queue

    validator_queue = get_validator_queue()
    job = validator_queue.enqueue_call(
        func="app.validator.job_processor.process_validation_job",
        args=(job_result,),
        result_ttl=settings.REDIS_TTL_SECONDS,
        failure_ttl=settings.REDIS_TTL_SECONDS,
    )
    return job.id


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

    # Run async generate in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
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

                # Handle different result types
                llm_result: LLMResponse
                if isinstance(result, LLMResponse):
                    # Direct LLMResponse (for testing)
                    llm_result = result
                elif asyncio.iscoroutine(result):
                    # For coroutine result
                    coro = cast(Coroutine[Any, Any, LLMResponse], result)
                    llm_result = loop.run_until_complete(coro)
                else:
                    # For async generator result
                    gen = cast(AsyncGenerator[LLMResponse, None], result)
                    llm_result = loop.run_until_complete(anext(gen))

                # Validate the response — retry only on truly empty responses
                if not llm_result.text or llm_result.text.strip() == "":
                    retry_count += 1
                    last_error = "Received empty response from LLM"
                    logger.warning(
                        f"LLM returned empty response for job {job.id}, "
                        f"retry {retry_count}/{max_retries}"
                    )
                    if retry_count < max_retries:
                        # Wait a bit before retrying (exponential backoff)
                        import time

                        time.sleep(2**retry_count)
                        continue
                    else:
                        # Max retries reached, fail the job
                        raise ValueError(
                            f"LLM consistently returned empty response after {max_retries} attempts"
                        )

                # Response is valid, break out of retry loop
                break

            except Exception as e:
                # Handle Claude-specific errors first - these should not retry
                from app.llm.providers.claude import (
                    ClaudeQuotaExceededException,
                    ClaudeNotAuthenticatedException,
                )

                if isinstance(
                    e, ClaudeNotAuthenticatedException | ClaudeQuotaExceededException
                ):
                    # Handle Claude errors and re-raise them immediately without retrying
                    handle_claude_errors(e, job)
                    # This will re-raise the exception after updating state

                # For other errors, apply retry logic
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

                time.sleep(2**retry_count)

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
            and llm_result.text.strip() != ""
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
                    logger.error(
                        f"Failed to store result in content store: {e}",
                        exc_info=True,
                    )
                    # Don't fail the job, but log the error
            else:
                logger.debug(f"No content_hash in job metadata for job {job.id}")
        elif not is_valid_response:
            logger.warning(
                f"Not storing invalid response in content store for job {job.id}: '{llm_result.text[:50]}...'"
            )
        else:
            logger.debug("Content store not configured")

        # Check if validator is enabled and route accordingly
        if should_use_validator():
            # Route through validator first
            try:
                validator_job_id = enqueue_to_validator(job_result)
                logger.info(
                    f"Successfully enqueued validator job {validator_job_id} for LLM job {job.id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to enqueue validator job for LLM job {job.id}: {e}"
                )
                # Re-raise to ensure the LLM job fails and can be retried
                raise ValueError(f"Failed to enqueue validator job: {e}") from e
        else:
            # Route directly to reconciler (backward compatibility)
            try:
                if _is_sqs_backend():
                    from app.pipeline.sqs_sender import send_to_sqs

                    reconciler_url = os.environ.get("RECONCILER_QUEUE_URL", "")
                    scraper_id = job.metadata.get("scraper_id", "default")
                    msg_id = send_to_sqs(
                        queue_url=reconciler_url,
                        message_body=job_result.model_dump(mode="json"),
                        message_group_id=scraper_id,
                        deduplication_id=job.id,
                        source="llm-worker",
                    )
                    logger.info(
                        f"Successfully sent reconciler SQS message {msg_id} for LLM job {job.id}"
                    )
                else:
                    from app.llm.queue.queues import reconciler_queue

                    reconciler_job = reconciler_queue.enqueue_call(
                        func="app.reconciler.job_processor.process_job_result",
                        args=(job_result,),
                        result_ttl=settings.REDIS_TTL_SECONDS,
                        failure_ttl=settings.REDIS_TTL_SECONDS,
                    )
                    logger.info(
                        f"Successfully enqueued reconciler job {reconciler_job.id} for LLM job {job.id}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to enqueue reconciler job for LLM job {job.id}: {e}"
                )
                # Re-raise to ensure the LLM job fails and can be retried
                raise ValueError(f"Failed to enqueue reconciler job: {e}") from e

        recorder_data = {
            "job_id": job.id,
            "job": job.model_dump(),
            "result": llm_result,
            "error": None,
        }
        try:
            if _is_sqs_backend():
                from app.pipeline.sqs_sender import send_to_sqs

                recorder_url = os.environ.get("RECORDER_QUEUE_URL", "")
                scraper_id = job.metadata.get("scraper_id", "default")
                msg_id = send_to_sqs(
                    queue_url=recorder_url,
                    message_body=recorder_data,
                    message_group_id=scraper_id,
                    source="llm-worker",
                )
                logger.info(
                    f"Successfully sent recorder SQS message {msg_id} for LLM job {job.id}"
                )
            else:
                from app.llm.queue.queues import recorder_queue

                recorder_job = recorder_queue.enqueue_call(
                    func="app.recorder.utils.record_result",
                    args=(recorder_data,),
                    result_ttl=settings.REDIS_TTL_SECONDS,
                    failure_ttl=settings.REDIS_TTL_SECONDS,
                )
                logger.info(
                    f"Successfully enqueued recorder job {recorder_job.id} for LLM job {job.id}"
                )
        except Exception as e:
            # Log error but don't fail the job - recording is optional
            logger.error(f"Failed to enqueue recorder job for LLM job {job.id}: {e}")

        return llm_result
    finally:
        loop.close()


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
            # Update auth state in Redis (only available with Redis backend)
            if not _is_sqs_backend():
                from app.llm.queue.auth_state import AuthStateManager
                from app.llm.queue.queues import llm_queue

                auth_manager = AuthStateManager(llm_queue.connection)
                auth_manager.set_auth_failed(str(e), retry_after=e.retry_after)

            logger.error(
                f"Claude authentication failed: {e}. "
                f"Worker will pause job processing."
            )
            # Just re-raise - the worker will handle retries
            raise

        elif isinstance(e, ClaudeQuotaExceededException):
            # Update quota state in Redis (only available with Redis backend)
            if not _is_sqs_backend():
                from app.llm.queue.auth_state import AuthStateManager
                from app.llm.queue.queues import llm_queue

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
    except ImportError:
        # Claude provider not available, just re-raise original exception
        raise e
