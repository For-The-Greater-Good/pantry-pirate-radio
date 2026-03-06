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
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Module-level SQS client cache
_sqs_client: Any = None


def _get_sqs_client() -> Any:
    """Get or create a cached SQS client."""
    global _sqs_client
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
