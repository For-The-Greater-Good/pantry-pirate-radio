"""Fargate worker for processing LLM jobs from SQS.

This module provides the entry point for AWS Fargate workers that:
1. Poll SQS for job messages
2. Process jobs using the configured LLM provider
3. Update job status in DynamoDB
4. Delete messages after successful processing

Usage:
    Set environment variables:
        QUEUE_BACKEND=sqs
        SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123/my-queue
        SQS_JOBS_TABLE=my-jobs-table
        LLM_PROVIDER=bedrock
        LLM_MODEL_NAME=anthropic.claude-sonnet-4-x

    Then run:
        python -m app.llm.queue.fargate_worker
"""

import asyncio
import os
import signal
import sys
import time
from typing import Any

import structlog

from app.llm.providers.factory import create_provider
from app.llm.queue.backend import get_queue_backend
from app.llm.queue.backend_sqs import SQSQueueBackend
from app.llm.queue.processor import process_llm_job
from app.llm.queue.types import JobStatus

logger = structlog.get_logger(__name__)


class FargateWorker:
    """Worker that processes LLM jobs from SQS in a Fargate container.

    Designed for long-running, resource-intensive LLM processing tasks
    that benefit from dedicated compute resources.

    Args:
        backend: SQSQueueBackend instance for job management
        max_messages: Maximum messages to receive per poll (1-10)
        wait_time_seconds: Long polling wait time (0-20)
        visibility_extension_interval: Seconds between visibility extensions
    """

    def __init__(
        self,
        backend: SQSQueueBackend,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
        visibility_extension_interval: int = 120,
    ) -> None:
        """Initialize FargateWorker."""
        self.backend = backend
        self.max_messages = max_messages
        self.wait_time_seconds = wait_time_seconds
        self.visibility_extension_interval = visibility_extension_interval

        self._running = False
        self._shutdown_requested = False
        self._current_receipt_handle: str | None = None

        # Create LLM provider from configuration (read from env directly
        # to avoid importing app.core.events which pulls in Redis)
        llm_provider = os.environ.get("LLM_PROVIDER", "bedrock")
        llm_model = os.environ.get(
            "LLM_MODEL_NAME", "anthropic.claude-sonnet-4-20250514"
        )
        llm_temperature = float(os.environ.get("LLM_TEMPERATURE", "0.1"))
        llm_max_tokens_str = os.environ.get("LLM_MAX_TOKENS")
        llm_max_tokens = int(llm_max_tokens_str) if llm_max_tokens_str else None
        aws_region = os.environ.get("AWS_DEFAULT_REGION")

        self.provider = create_provider(
            llm_provider,
            llm_model,
            llm_temperature,
            llm_max_tokens,
            region_name=aws_region,
        )

        logger.info(
            "fargate_worker_initialized",
            provider=llm_provider,
            model=llm_model,
            queue=backend.queue_name,
        )

    def _setup_signal_handlers(self) -> None:
        """Set up graceful shutdown signal handlers."""

        def handle_signal(signum: int, frame: Any) -> None:
            logger.info("shutdown_signal_received", signal=signum)
            self._shutdown_requested = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

    async def _extend_visibility_periodically(
        self,
        receipt_handle: str,
        job_id: str,
    ) -> None:
        """Periodically extend message visibility while processing.

        This prevents the message from becoming visible to other workers
        while a long-running LLM job is being processed.

        Args:
            receipt_handle: SQS receipt handle for the message
            job_id: Job ID for logging
        """
        while not self._shutdown_requested and self._current_receipt_handle:
            await asyncio.sleep(self.visibility_extension_interval)

            if self._current_receipt_handle == receipt_handle:
                try:
                    # Extend visibility by another interval plus buffer
                    new_timeout = self.visibility_extension_interval + 60
                    self.backend.change_visibility(receipt_handle, new_timeout)
                    logger.debug(
                        "visibility_extended",
                        job_id=job_id,
                        new_timeout=new_timeout,
                    )
                except Exception as e:
                    logger.warning(
                        "visibility_extension_failed",
                        job_id=job_id,
                        error=str(e),
                    )
                    break

    def _process_single_job(self, message: dict[str, Any]) -> bool:
        """Process a single job from SQS.

        Args:
            message: Message dict from receive_messages

        Returns:
            True if processing succeeded, False otherwise
        """
        job_id = message["job_id"]
        receipt_handle = message["receipt_handle"]
        job = message["job"]

        logger.info("processing_job_started", job_id=job_id)

        try:
            # Track current receipt handle for visibility extension
            self._current_receipt_handle = receipt_handle

            # Update status to processing
            self.backend.update_status(job_id, JobStatus.PROCESSING)

            # Start visibility extension task
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            extension_task = loop.create_task(
                self._extend_visibility_periodically(receipt_handle, job_id)
            )

            try:
                # Process the job
                result = process_llm_job(job, self.provider)

                # Cancel visibility extension
                extension_task.cancel()
                try:
                    loop.run_until_complete(extension_task)
                except asyncio.CancelledError:
                    pass

                # Update status to completed with result
                self.backend.update_status(job_id, JobStatus.COMPLETED, result=result)

                # Delete message from queue
                self.backend.delete_message(receipt_handle)

                logger.info(
                    "processing_job_completed",
                    job_id=job_id,
                    result_length=len(result.text) if result and result.text else 0,
                )

                return True

            finally:
                loop.close()
                self._current_receipt_handle = None

        except Exception as e:
            logger.error(
                "processing_job_failed",
                job_id=job_id,
                error=str(e),
            )

            # Update status to failed
            try:
                self.backend.update_status(job_id, JobStatus.FAILED, error=str(e))
            except Exception as status_error:
                logger.error(
                    "failed_to_update_status",
                    job_id=job_id,
                    error=str(status_error),
                )

            # Don't delete message - let it retry via visibility timeout
            self._current_receipt_handle = None
            return False

    def run(self) -> None:
        """Run the worker main loop.

        Continuously polls SQS for messages and processes them.
        Handles graceful shutdown on SIGTERM/SIGINT.
        """
        self._setup_signal_handlers()
        self._running = True

        logger.info(
            "fargate_worker_started",
            queue=self.backend.queue_name,
            max_messages=self.max_messages,
        )

        processed_count = 0
        failed_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 10
        base_delay = 5

        while self._running and not self._shutdown_requested:
            try:
                # Poll for messages
                messages = self.backend.receive_messages(
                    max_messages=self.max_messages,
                    wait_time_seconds=self.wait_time_seconds,
                )

                # Reset error counter on successful poll
                consecutive_errors = 0

                if not messages:
                    logger.debug("no_messages_received")
                    continue

                # Process each message
                for message in messages:
                    if self._shutdown_requested:
                        logger.info("shutdown_during_processing")
                        break

                    success = self._process_single_job(message)
                    if success:
                        processed_count += 1
                    else:
                        failed_count += 1

            except Exception as e:
                consecutive_errors += 1
                # Exponential backoff: 5s, 10s, 20s, 40s, 80s, 160s, max 300s (5 min)
                delay = min(base_delay * (2 ** min(consecutive_errors - 1, 6)), 300)
                logger.error(
                    "worker_loop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    consecutive_errors=consecutive_errors,
                    retry_delay=delay,
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        "too_many_consecutive_errors",
                        count=consecutive_errors,
                        message="Worker shutting down due to repeated failures",
                    )
                    self._shutdown_requested = True
                    break

                time.sleep(delay)

        logger.info(
            "fargate_worker_stopped",
            processed=processed_count,
            failed=failed_count,
        )

    def stop(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_requested = True
        self._running = False


def main() -> int:
    """Main entry point for Fargate worker.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Get queue backend (must be SQS for Fargate)
        backend = get_queue_backend()

        if not isinstance(backend, SQSQueueBackend):
            logger.error(
                "fargate_worker_requires_sqs_backend",
                backend_type=type(backend).__name__,
            )
            print(
                "Error: Fargate worker requires SQS backend. " "Set QUEUE_BACKEND=sqs",
                file=sys.stderr,
            )
            return 1

        # Create and run worker
        worker = FargateWorker(backend)
        worker.run()

        return 0

    except KeyboardInterrupt:
        logger.info("worker_interrupted")
        return 0

    except Exception as e:
        logger.error("worker_startup_failed", error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
