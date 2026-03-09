"""SQS message sender utility for inter-service communication.

Replaces RQ's enqueue_call() for SQS-based deployments. Sends JSON messages
to SQS FIFO queues with deduplication and message grouping.

Usage:
    from app.pipeline.sqs_sender import send_to_sqs

    send_to_sqs(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/validator.fifo",
        message_body={"job_id": "abc", "data": {...}},
        message_group_id="scraper-xyz",
    )
"""

import json
import os
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Retry configuration for transient SQS errors
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds
_BACKOFF_FACTOR = 2.0

# AWS error codes that indicate transient failures worth retrying
_RETRYABLE_ERROR_CODES = frozenset(
    {
        "Throttling",
        "ThrottlingException",
        "RequestLimitExceeded",
        "ServiceUnavailable",
        "InternalError",
        "InternalServerError",
        "RequestTimeout",
        "RequestTimeoutException",
    }
)

# Module-level SQS client cache with thread safety
_sqs_client: Any = None
_sqs_client_lock = threading.Lock()


def _get_sqs_client() -> Any:
    """Get or create a cached SQS client (thread-safe)."""
    global _sqs_client
    if _sqs_client is not None:
        return _sqs_client
    with _sqs_client_lock:
        # Double-check after acquiring lock
        if _sqs_client is None:
            import boto3

            region = os.environ.get("AWS_DEFAULT_REGION")
            if region:
                _sqs_client = boto3.client("sqs", region_name=region)
            else:
                _sqs_client = boto3.client("sqs")
    return _sqs_client


def reset_sqs_client() -> None:
    """Reset cached SQS client. Used for testing."""
    global _sqs_client
    with _sqs_client_lock:
        _sqs_client = None


def send_to_sqs(
    queue_url: str,
    message_body: dict[str, Any],
    message_group_id: str = "default",
    deduplication_id: str | None = None,
    source: str = "pipeline",
) -> str:
    """Send a message to an SQS FIFO queue.

    Args:
        queue_url: Full SQS queue URL
        message_body: Message payload (will be JSON-serialized)
        message_group_id: FIFO message group ID for ordering
        deduplication_id: Message deduplication ID (auto-generated if None)
        source: Source service name for tracing

    Returns:
        SQS message ID

    Raises:
        ValueError: If queue_url is empty
    """
    if not queue_url:
        raise ValueError("queue_url is required")

    sqs = _get_sqs_client()

    # Build the envelope
    envelope = {
        "job_id": message_body.get("job_id", str(uuid.uuid4())),
        "data": message_body,
        "source": source,
        "enqueued_at": datetime.now(UTC).isoformat(),
    }

    # Build send_message kwargs
    send_kwargs: dict[str, Any] = {
        "QueueUrl": queue_url,
        "MessageBody": json.dumps(envelope, default=str),
    }

    # Add FIFO attributes if this is a FIFO queue
    if queue_url.endswith(".fifo"):
        send_kwargs["MessageDeduplicationId"] = deduplication_id or envelope["job_id"]
        send_kwargs["MessageGroupId"] = message_group_id

    last_exception: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = sqs.send_message(**send_kwargs)
            message_id = response["MessageId"]

            logger.info(
                "sqs_message_sent",
                queue_url=queue_url,
                message_id=message_id,
                job_id=envelope["job_id"],
                source=source,
            )

            return message_id

        except Exception as e:
            last_exception = e

            if not _is_retryable(e) or attempt == _MAX_RETRIES:
                raise

            delay = _BASE_DELAY * (_BACKOFF_FACTOR**attempt)
            logger.warning(
                "sqs_send_retrying",
                queue_url=queue_url,
                job_id=envelope["job_id"],
                attempt=attempt + 1,
                max_retries=_MAX_RETRIES,
                delay=delay,
                error=str(e),
            )
            time.sleep(delay)

    # Should not be reached, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected retry loop exit")


def _is_retryable(exc: Exception) -> bool:
    """Check whether an exception is a transient AWS error worth retrying.

    M3 FIX: Uses proper isinstance checks via lazy botocore import instead
    of fragile string comparisons on class names.

    Args:
        exc: The exception to check

    Returns:
        True if the error is transient and should be retried
    """
    try:
        from botocore.exceptions import BotoCoreError, ClientError

        # Check for botocore ClientError with retryable error code
        if isinstance(exc, ClientError):
            error_code = exc.response.get("Error", {}).get("Code", "")
            return error_code in _RETRYABLE_ERROR_CODES

        # BotoCoreError covers connection/endpoint errors
        if isinstance(exc, BotoCoreError):
            return True
    except ImportError:
        # Fallback to duck typing if botocore not available
        if type(exc).__name__ == "ClientError" and hasattr(exc, "response"):
            try:
                error_code = exc.response.get("Error", {}).get("Code", "")  # type: ignore[attr-defined]
                return error_code in _RETRYABLE_ERROR_CODES
            except (AttributeError, TypeError):
                pass

        if type(exc).__name__ == "BotoCoreError":
            return True

    # Retry on generic connection/timeout errors
    if isinstance(exc, ConnectionError | TimeoutError):
        return True

    return False
