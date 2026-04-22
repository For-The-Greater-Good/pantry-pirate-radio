"""RFC 5545 iCalendar helpers — canonical normalization for schedule.byday.

Used by the submarine result builder, the reconciler, and Pydantic
validators so every write path converges on the same format before
the value reaches the database.

Spec: https://datatracker.ietf.org/doc/html/rfc5545#section-3.3.10
BYDAY token = [<weekdaynum>]<weekday>, where weekdaynum = [plus/minus] ordwk
(1..5). Comma-separates a list. Anything else is dropped to NULL with a
warning so CloudWatch can surface new drift.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)


BYDAY_TOKEN_PATTERN = re.compile(r"^[+-]?[1-5]?(?:MO|TU|WE|TH|FR|SA|SU)$")
"""Matches one valid RFC 5545 BYDAY token (MO..SU with optional ±1..±5 prefix)."""


_DAY_ABBREV: dict[str, str] = {
    "monday": "MO",
    "tuesday": "TU",
    "wednesday": "WE",
    "thursday": "TH",
    "friday": "FR",
    "saturday": "SA",
    "sunday": "SU",
}

_ORDINAL_WORDS: dict[str, int] = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "last": -1,
}

_L_PREFIX_PATTERN = re.compile(r"^L(MO|TU|WE|TH|FR|SA|SU)$")
_PROSE_PATTERN = re.compile(
    r"^(first|second|third|fourth|fifth|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
    re.IGNORECASE,
)


def _coerce_token(token: str) -> str | None:
    """Best-effort coercion of a single token to an RFC 5545 BYDAY token.

    Returns None if the token cannot be coerced. Callers that need the
    full RFC 5545 pattern enforcement should validate the result with
    BYDAY_TOKEN_PATTERN.
    """
    if not token:
        return None

    # Unicode minus → ASCII hyphen (issue 1)
    token = token.replace("−", "-")  # noqa: RUF001 — intentional: normalizing U+2212

    # "Third Tuesday", "last friday", etc. (issue 2)
    prose = _PROSE_PATTERN.match(token)
    if prose:
        ordinal = _ORDINAL_WORDS[prose.group(1).lower()]
        day = _DAY_ABBREV[prose.group(2).lower()]
        return f"{ordinal}{day}"

    # "Monday" bare → "MO"
    lower = token.lower()
    if lower in _DAY_ABBREV:
        return _DAY_ABBREV[lower]

    # Promote to uppercase so "mo" → "MO", "1fr" → "1FR"
    upper = token.upper()

    # "LTU" → "-1TU" (issue 4)
    lprefix = _L_PREFIX_PATTERN.match(upper)
    if lprefix:
        return f"-1{lprefix.group(1)}"

    if BYDAY_TOKEN_PATTERN.match(upper):
        return upper

    return None


def normalize_byday(raw: str | None) -> str | None:
    """Coerce a BYDAY string to RFC 5545 form, or return None on failure.

    Accepts comma-separated tokens with optional whitespace around each.
    Silently returns None for empty/None input. For a non-empty input
    that cannot be fully normalized, returns None and emits a
    structlog warning so CloudWatch can surface new drift patterns.
    """
    if raw is None:
        return None

    stripped = raw.strip()
    if not stripped:
        return None

    # Normalize Unicode minus up-front so split/strip work on ASCII only.
    stripped = stripped.replace("−", "-")  # noqa: RUF001 — intentional

    tokens = [t.strip() for t in stripped.split(",")]
    normalized: list[str] = []
    for tok in tokens:
        coerced = _coerce_token(tok)
        if coerced is None or not BYDAY_TOKEN_PATTERN.match(coerced):
            logger.warning("ical_byday_unrecognized", raw=raw)
            return None
        normalized.append(coerced)

    return ",".join(normalized)
