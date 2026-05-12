"""HSDS row → Plentiful-shaped PTF response.

Pure functions, no DB. All Plentiful quirks are isolated here so a
single test row pinpoints any regression: phone-null-becomes-zero,
deterministic negative pantry_id, timezone default, unauth defaults.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any, Optional

from app.api.v1.partners.ptf.formatters import (
    normalize_phone,
    parse_zip_code,
    state_to_timezone,
)
from app.api.v1.partners.ptf.locations_schemas import (
    PtfFeedingAmericaFoodBank,
    PtfLocationDetail,
    PtfLocationListItem,
)

_DEFAULT_TIMEZONE = "America/New_York"

_CATALOGUE_PATH = Path(__file__).parent / "data" / "feeding_america_catalogue.json"


def _load_catalogue() -> dict[int, dict[str, Any]]:
    if not _CATALOGUE_PATH.exists():
        return {}
    raw = json.loads(_CATALOGUE_PATH.read_text())
    # JSON keys are strings; coerce to int for fa_org_id lookup.
    return {int(k): v for k, v in raw.items()}


# Loaded once per process; Lambda warm containers reuse it.
FA_CATALOGUE: dict[int, dict[str, Any]] = _load_catalogue()


def fa_pantry_id_from_uuid(uuid_str: str) -> int:
    """Stable, negative integer derived from a UUID.

    Plentiful uses pantry_id = 0 - organization_id when no Plentiful Pantry
    exists. PPR has no Plentiful Pantry, so every PPR location emits a
    negative id. The hash is deterministic per UUID across processes.
    """
    # crc32 is 32 bits, mask to 31 bits, then negate so it always fits in
    # a signed 32-bit int and remains negative.
    return -(zlib.crc32(uuid_str.encode("utf-8")) & 0x7FFFFFFF)


def _phone_to_int(raw: Optional[str]) -> int:
    """Plentiful uses 0 for null phones; otherwise digits-as-int."""
    digits = normalize_phone(raw)
    if digits is None:
        return 0
    try:
        return int(digits)
    except ValueError:
        return 0


def _timezone_for(state: Optional[str]) -> str:
    tz = state_to_timezone(state) if state else None
    return tz or _DEFAULT_TIMEZONE


def _resolve_fa(
    fa_org_id: Optional[int],
    fa_org_name: Optional[str],
    catalogue: dict[int, dict[str, Any]],
) -> Optional[PtfFeedingAmericaFoodBank]:
    """Build the FA block, enriching from the catalogue when available."""
    if fa_org_id is None:
        return None
    payload: dict[str, Any] = {"id": fa_org_id, "name": fa_org_name or ""}
    enriched = catalogue.get(fa_org_id)
    if enriched:
        for key in (
            "state",
            "find_food_url",
            "url_slug",
            "is_affiliate",
            "parent_org_id",
            "parent_name",
        ):
            value = enriched.get(key)
            if value is not None:
                payload[key] = value
        # Prefer catalogue name when present (clean canonical spelling).
        if enriched.get("name"):
            payload["name"] = enriched["name"]
    return PtfFeedingAmericaFoodBank.model_validate(payload)


def _compose_address(row: Any) -> str:
    parts = [
        row.address_1 or "",
        row.city or "",
        row.state_province or "",
        row.postal_code or "",
    ]
    return ", ".join(p for p in parts if p)


def to_list_item(
    row: Any, catalogue: Optional[dict[int, dict[str, Any]]] = None
) -> PtfLocationListItem:
    """Build the list-shape from a SELECT row (see queries.py)."""
    cat = catalogue if catalogue is not None else FA_CATALOGUE
    uuid_str = str(row.id)
    return PtfLocationListItem(
        id=uuid_str,
        name=row.name or row.org_name or "Unknown",
        short_name=row.short_name or row.name or "",
        address_street_1=row.address_1 or "",
        address_street_2=row.address_2 or "",
        city=row.city or "",
        zip_code=_zip_to_int(row.postal_code),
        state=row.state_province or "",
        phone=_phone_to_int(row.phone_number),
        website=row.org_website or "",
        pantry_id=fa_pantry_id_from_uuid(uuid_str),
        pantry_timezone=_timezone_for(row.state_province),
        avatar="",
        longitude=float(row.longitude) if row.longitude is not None else 0.0,
        latitude=float(row.latitude) if row.latitude is not None else 0.0,
        has_plentiful_pantry=False,
        has_appointments=False,
        service_type=1,
        programs=[],
        services=None,
        services_detailed=None,
        next_service=None,
        feeding_america_food_bank=_resolve_fa(row.fa_org_id, row.fa_org_name, cat),
    )


def to_detail(
    row: Any,
    catalogue: Optional[dict[int, dict[str, Any]]] = None,
    schedules: Optional[list[Any]] = None,
) -> PtfLocationDetail:
    """Build the detail-shape from a SELECT row + schedule rows."""
    cat = catalogue if catalogue is not None else FA_CATALOGUE
    uuid_str = str(row.id)
    return PtfLocationDetail(
        id=uuid_str,
        name=row.name or row.org_name or "Unknown",
        short_name=row.short_name or row.name or "",
        address=_compose_address(row),
        address_street_1=row.address_1 or "",
        address_street_2=row.address_2 or "",
        city=row.city or "",
        state=row.state_province or "",
        zip_code=_zip_to_int(row.postal_code),
        latitude=float(row.latitude) if row.latitude is not None else 0.0,
        longitude=float(row.longitude) if row.longitude is not None else 0.0,
        phone=_phone_to_int(row.phone_number),
        website=row.org_website or "",
        email=row.org_email or "",
        additional_info=row.description or row.org_description or "",
        avatar="",
        timezone=_timezone_for(row.state_province),
        schedule="",
        types=[],
        images=[],
        pantry_id=fa_pantry_id_from_uuid(uuid_str),
        user_can_visit=False,
        user_visit_summary="",
        service_hours=[],
        amenities=[],
        conditions=[],
        has_appointment=False,
        has_line_open=False,
        use_tefap=False,
        feeding_america_food_bank=_resolve_fa(row.fa_org_id, row.fa_org_name, cat),
    )


def _zip_to_int(postal: Optional[str]) -> Optional[int]:
    parsed = parse_zip_code(postal)
    if parsed is None:
        return None
    try:
        return int(parsed)
    except ValueError:
        return None
