"""Generic SQS-polling worker for pipeline services.

Provides a reusable base for all pipeline Fargate workers (validator,
reconciler, recorder). Each service creates a thin entry point that
configures PipelineWorker with the correct processing function.

Follows the same patterns as app.llm.queue.fargate_worker.FargateWorker
but is decoupled from LLM-specific concerns.

Usage:
    from app.pipeline.sqs_worker import PipelineWorker

    def my_process_fn(message_data: dict) -> dict | None:
        # Process the message, return result for forwarding
        return {"processed": True}

    worker = PipelineWorker(
        queue_url="https://sqs.../my-queue.fifo",
        process_fn=my_process_fn,
        service_name="my-service",
        next_queue_url="https://sqs.../next-queue.fifo",
    )
    worker.run()
"""

import json
import os
import signal
import sys
import threading
import time
from typing import Any, Callable

import structlog

from app.pipeline.sqs_sender import send_to_sqs

logger = structlog.get_logger(__name__)


class _VisibilityHeartbeat:
    """Background thread that extends SQS message visibility during processing.

    Matches the pattern in FargateWorker._HeartbeatThread but with retry logic
    (H5 fix applied here as well).
    """

    _MAX_RETRIES = 3

    def __init__(
        self,
        sqs_client: Any,
        queue_url: str,
        receipt_handle: str,
        visibility_timeout: int,
        service_name: str,
    ) -> None:
        self._sqs_client = sqs_client
        self._queue_url = queue_url
        self._receipt_handle = receipt_handle
        self._new_timeout = visibility_timeout
        self._service_name = service_name
        self._stop_event = threading.Event()
        # Extend at half the timeout interval
        self._interval = visibility_timeout / 2
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.failed = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            success = False
            for attempt in range(self._MAX_RETRIES):
                try:
                    self._sqs_client.change_message_visibility(
                        QueueUrl=self._queue_url,
                        ReceiptHandle=self._receipt_handle,
                        VisibilityTimeout=self._new_timeout,
                    )
                    logger.debug(
                        "visibility_extended",
                        service=self._service_name,
                        new_timeout=self._new_timeout,
                    )
                    success = True
                    break
                except Exception:
                    logger.warning(
                        "heartbeat_extend_failed",
                        service=self._service_name,
                        attempt=attempt + 1,
                        max_retries=self._MAX_RETRIES,
                        exc_info=True,
                    )
                    if attempt < self._MAX_RETRIES - 1:
                        time.sleep(2 ** (attempt + 1))

            if not success:
                logger.error(
                    "heartbeat_permanently_failed",
                    service=self._service_name,
                )
                self.failed = True
                break


