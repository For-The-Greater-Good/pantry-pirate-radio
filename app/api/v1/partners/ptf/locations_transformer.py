"""HSDS row → Plentiful-shaped PTF response.

Pure functions, no DB. All Plentiful quirks are isolated here so a
single test row pinpoints any regression: phone-null-becomes-zero,
deterministic negative pantry_id, timezone default, unauth defaults.

Failure posture (Principle VI — vulnerable populations):
- Never manufacture coordinates, names, or IDs for missing data. The
  query layer already filters out incomplete rows; the transformer
  raises `PtfRowIncomplete` so the router's per-row try/except can
  log + skip rather than silently shipping a bogus location.
- Every fallback path that would have been silent is now a
  structured warn log so operators discover upstream rot.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any, Optional

import structlog

from app.api.v1.partners.ptf.formatters import (
    format_schedule,
    normalize_phone,
    parse_zip_code,
    state_to_timezone,
)
from app.api.v1.partners.ptf.locations_schemas import (
    PtfFeedingAmericaFoodBank,
    PtfLocationDetail,
    PtfLocationListItem,
)

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEZONE = "America/New_York"

_CATALOGUE_PATH = Path(__file__).parent / "data" / "feeding_america_catalogue.json"


class PtfRowIncompleteError(ValueError):
    """A SELECT row is missing data the wire shape requires.

    Raised by `to_list_item` / `to_detail` so the router can log+skip
    rather than shipping `name="Unknown"` or `(0, 0)` coordinates.
    """


# Back-compat alias retained for callers that import the old name.
# (Currently none, but cheap insurance against breaking imports.)
PtfRowIncomplete = PtfRowIncompleteError


def _load_catalogue() -> dict[int, dict[str, Any]]:
    """Load the FA catalogue JSON snapshot at module import.

    Failure posture:
    - Missing file: log a structured warning and return `{}`. The
      endpoint stays up with the minimum `{id, name}` FA block, but
      the operator knows enrichment is degraded.
    - Corrupt JSON or non-int keys: let `JSONDecodeError` / `ValueError`
      propagate so the process fails loudly on cold start. A corrupt
      catalogue should never silently serve degraded responses for days.
    """
    if not _CATALOGUE_PATH.exists():
        logger.warning(
            "ptf_fa_catalogue_missing",
            path=str(_CATALOGUE_PATH),
            impact="feeding_america_food_bank block will be id+name only",
        )
        return {}
    raw = json.loads(_CATALOGUE_PATH.read_text())
    # JSON keys are strings; coerce to int for fa_org_id lookup. The
    # build script may write a `_metadata` entry with non-int key —
    # skip it (and any other non-numeric key) silently.
    out: dict[int, dict[str, Any]] = {}
    for k, v in raw.items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


# Loaded once per process; Lambda warm containers reuse it.
FA_CATALOGUE: dict[int, dict[str, Any]] = _load_catalogue()


def fa_pantry_id_from_uuid(uuid_str: str) -> int:
    """Stable integer derived from a UUID.

    Plentiful uses `pantry_id = 0 - organization_id` when no Plentiful
    Pantry exists. PPR has no Plentiful Pantry, so every PPR location
    emits a negative-or-zero value. Same UUID always yields the same
    value, deterministic across processes and Lambda warm/cold.

    Collision space: 2^31 ≈ 2.1B. At 100k locations the birthday
    probability is ~0.2%. Consumers MUST treat `id` (the UUID string)
    as the canonical identifier and `pantry_id` as a legacy-shape int.
    """
    # crc32 is 32 bits; mask to 31 bits so the result fits in a signed
    # 32-bit int. Negate so the value is non-positive (zero is possible
    # but vanishingly rare).
    return -(zlib.crc32(uuid_str.encode("utf-8")) & 0x7FFFFFFF)


def _phone_to_int(raw: Optional[str]) -> int:
    """Plentiful convention: 0 for null phones; otherwise digits-as-int.

    Distinguishes the legitimate null case (returns 0, no log) from the
    "normalize_phone returned a non-empty string we can't cast" case
    (returns 0, but logs `ptf_phone_unparseable` so we discover when
    normalize_phone produces garbage).
    """
    digits = normalize_phone(raw)
    if digits is None:
        return 0
    try:
        return int(digits)
    except ValueError:
        logger.warning(
            "ptf_phone_unparseable",
            raw=raw,
            normalized=digits,
        )
        return 0


def _timezone_for(state: Optional[str]) -> str:
    tz = state_to_timezone(state) if state else None
    return tz or _DEFAULT_TIMEZONE


def _resolve_fa(
    fa_org_id: Optional[int],
    fa_org_name: Optional[str],
    catalogue: dict[int, dict[str, Any]],
) -> Optional[PtfFeedingAmericaFoodBank]:
    """Build the FA block, enriching from the catalogue when available.

    Logs `ptf_fa_org_not_in_catalogue` when the JOIN matched an FA org
    that the in-process catalogue snapshot doesn't know about. Indicates
    either a stale catalogue (rerun `scripts/build_ptf_fa_catalogue.py`)
    or a new FA member bank.
    """
    if fa_org_id is None:
        return None
    enriched = catalogue.get(fa_org_id)
    if enriched is None:
        # JOIN found a row but our catalogue is missing it. Ship the
        # minimum id+name block so consumers still get the linkage, and
        # warn so operators can refresh the snapshot.
        logger.warning(
            "ptf_fa_org_not_in_catalogue",
            fa_org_id=fa_org_id,
            fa_org_name=fa_org_name,
        )
        return PtfFeedingAmericaFoodBank.model_validate(
            {"id": fa_org_id, "name": fa_org_name or ""}
        )
    payload: dict[str, Any] = {
        "id": fa_org_id,
        # Prefer the canonical catalogue name when present (clean
        # spelling); fall back to the DB row name.
        "name": enriched.get("name") or fa_org_name or "",
    }
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
    return PtfFeedingAmericaFoodBank.model_validate(payload)


def _affiliations_for(row: Any) -> list[str]:
    """Compute the `affiliations` list for a row.

    A location qualifies for "FANO" iff at least one of its sources is in
    the FANO allowlist (computed in SQL as `has_qualifying_source`). The
    ZIP-to-FA crosswalk only affects `feeding_america_food_bank`; an
    allowlist scraper finding a location is itself a sufficient signal
    that the location is a food bank, regardless of whether the ZIP
    happens to map to a specific FA member bank.

    When the ZIP matched FA crosswalk but the source did not qualify
    (the SQL CASE suppressed `fa_org_id`), we emit a structured info
    log so operators can audit aggregator-only locations that overlap
    FA territory (Constitution XII).
    """
    affiliations: list[str] = []
    has_qualifying = bool(getattr(row, "has_qualifying_source", False))
    if has_qualifying:
        affiliations.append("FANO")
    elif getattr(row, "zip_matched_fa", False):
        logger.info(
            "ptf_fano_suppressed_no_qualifying_source",
            location_id=str(getattr(row, "id", "")),
        )
    return affiliations


def _compose_address(row: Any) -> str:
    """Plentiful's composed address: street1, street2, city, state, zip.

    Mirrors `Organization.formatOrganizationAsLocation` in the monolith
    (`api/models/Organization.js` line ~786-792). Empty segments are
    skipped so a missing `address_street_2` doesn't produce a `", ,"`.
    """
    parts = [
        row.address_1 or "",
        row.address_2 or "",
        row.city or "",
        row.state_province or "",
        row.postal_code or "",
    ]
    return ", ".join(p for p in parts if p)


def _require(row: Any) -> tuple[str, str, float, float]:
    """Extract the four wire-shape-required fields from a row.

    Raises `PtfRowIncomplete` if any required field is missing or
    obviously invalid (name empty, coord null, lat=0 AND lng=0).
    The SQL `WHERE` already filters these; this is defense-in-depth
    so a future query bug or a sentinel-value row still fails loud.
    """
    name = row.name or row.org_name
    if not name:
        raise PtfRowIncomplete(f"location {row.id} has no name")
    lat = row.latitude
    lng = row.longitude
    if lat is None or lng is None:
        raise PtfRowIncomplete(f"location {row.id} has null coordinates")
    lat_f = float(lat)
    lng_f = float(lng)
    if lat_f == 0.0 and lng_f == 0.0:
        raise PtfRowIncomplete(f"location {row.id} has Null Island coordinates")
    return str(row.id), name, lat_f, lng_f


def to_list_item(
    row: Any, catalogue: Optional[dict[int, dict[str, Any]]] = None
) -> PtfLocationListItem:
    """Build the list-shape from a SELECT row (see queries.py).

    Raises `PtfRowIncomplete` if the row is missing data the wire
    shape requires (name, coordinates). The router catches and skips.
    """
    cat = catalogue if catalogue is not None else FA_CATALOGUE
    uuid_str, name, lat_f, lng_f = _require(row)
    return PtfLocationListItem(
        id=uuid_str,
        name=name,
        short_name=row.short_name or name,
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
        longitude=lng_f,
        latitude=lat_f,
        has_plentiful_pantry=False,
        has_appointments=False,
        service_type=1,
        programs=[],
        services=None,
        services_detailed=None,
        next_service=None,
        feeding_america_food_bank=_resolve_fa(row.fa_org_id, row.fa_org_name, cat),
        affiliations=_affiliations_for(row),
    )


def to_detail(
    row: Any,
    catalogue: Optional[dict[int, dict[str, Any]]] = None,
    schedules: Optional[list[Any]] = None,
) -> PtfLocationDetail:
    """Build the detail-shape from a SELECT row + schedule rows.

    Plentiful's RN client (`plentiful-rn/types/Pantry.ts`) expects a
    rich detail shape with many fields PPR has no source data for.
    We emit them with sensible defaults so the TypeScript contract
    deserializes cleanly. See the per-field comments in
    `locations_schemas.py:PtfLocationDetail` for which fields are
    PPR-empty by design.
    """
    cat = catalogue if catalogue is not None else FA_CATALOGUE
    uuid_str, name, lat_f, lng_f = _require(row)
    schedule_str = format_schedule(schedules) if schedules else ""
    return PtfLocationDetail(
        id=uuid_str,
        name=name,
        short_name=row.short_name or name,
        address=_compose_address(row),
        address_street_1=row.address_1 or "",
        address_street_2=row.address_2 or "",
        city=row.city or "",
        state=row.state_province or "",
        zip_code=_zip_to_int(row.postal_code),
        latitude=lat_f,
        longitude=lng_f,
        phone=_phone_to_int(row.phone_number),
        website=row.org_website or "",
        email=row.org_email or "",
        # Plentiful's RN type aliases this as `notes`; we emit both so
        # consumers reading either field get the same payload.
        additional_info=row.description or row.org_description or "",
        notes=row.description or row.org_description or "",
        avatar="",
        small_photo_url="",
        timezone=_timezone_for(row.state_province),
        schedule=schedule_str or "",
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
        # Plentiful-required fields PPR has no data for. Defaults
        # chosen to satisfy the RN TS type without lying about state.
        requested_fields=[],
        allowed_fields=[],
        new_options=[],
        visits=[],
        upcoming=[],
        editable=[],
        frequency_limitations=0,
        frequency_limitations_count=0,
        advance_registration=0,
        additional_info_confirmed_at=None,
        reservations_available_notifications=False,
        subscribed=False,
        auth_code_id=0,
        use_auth_codes=0,
        use_zip_code_restrictions=0,
        restricted_zip_codes=None,
        updated_at="",
        disable_client_booking=False,
        nextVisit=None,
        lastVisit=None,
        user_can_book=False,
        distance=0,
        feeding_america_food_bank=_resolve_fa(row.fa_org_id, row.fa_org_name, cat),
        affiliations=_affiliations_for(row),
    )


def _zip_to_int(postal: Optional[str]) -> Optional[int]:
    """Plentiful's wire-level ZIP is an integer.

    Note: zero-padded ZIPs (PR 006xx, MA 010xx, CT 060xx, NJ 070xx) lose
    their leading zero by going through int. This matches Plentiful's
    existing behavior (their RN client zero-pads on display); changing
    this would break parity. Documented here so a future reader doesn't
    "fix" it.
    """
    parsed = parse_zip_code(postal)
    if parsed is None:
        return None
    try:
        return int(parsed)
    except ValueError:
        logger.warning("ptf_zip_unparseable", raw=postal, normalized=parsed)
        return None
