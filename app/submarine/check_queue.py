"""Lambda handler to check if an SQS queue is empty.

Used by Step Functions to wait for submarine crawlers to finish
before invoking the batcher Lambda for batch inference.
"""

import os
from typing import Any

import boto3
import structlog

logger = structlog.get_logger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Check SQS queue depth and return whether it's empty.

    Args:
        event: {"queue_url": "https://sqs..."} or uses SUBMARINE_QUEUE_URL env var.

    Returns:
        {"is_empty": bool, "visible": int, "in_flight": int}
    """
    queue_url = event.get("queue_url") or os.environ.get("SUBMARINE_QUEUE_URL", "")
    if not queue_url:
        logger.error("check_queue_no_url")
        return {"is_empty": True, "visible": 0, "in_flight": 0, "error": "no queue URL"}

    sqs = boto3.client("sqs")
    attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
    )["Attributes"]

    visible = int(attrs.get("ApproximateNumberOfMessages", "0"))
    in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", "0"))
    is_empty = (visible + in_flight) == 0

    logger.info(
        "check_queue_result",
        queue_url=queue_url,
        visible=visible,
        in_flight=in_flight,
        is_empty=is_empty,
    )

    return {"is_empty": is_empty, "visible": visible, "in_flight": in_flight}
