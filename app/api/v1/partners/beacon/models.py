"""Pydantic models for beacon partner sync endpoint.

Richer than PTF — includes structured schedules, phones, languages,
and accessibility for rendering full location detail pages.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class BeaconSchedule(BaseModel):
    """A schedule entry with structured day/time data."""

    opens_at: Optional[str] = None
    closes_at: Optional[str] = None
    byday: Optional[str] = None
    freq: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


class BeaconPhone(BaseModel):
    """A phone number with type metadata."""

    number: str
    type: Optional[str] = None
    extension: Optional[str] = None


class BeaconLanguage(BaseModel):
    """A spoken language at a location."""

    name: str
    code: Optional[str] = None


class BeaconAccessibility(BaseModel):
    """Accessibility information for a location."""

    description: Optional[str] = None
    details: Optional[str] = None
    url: Optional[str] = None


class BeaconLocation(BaseModel):
    """Full location record for beacon static page rendering."""

    id: str = Field(description="PPR location UUID")
    name: str = Field(description="Location name")
    description: Optional[str] = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    transportation: Optional[str] = None
    website: Optional[str] = Field(default=None, description="Location URL")
    confidence_score: int = Field(ge=0, le=100)
    validation_status: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    org_email: Optional[str] = None
    org_website: Optional[str] = None
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phones: list[BeaconPhone] = Field(default_factory=list)
    schedules: list[BeaconSchedule] = Field(default_factory=list)
    languages: list[BeaconLanguage] = Field(default_factory=list)
    accessibility: Optional[BeaconAccessibility] = None
    data_sources: list[str] = Field(default_factory=list)
    updated_at: datetime


class BeaconSyncMeta(BaseModel):
    """Pagination and response metadata."""

    total_available: int
    returned: int
    cursor: Optional[str] = None
    has_more: bool
    generated_at: datetime
    etag: str
    data_version: str = "1.0"


class BeaconSyncResponse(BaseModel):
    """Top-level response for beacon sync endpoint."""

    meta: BeaconSyncMeta
    locations: list[BeaconLocation]

    @model_validator(mode="after")
    def check_returned_matches_count(self) -> "BeaconSyncResponse":
        if self.meta.returned != len(self.locations):
            raise ValueError(
                f"meta.returned ({self.meta.returned}) != "
                f"locations count ({len(self.locations)})"
            )
        return self


class BeaconRedirectSurvivor(BaseModel):
    """The surviving canonical location a dead URL should redirect to.

    Address components let beacon reconstruct the survivor's directory URL
    via its own slug rules (slug logic stays in one place — beacon).
    """

    id: str
    name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None


class BeaconRedirect(BaseModel):
    """A soft-deleted location id and the canonical survivor it merged into.

    Beacon already knows the dead URL (from its own build tracker at deletion
    time); this only supplies the survivor side, which lives in the current DB.
    Only redirects with a live canonical survivor are emitted — beacon
    parent-redirects-or-410s anything not present here.
    """

    dead_id: str
    survivor: BeaconRedirectSurvivor


class BeaconRedirectsMeta(BaseModel):
    """Pagination/response metadata for the redirects endpoint."""

    returned: int
    cursor: Optional[str] = None
    has_more: bool
    generated_at: datetime
    data_version: str = "1.0"


class BeaconRedirectsResponse(BaseModel):
    """Top-level response for the beacon redirects endpoint."""

    meta: BeaconRedirectsMeta
    redirects: list[BeaconRedirect]

    @model_validator(mode="after")
    def check_returned_matches_count(self) -> "BeaconRedirectsResponse":
        if self.meta.returned != len(self.redirects):
            raise ValueError(
                f"meta.returned ({self.meta.returned}) != "
                f"redirects count ({len(self.redirects)})"
            )
        return self
