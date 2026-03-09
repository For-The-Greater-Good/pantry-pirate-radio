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
        LLM_MODEL_NAME=us.anthropic.claude-haiku-4-5-20251001-v1:0

    Then run:
        python -m app.llm.queue.fargate_worker
"""

import collections
import os
import signal
import sys
import threading
import time
from typing import Any

import structlog

from app.llm.providers.factory import create_provider
from app.llm.queue.backend import get_queue_backend
from app.llm.queue.backend_sqs import SQSQueueBackend
from app.llm.queue.processor import process_llm_job, validate_sqs_queue_urls
from app.llm.queue.types import JobStatus

logger = structlog.get_logger(__name__)


class _HeartbeatThread:
    """Background thread that repeatedly calls a callback at a fixed interval.

    Uses ``threading.Event`` for clean shutdown instead of a self-rescheduling
    ``threading.Timer`` chain, which avoids unbounded timer creation and makes
    cancellation deterministic.

    H5 FIX: Retries transient failures with exponential backoff (3 attempts)
    before giving up. Sets ``failed`` flag so the main thread can detect
    heartbeat death and abort processing cleanly.
    """

    _MAX_RETRIES = 3

    def __init__(self, interval: float, callback: Any) -> None:
        self._interval = interval
        self._callback = callback
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.failed = False

    def start(self) -> None:
        """Start the heartbeat thread."""
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to stop and wait for it to finish."""
        self._stop_event.set()
        self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        """Loop until stop is requested, calling callback each interval."""
        while not self._stop_event.wait(self._interval):
            success = False
            for attempt in range(self._MAX_RETRIES):
                try:
                    self._callback()
                    success = True
                    break
                except Exception:
                    logger.warning(
                        "heartbeat_callback_error",
                        attempt=attempt + 1,
                        max_retries=self._MAX_RETRIES,
                        exc_info=True,
                    )
                    if attempt < self._MAX_RETRIES - 1:
                        # Exponential backoff between retries
                        time.sleep(2 ** (attempt + 1))

            if not success:
                logger.error(
                    "heartbeat_permanently_failed",
                    message="Heartbeat thread giving up after max retries",
                )
                self.failed = True
                break


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
            "LLM_MODEL_NAME", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
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

    def _start_visibility_heartbeat(
        self,
        receipt_handle: str,
        job_id: str,
    ) -> _HeartbeatThread:
        """Start a background thread to extend message visibility while processing.

        This prevents the message from becoming visible to other workers
        while a long-running LLM job is being processed. Uses a single
        ``_HeartbeatThread`` instead of a self-rescheduling Timer chain.

        Args:
            receipt_handle: SQS receipt handle for the message
            job_id: Job ID for logging

        Returns:
            The started _HeartbeatThread (caller must stop it when done)
        """
        new_timeout = self.visibility_extension_interval + 60
        interval = self.visibility_extension_interval / 2

        def _extend_visibility() -> None:
            """Extend visibility for the current message."""
            if (
                self._shutdown_requested
                or self._current_receipt_handle != receipt_handle
            ):
                # Raising stops the heartbeat loop cleanly
                raise RuntimeError("job_no_longer_active")
            self.backend.change_visibility(receipt_handle, new_timeout)
            logger.debug(
                "visibility_extended",
                job_id=job_id,
                new_timeout=new_timeout,
            )

        heartbeat = _HeartbeatThread(interval, _extend_visibility)
        heartbeat.start()
        return heartbeat

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

            # Start recurring visibility heartbeat thread
            heartbeat = self._start_visibility_heartbeat(receipt_handle, job_id)

            try:
                # Process the job
                result = process_llm_job(job, self.provider)

                # H5: Check if heartbeat died (message may have been redelivered)
                if heartbeat.failed:
                    logger.error(
                        "heartbeat_failed_during_llm_processing",
                        job_id=job_id,
                    )
                    return False

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
                # Stop visibility heartbeat thread
                heartbeat.stop()
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

        # Job-level failure rate tracking (I9): track the last N job outcomes.
        # If >90 % of the last JOB_HISTORY_SIZE jobs failed, the worker is
        # unlikely to recover and should be replaced by ECS.
        job_history_size = 20
        job_failure_threshold = 0.90
        # True = success, False = failure
        job_results: collections.deque[bool] = collections.deque(
            maxlen=job_history_size
        )

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
                    job_results.append(success)
                    if success:
                        processed_count += 1
                    else:
                        failed_count += 1

                    # Check job-level failure rate once we have enough data
                    if len(job_results) >= job_history_size:
                        failure_count = sum(1 for r in job_results if not r)
                        failure_rate = failure_count / len(job_results)
                        if failure_rate > job_failure_threshold:
                            logger.critical(
                                "job_failure_rate_exceeded",
                                failure_rate=round(failure_rate, 2),
                                failures=failure_count,
                                window=len(job_results),
                                message=(
                                    "Worker shutting down: "
                                    f">{job_failure_threshold*100:.0f}% of "
                                    f"last {job_history_size} jobs failed"
                                ),
                            )
                            self._shutdown_requested = True
                            break

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

        # Determine if shutdown was abnormal (poll errors or job failure rate)
        job_failure_shutdown = False
        if len(job_results) >= job_history_size:
            failure_count = sum(1 for r in job_results if not r)
            job_failure_shutdown = (
                failure_count / len(job_results) > job_failure_threshold
            )

        # Exit with error code if shutdown was due to repeated failures
        # so ECS replaces the task instead of treating it as a healthy exit
        if consecutive_errors >= max_consecutive_errors or job_failure_shutdown:
            reason = (
                "consecutive_poll_errors"
                if consecutive_errors >= max_consecutive_errors
                else "job_failure_rate"
            )
            logger.critical(
                "worker_exiting_with_error_code",
                reason=reason,
                consecutive_errors=consecutive_errors,
                message="Exiting with code 1 so ECS replaces the task",
            )
            sys.exit(1)

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
            return 1

        # C3: Validate required SQS queue URLs at startup (fail fast)
        validate_sqs_queue_urls()

        # Create and run worker
        worker = FargateWorker(backend)
        worker.run()

        return 0

    except KeyboardInterrupt:
        logger.info("worker_interrupted")
        return 0

    except Exception as e:
        logger.error("worker_startup_failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
