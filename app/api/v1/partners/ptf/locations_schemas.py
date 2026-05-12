"""Pydantic schemas for the PTF /locations endpoints.

These mirror Plentiful's `/map/locations` (list) and `/map/location/:id`
(detail) wire shapes field-for-field, with a single PPR addition:
`feeding_america_food_bank`. `extra = "forbid"` is non-negotiable —
unknown keys must blow up so future Plentiful additions can't pass
through silently.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class PtfFeedingAmericaFoodBank(BaseModel):
    """The Feeding America regional food bank for this location, when known."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    state: Optional[str] = None
    find_food_url: Optional[str] = None
    url_slug: Optional[str] = None
    is_affiliate: Optional[bool] = None
    parent_org_id: Optional[int] = None
    parent_name: Optional[str] = None


class PtfLocationListItem(BaseModel):
    """List-shape item — mirrors Plentiful Organization.getMapLocations()."""

    model_config = ConfigDict(extra="forbid")

    id: str  # PPR UUID, emitted verbatim
    name: str
    short_name: str
    address_street_1: str
    address_street_2: str
    city: str
    zip_code: Optional[int]
    state: str
    phone: int  # 0 when null (Plentiful convention)
    website: str
    pantry_id: int  # Negative hash of UUID; PPR has no Plentiful pantry
    pantry_timezone: str
    avatar: str  # "" when unknown
    longitude: float
    latitude: float
    has_plentiful_pantry: bool
    has_appointments: bool
    service_type: int  # 1=line (default), 2=appointment
    programs: list[str]
    services: Optional[str] = None
    services_detailed: Optional[list[Any]] = None
    next_service: Optional[Any] = None
    feeding_america_food_bank: Optional[PtfFeedingAmericaFoodBank] = None


class PtfLocationDetail(BaseModel):
    """Detail-shape — mirrors Plentiful Organization.getOrganization()."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    short_name: str
    address: str  # Composed: "street1, city, state, zip"
    address_street_1: str
    address_street_2: str
    city: str
    state: str
    zip_code: Optional[int]
    latitude: float
    longitude: float
    phone: int
    website: str
    email: str
    additional_info: str
    avatar: str
    timezone: str
    schedule: str
    types: list[int]
    images: list[Any]
    pantry_id: int
    user_can_visit: bool
    user_visit_summary: str
    service_hours: list[Any]
    amenities: list[str]
    conditions: list[str]
    has_appointment: bool
    has_line_open: bool
    use_tefap: bool
    feeding_america_food_bank: Optional[PtfFeedingAmericaFoodBank] = None
