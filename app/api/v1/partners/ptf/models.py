"""Pydantic models for PTF partner sync endpoint."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class PtfOrganization(BaseModel):
    """A location record pre-formatted for PTF's Organization model."""

    ppr_location_id: str = Field(description="Pantry Pirate Radio location UUID")
    name: str = Field(description="Location or organization name")
    latitude: float = Field(description="WGS84 latitude", ge=-90, le=90)
    longitude: float = Field(description="WGS84 longitude", ge=-180, le=180)
    address_street_1: str = Field(default="", description="Street address line 1")
    address_street_2: str = Field(default="", description="Street address line 2")
    city: str = Field(default="", description="City name")
    state: str = Field(default="", description="Two-letter state code")
    zip_code: Optional[str] = Field(
        default=None,
        description="5-digit ZIP code (zero-padded)",
        pattern=r"^\d{5}$",
    )
    phone: Optional[str] = Field(
        default=None,
        description="Phone number as digits only (10 or 11 digits)",
        pattern=r"^\d{10,11}$",
    )
    website: Optional[str] = Field(default=None, description="Website URL")
    email: Optional[str] = Field(default=None, description="Contact email")
    additional_info: str = Field(
        default="",
        description="Description, services, extra phones, and disclaimer",
    )
    schedule: Optional[str] = Field(
        default=None,
        description="Human-readable schedule, e.g. 'Monday: 9:00 AM - 5:00 PM'",
    )
    timezone: Optional[str] = Field(
        default=None, description="IANA timezone, e.g. 'America/New_York'"
    )
    hide: int = Field(default=0, description="0=visible, 1=hidden")
    boundless_id: Optional[int] = Field(
        default=None, description="Reserved for partner use"
    )
    data_sources: list[str] = Field(
        default_factory=list,
        description="Human-readable names of data sources",
    )
    confidence_score: int = Field(description="Data quality score 0-100", ge=0, le=100)
    updated_at: datetime = Field(description="Last update timestamp (UTC)")


class PtfSyncMeta(BaseModel):
    """Metadata for the sync response."""

    total_available: int = Field(description="Total matching records (pre-pagination)")
    returned: int = Field(description="Records in this page")
    cursor: Optional[str] = Field(
        default=None, description="Cursor for next page (base64)"
    )
    has_more: bool = Field(description="Whether more pages exist")
    generated_at: datetime = Field(description="Response generation timestamp (UTC)")
    etag: str = Field(description="ETag for cache validation")
    data_version: str = Field(default="1.0", description="Response schema version")


class PtfSyncResponse(BaseModel):
    """Top-level response for PTF sync endpoint."""

    meta: PtfSyncMeta
    organizations: list[PtfOrganization]

    @model_validator(mode="after")
    def check_returned_matches_count(self) -> "PtfSyncResponse":
        """Validate meta.returned matches actual organization count."""
        if self.meta.returned != len(self.organizations):
            raise ValueError(
                f"meta.returned ({self.meta.returned}) does not match "
                f"organizations count ({len(self.organizations)})"
            )
        return self
