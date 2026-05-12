"""Pydantic schemas for the PTF /locations endpoints.

These mirror Plentiful's `/map/locations` (list) and `/map/location/:id`
(detail) wire shapes field-for-field, with a single PPR addition:
`feeding_america_food_bank`. `extra = "forbid"` is non-negotiable —
unknown keys must blow up so future Plentiful additions can't pass
through silently.

Invariants are pushed into the type system where possible (numeric
bounds on coordinates, phone, and service_type) so OpenAPI documents
the contract and drifts fail at validation time rather than at the
consumer end.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---- Reusable typed primitives -------------------------------------------

# WGS84 bounds. Plentiful filters out lat=0,lng=0 (Null Island) at the SQL
# layer; the transformer enforces it again. The 0,0 case is *allowed* by
# this type because Pydantic can't see the joint constraint — see
# `locations_queries.py` / `locations_transformer.py` for the filter.
Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]

# Plentiful emits phone as a non-negative int with 0 as the null sentinel.
# Real US/CA numbers fit in 11 digits, but 10/11 digit values are still
# expected — bound at 12 digits to leave room for ext but reject garbage.
PhoneInt = Annotated[
    int,
    Field(ge=0, le=99_999_999_999, description="Digits only; 0 means null"),
]

# Always negative (or zero in the vanishing-collision case) hash of the
# UUID. Plentiful's invariant is `pantry_id <= 0` for non-Pantry orgs.
PantryIdInt = Annotated[
    int,
    Field(
        le=0, description="Negative-or-zero hash of UUID; PPR has no Plentiful Pantry"
    ),
]

# Plentiful's enum: 1=line (walk-in), 2=appointment. PPR currently emits 1.
ServiceType = Literal[1, 2]


class PtfFeedingAmericaFoodBank(BaseModel):
    """The Feeding America regional food bank for this location, when known."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1, description="Feeding America OrganizationID")
    name: str
    state: Optional[str] = Field(default=None, description="Two-letter US state code")
    find_food_url: Optional[str] = None
    url_slug: Optional[str] = None
    is_affiliate: Optional[bool] = None
    parent_org_id: Optional[int] = Field(default=None, ge=1)
    parent_name: Optional[str] = None


class PtfLocationListItem(BaseModel):
    """List-shape item — mirrors Plentiful Organization.getMapLocations()."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="PPR UUID; the canonical identifier")
    name: str
    short_name: str
    address_street_1: str
    address_street_2: str
    city: str
    zip_code: Optional[int] = Field(
        default=None,
        description=(
            "5-digit ZIP coerced to int. Leading zeros (PR/MA/CT/NJ) lose "
            "their padding to match Plentiful's wire format."
        ),
    )
    state: str
    phone: PhoneInt
    website: str
    pantry_id: PantryIdInt
    pantry_timezone: str
    avatar: str = Field(description="CDN URL; empty string when PPR has none")
    longitude: Longitude
    latitude: Latitude
    has_plentiful_pantry: bool = Field(
        description="Always False for PPR-sourced locations"
    )
    has_appointments: bool
    service_type: ServiceType
    programs: list[str]
    services: Optional[str] = None
    services_detailed: Optional[list[dict[str, Any]]] = None
    next_service: Optional[dict[str, Any]] = None
    feeding_america_food_bank: Optional[PtfFeedingAmericaFoodBank] = None


class PtfLocationDetail(BaseModel):
    """Detail-shape — mirrors Plentiful Organization.getOrganization() and
    Pantry.getPantryDetails(), so `plentiful-rn/types/Pantry.ts` round-trips
    cleanly even for fields PPR has no source data for."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    short_name: str
    address: str = Field(
        description="Composed: street1, street2, city, state, zip (Plentiful order)"
    )
    address_street_1: str
    address_street_2: str
    city: str
    state: str
    zip_code: Optional[int] = None
    latitude: Latitude
    longitude: Longitude
    phone: PhoneInt
    website: str
    email: str
    additional_info: str
    notes: str = Field(
        description="RN type alias of additional_info; emitted identically"
    )
    avatar: str
    small_photo_url: str = Field(
        description="Pantry photo URL; empty string when PPR has none"
    )
    timezone: str
    schedule: str
    types: list[int]
    images: list[dict[str, Any]]
    pantry_id: PantryIdInt
    user_can_visit: bool
    user_visit_summary: str
    service_hours: list[dict[str, Any]]
    amenities: list[str]
    conditions: list[str]
    has_appointment: bool
    has_line_open: bool
    use_tefap: bool
    # Plentiful-required RN fields PPR has no source data for. Emitted
    # as their TypeScript-default values so `Pantry.ts` deserializes.
    requested_fields: list[str]
    allowed_fields: list[str]
    new_options: list[dict[str, Any]]
    visits: list[dict[str, Any]]
    upcoming: list[dict[str, Any]]
    editable: list[dict[str, Any]]
    frequency_limitations: int = Field(ge=0)
    frequency_limitations_count: int = Field(ge=0)
    advance_registration: int = Field(ge=0)
    additional_info_confirmed_at: Optional[str] = None
    reservations_available_notifications: bool
    subscribed: bool
    auth_code_id: int = Field(ge=0)
    use_auth_codes: int = Field(ge=0, le=1)
    use_zip_code_restrictions: int = Field(ge=0, le=1)
    restricted_zip_codes: Optional[str] = None
    updated_at: str
    disable_client_booking: bool
    # camelCase here is intentional — Plentiful's wire format uses
    # `nextVisit` / `lastVisit` and the RN TypeScript type matches.
    nextVisit: Optional[dict[str, Any]] = None  # noqa: N815
    lastVisit: Optional[dict[str, Any]] = None  # noqa: N815
    user_can_book: bool
    distance: float = Field(ge=0)
    feeding_america_food_bank: Optional[PtfFeedingAmericaFoodBank] = None
