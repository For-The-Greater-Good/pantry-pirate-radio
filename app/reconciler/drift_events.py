"""Source-drift event publisher.

Emits `source_drift_detected` SNS events when the reconciler's merge
strategy suppresses a canonical-field write because `verified_by`
points at a human writer (admin / source / claimed). The ppr-lighthouse
plugin subscribes to these events and renders them as "a scraper
disagreed with X" callouts on the owner dashboard.

Graceful no-op when LIGHTHOUSE_EVENTS_TOPIC_ARN is unset — local `bouy`
runs and unit tests don't need the AWS side. Failures to publish are
logged and swallowed so the reconciler never fails a merge over a
telemetry problem.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone, UTC
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

_sns_client: Any = None


def _get_topic_arn() -> str | None:
    return os.environ.get("LIGHTHOUSE_EVENTS_TOPIC_ARN") or None


def _get_client() -> Any:
    """Return a process-cached SNS client. Created on first use."""
    global _sns_client
    if _sns_client is None:
        region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
        if region:
            _sns_client = boto3.client("sns", region_name=region)
        else:
            _sns_client = boto3.client("sns")
    return _sns_client


def publish_drift_event(
    *,
    location_id: str,
    scraper_name: str,
    field_name: str,
    scraper_value: str,
    canonical_value: str,
    detected_at: datetime | None = None,
) -> bool:
    """Publish one source-drift event. Returns True if sent, False on skip/error.

    Non-fatal: a failure here is logged but never propagated. The
    reconciler uses the return value only for structured-log bookkeeping.
    """
    topic_arn = _get_topic_arn()
    if not topic_arn:
        # Local / unit-test mode — silently skip. Structured log makes
        # it visible without flagging every call as a warning.
        logger.debug(
            "drift_event_skipped_no_topic",
            extra={
                "location_id": location_id,
                "scraper_name": scraper_name,
                "field_name": field_name,
            },
        )
        return False

    event_time = (detected_at or datetime.now(UTC)).isoformat()
    payload = {
        "event_type": "source_drift_detected",
        "event_id": str(uuid.uuid4()),
        "location_id": location_id,
        "scraper_name": scraper_name,
        "field_name": field_name,
        "scraper_value": scraper_value,
        "canonical_value": canonical_value,
        "detected_at": event_time,
    }

    try:
        _get_client().publish(
            TopicArn=topic_arn,
            Message=json.dumps(payload),
            MessageAttributes={
                "event_type": {
                    "DataType": "String",
                    "StringValue": "source_drift_detected",
                },
            },
        )
        logger.info(
            "drift_event_published",
            extra={
                "location_id": location_id,
                "scraper_name": scraper_name,
                "field_name": field_name,
            },
        )
        return True
    except (BotoCoreError, ClientError) as exc:
        logger.error(
            "drift_event_publish_failed",
            extra={
                "location_id": location_id,
                "scraper_name": scraper_name,
                "field_name": field_name,
                "error": str(exc),
            },
        )
        return False