class PipelineWorker:
    """Generic SQS-polling worker for pipeline services.

    Polls an SQS queue, processes messages through a provided function,
    optionally forwards results to the next queue, and deletes messages
    after successful processing.

    Args:
        queue_url: SQS queue URL to poll
        process_fn: Callable that processes a single message's data payload.
            Receives the 'data' dict from the SQS message envelope.
            Returns a dict to forward to the next queue, or None to skip forwarding.
        service_name: Name of this service for logging
        next_queue_url: Optional SQS queue URL to forward results to
        max_messages: Maximum messages to receive per poll (1-10)
        wait_time_seconds: Long polling wait time (0-20)
        visibility_timeout: SQS visibility timeout in seconds
        max_consecutive_errors: Max errors before shutdown
    """

    def __init__(
        self,
        queue_url: str,
        process_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
        service_name: str,
        next_queue_url: str | None = None,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
        max_consecutive_errors: int = 10,
    ) -> None:
        # C3: Validate queue URLs at startup (fail fast)
        if not queue_url:
            raise ValueError(
                f"queue_url is required for {service_name} PipelineWorker. "
                f"Set the appropriate SQS_QUEUE_URL environment variable."
            )

        self.queue_url = queue_url
        self.process_fn = process_fn
        self.service_name = service_name
        self.next_queue_url = next_queue_url
        self.max_messages = max_messages
        self.wait_time_seconds = wait_time_seconds
        self.visibility_timeout = visibility_timeout
        self.max_consecutive_errors = max_consecutive_errors

        self._running = False
        self._shutdown_requested = False

        self._sqs_client: Any = None

        logger.info(
            "pipeline_worker_initialized",
            service=service_name,
            queue_url=queue_url,
            next_queue_url=next_queue_url,
        )

    def _get_sqs_client(self) -> Any:
        """Get or create SQS client."""
        if self._sqs_client is None:
            import boto3

            region = os.environ.get("AWS_DEFAULT_REGION")
            if region:
                self._sqs_client = boto3.client("sqs", region_name=region)
            else:
                self._sqs_client = boto3.client("sqs")
        return self._sqs_client

    def _setup_signal_handlers(self) -> None:
        """Set up graceful shutdown signal handlers for ECS."""

        def handle_signal(signum: int, frame: Any) -> None:
            logger.info(
                "shutdown_signal_received",
                signal=signum,
                service=self.service_name,
            )
            self._shutdown_requested = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

    def _receive_messages(self) -> list[dict[str, Any]]:
        """Poll SQS for messages.

        Returns:
            List of raw SQS message dicts with parsed bodies
        """
        sqs = self._get_sqs_client()

        response = sqs.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=min(self.max_messages, 10),
            WaitTimeSeconds=self.wait_time_seconds,
            VisibilityTimeout=self.visibility_timeout,
            AttributeNames=["All"],
        )

        messages = []
        for msg in response.get("Messages", []):
            try:
                body = json.loads(msg["Body"])
                data = body.get("data")
                if data is None:
                    logger.info(
                        "sqs_message_missing_envelope_using_raw_body",
                        service=self.service_name,
                        message_id=msg.get("MessageId"),
                        body_keys=list(body.keys()) if isinstance(body, dict) else None,
                    )
                    data = body
                messages.append(
                    {
                        "message_id": msg["MessageId"],
                        "receipt_handle": msg["ReceiptHandle"],
                        "job_id": body.get("job_id", "unknown"),
                        "data": data,
                        "source": body.get("source", "unknown"),
                        "enqueued_at": body.get("enqueued_at"),
                    }
                )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.error(
                    "failed_to_parse_sqs_message",
                    service=self.service_name,
                    message_id=msg.get("MessageId"),
                    error=str(e),
                    raw_body=msg.get("Body", "")[:500],
                )
                # Delete poison pill to prevent infinite retry
                try:
                    sqs.delete_message(
                        QueueUrl=self.queue_url,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
                except Exception as delete_error:
                    logger.error(
                        "failed_to_delete_malformed_message",
                        error=str(delete_error),
                    )

        return messages

    def _process_single_message(self, message: dict[str, Any]) -> bool:
        """Process a single SQS message.

        Args:
            message: Parsed message dict from _receive_messages

        Returns:
            True if processing succeeded, False otherwise
        """
        job_id = message["job_id"]
        receipt_handle = message["receipt_handle"]
        data = message["data"]

        logger.info(
            "processing_message_started",
            service=self.service_name,
            job_id=job_id,
            source=message["source"],
        )

        # H1: Start visibility heartbeat to prevent message redelivery
        # during long-running processing
        sqs = self._get_sqs_client()
        heartbeat = _VisibilityHeartbeat(
            sqs_client=sqs,
            queue_url=self.queue_url,
            receipt_handle=receipt_handle,
            visibility_timeout=self.visibility_timeout,
            service_name=self.service_name,
        )
        heartbeat.start()

        try:
            # Call the processing function
            result = self.process_fn(data)

            # Check if heartbeat died (message may have been redelivered)
            if heartbeat.failed:
                logger.error(
                    "heartbeat_failed_during_processing",
                    service=self.service_name,
                    job_id=job_id,
                )
                return False

            # Forward result to next queue if configured and result is provided.
            # NOTE (M27): The forward-then-delete ordering provides at-least-once
            # delivery semantics. If the worker crashes after forwarding but
            # before deleting, the message will be redelivered by SQS after
            # the visibility timeout expires, resulting in a duplicate.
            # Downstream consumers MUST be idempotent to handle this correctly.
            if self.next_queue_url and result is not None:
                # Extract message group ID from data for FIFO ordering
                group_id = "default"
                if isinstance(data, dict):
                    # Try to get scraper_id from nested job metadata
                    job_data = data.get("job", {})
                    if isinstance(job_data, dict):
                        metadata = job_data.get("metadata", {})
                        if isinstance(metadata, dict):
                            group_id = metadata.get("scraper_id", "default")

                send_to_sqs(
                    queue_url=self.next_queue_url,
                    message_body=result,
                    message_group_id=group_id,
                    source=self.service_name,
                )

            # Delete message after successful processing
            sqs.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
            )

            logger.info(
                "processing_message_completed",
                service=self.service_name,
                job_id=job_id,
                forwarded=bool(self.next_queue_url and result is not None),
            )

            return True

        except Exception as e:
            logger.error(
                "processing_message_failed",
                service=self.service_name,
                job_id=job_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Don't delete message — let it retry via visibility timeout
            return False
        finally:
            heartbeat.stop()

    def run(self) -> None:
        """Run the worker main loop.

        Continuously polls SQS for messages and processes them.
        Handles graceful shutdown on SIGTERM/SIGINT.
        """
        self._setup_signal_handlers()
        self._running = True

        logger.info(
            "pipeline_worker_started",
            service=self.service_name,
            queue_url=self.queue_url,
            max_messages=self.max_messages,
        )

        processed_count = 0
        failed_count = 0
        consecutive_errors = 0
        base_delay = 5

        while self._running and not self._shutdown_requested:
            try:
                messages = self._receive_messages()

                # Reset error counter on successful poll
                consecutive_errors = 0

                if not messages:
                    logger.debug(
                        "no_messages_received",
                        service=self.service_name,
                    )
                    continue

                for message in messages:
                    if self._shutdown_requested:
                        logger.info(
                            "shutdown_during_processing",
                            service=self.service_name,
                        )
                        break

                    success = self._process_single_message(message)
                    if success:
                        processed_count += 1
                    else:
                        failed_count += 1

            except Exception as e:
                consecutive_errors += 1
                delay = min(base_delay * (2 ** min(consecutive_errors - 1, 6)), 300)
                logger.error(
                    "worker_loop_error",
                    service=self.service_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    consecutive_errors=consecutive_errors,
                    retry_delay=delay,
                )

                if consecutive_errors >= self.max_consecutive_errors:
                    logger.critical(
                        "too_many_consecutive_errors",
                        service=self.service_name,
                        count=consecutive_errors,
                    )
                    self._shutdown_requested = True
                    break

                time.sleep(delay)

        logger.info(
            "pipeline_worker_stopped",
            service=self.service_name,
            processed=processed_count,
            failed=failed_count,
        )

        # Exit with error code if shutdown was due to too many consecutive errors
        # so ECS replaces the task instead of treating it as a healthy exit
        if consecutive_errors >= self.max_consecutive_errors:
            logger.critical(
                "worker_exiting_with_error_code",
                service=self.service_name,
                consecutive_errors=consecutive_errors,
                message="Exiting with code 1 so ECS replaces the task",
            )
            sys.exit(1)

    def stop(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_requested = True
        self._running = False
