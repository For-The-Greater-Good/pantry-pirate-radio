"""Lambda handler for client-side analytics events.

Receives events from beacon-analytics.js via API Gateway HTTP POST.
Writes to DynamoDB with 90-day TTL.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
import structlog

log = structlog.get_logger()

TABLE_NAME = os.environ.get("BEACON_ANALYTICS_TABLE", "")
TTL_DAYS = 90

_table = None


def _get_table():
    global _table
    if _table is None:
        dynamodb = boto3.resource("dynamodb")
        _table = dynamodb.Table(TABLE_NAME)
    return _table


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """API Gateway HTTP handler for analytics events."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return {"statusCode": 400, "body": "Invalid JSON"}

    page_path = body.get("p", "")
    event_type = body.get("e", "")
    timestamp = str(body.get("t", int(time.time() * 1000)))

    if not page_path or not event_type:
        return {"statusCode": 400, "body": "Missing required fields"}

    item = {
        "page_path": page_path,
        "timestamp": timestamp,
        "event_type": event_type,
        "referrer": body.get("r", ""),
        "data": body.get("d", {}),
        "expires_at": int(time.time()) + TTL_DAYS * 86400,
    }

    if TABLE_NAME:
        try:
            _get_table().put_item(Item=item)
        except Exception:
            log.error("analytics_write_failed", page_path=page_path, exc_info=True)
            return {"statusCode": 500, "body": "Write failed"}

    log.info("analytics_event", event_type=event_type, page_path=page_path)

    return {
        "statusCode": 204,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
        },
        "body": "",
    }
