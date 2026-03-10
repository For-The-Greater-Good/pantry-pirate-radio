"""API key authentication for Tightbeam endpoints.

Supports two modes:
- AWS: API Gateway pre-validates the key; middleware extracts key ID + context.
- Local: Validates against TIGHTBEAM_API_KEYS env var (comma-separated).
"""

import os

import structlog
from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings

from .models import CallerIdentity

logger = structlog.get_logger(__name__)

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

# Detect AWS API Gateway context (set by API Gateway when key is validated)
_APIGW_KEY_ID_HEADER = "x-api-key-id"
_APIGW_SOURCE_IP_HEADER = "x-forwarded-for"


def _parse_local_keys() -> dict[str, str]:
    """Parse TIGHTBEAM_API_KEYS into a dict of key -> name."""
    raw = settings.TIGHTBEAM_API_KEYS
    if not raw:
        return {}
    keys: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            name, key = entry.split(":", 1)
            keys[key.strip()] = name.strip()
        else:
            keys[entry] = "default"
    return keys


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> CallerIdentity:
    """Validate API key and return caller identity.

    AWS mode: API Gateway has already validated the key. We extract the key ID
    from the request context headers set by API Gateway.

    Local mode: We validate the key against the TIGHTBEAM_API_KEYS setting.
    """
    if not settings.TIGHTBEAM_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    # AWS API Gateway mode: key already validated, extract context
    is_lambda = os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
    if is_lambda:
        key_id = request.headers.get(_APIGW_KEY_ID_HEADER, "")
        if key_id:
            return CallerIdentity(
                api_key_id=key_id,
                api_key_name=request.headers.get("x-api-key-name"),
                source_ip=request.headers.get(_APIGW_SOURCE_IP_HEADER),
                user_agent=request.headers.get("user-agent"),
            )

    # Local mode: validate key ourselves
    if not api_key:
        logger.warning("tightbeam_auth_missing_key", path=str(request.url.path))
        raise HTTPException(status_code=401, detail="API key required")

    valid_keys = _parse_local_keys()
    if api_key not in valid_keys:
        logger.warning("tightbeam_auth_invalid_key", path=str(request.url.path))
        raise HTTPException(status_code=403, detail="Invalid API key")

    key_name = valid_keys[api_key]
    source_ip = request.client.host if request.client else None

    return CallerIdentity(
        api_key_id=api_key[:8] + "...",
        api_key_name=key_name,
        source_ip=source_ip,
        user_agent=request.headers.get("user-agent"),
    )
