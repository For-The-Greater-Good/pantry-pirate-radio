"""AWS Lambda entry point for the federation retention prune (EventBridge-scheduled).

The Docker realization is ``python -m app.federation prune``; this is the AWS twin.
Both call the SAME :func:`app.federation.__main__._prune` -> ``prune_to_horizon``
(Principle XV: identical behavior across environments). ``settings.DATABASE_URL``
auto-resolves from the Lambda's ``DATABASE_HOST`` + ``DATABASE_SECRET_ARN`` env
(see ``app.core.config``); the archive tier is the S3 backend
(``FEDERATION_ARCHIVE_BACKEND=s3`` + ``FEDERATION_ARCHIVE_S3_BUCKET``).
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    from app.federation.__main__ import _prune

    code = _prune()
    if code != 0:
        # A non-zero exit is a misconfiguration (e.g. no archive tier) — RAISE so the
        # Principle-XIV Lambda Errors alarm fires instead of silently no-op'ing.
        raise RuntimeError(f"federation prune failed (exit {code})")
    return {"status": "ok"}
