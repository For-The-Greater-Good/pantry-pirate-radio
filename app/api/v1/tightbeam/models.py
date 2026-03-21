"""Pydantic models for the Tightbeam API."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# --- Auth ---


class CallerIdentity(BaseModel):
    """Identity extracted from the authenticated request."""

    api_key_id: str = Field(min_length=1, description="API key identifier")
    api_key_name: Optional[str] = Field(
        default=None, description="Human-readable API key name"
    )
    source_ip: Optional[str] = Field(default=None, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, description="Client user-agent")
    caller_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Flexible caller identity (e.g. slack_user_id, channel_id)",
    )


# --- Search ---


class LocationResult(BaseModel):
    """A location in search results."""

    id: str
    name: Optional[str] = None
    organization_name: Optional[str] = None
    address_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    confidence_score: Optional[int] = Field(default=None, ge=0, le=100)
    validation_status: Optional[str] = None


class SearchResponse(BaseModel):
    """Search results response."""

    results: List[LocationResult]
    total: int = Field(ge=0)
    limit: int
    offset: int


# --- Location Detail ---


class SourceRecord(BaseModel):
    """A single source record for a location."""

    id: str
    scraper_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source_type: Optional[Literal["scraper", "human_update"]] = None
    confidence_score: Optional[int] = Field(default=None, ge=0, le=100)
    validation_status: Optional[Literal["verified", "needs_review", "rejected"]] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LocationDetail(BaseModel):
    """Full location detail with all source records."""

    location: LocationResult
    sources: List[SourceRecord] = Field(default_factory=list)


# --- Update ---


class LocationUpdateRequest(BaseModel):
    """Request body for updating a location."""

    name: Optional[str] = Field(default=None, description="Updated location name")
    address_1: Optional[str] = Field(default=None, description="Updated address")
    city: Optional[str] = Field(default=None, description="Updated city")
    state: Optional[str] = Field(default=None, description="Updated state")
    postal_code: Optional[str] = Field(default=None, description="Updated ZIP code")
    latitude: Optional[float] = Field(
        default=None, ge=-90, le=90, description="Updated latitude"
    )
    longitude: Optional[float] = Field(
        default=None, ge=-180, le=180, description="Updated longitude"
    )
    phone: Optional[str] = Field(default=None, description="Updated phone")
    email: Optional[str] = Field(default=None, description="Updated email")
    website: Optional[str] = Field(default=None, description="Updated website URL")
    description: Optional[str] = Field(default=None, description="Updated description")
    caller_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Plugin identity context (e.g. slack_user_id, channel_id)",
    )

    @model_validator(mode="after")
    def require_at_least_one_data_field(self) -> "LocationUpdateRequest":
        """Reject empty updates (all data fields are None)."""
        data_fields = [
            self.name,
            self.address_1,
            self.city,
            self.state,
            self.postal_code,
            self.latitude,
            self.longitude,
            self.phone,
            self.email,
            self.website,
            self.description,
        ]
        if all(f is None for f in data_fields):
            raise ValueError("At least one data field must be provided")
        return self


class LocationUpdateResponse(BaseModel):
    """Response after updating a location."""

    location_id: str
    source_id: str
    audit_id: str
    message: str = "Location updated successfully"


# --- Delete / Restore ---


class SoftDeleteRequest(BaseModel):
    """Request body for soft-deleting a location."""

    reason: Optional[str] = Field(
        default=None, min_length=1, description="Reason for soft-deleting"
    )
    caller_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Plugin identity context",
    )


class RestoreRequest(BaseModel):
    """Request body for restoring a soft-deleted location."""

    reason: Optional[str] = Field(
        default=None, min_length=1, description="Reason for restoring"
    )
    caller_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Plugin identity context",
    )


class MutationResponse(BaseModel):
    """Generic response for delete/restore mutations."""

    location_id: str
    audit_id: str
    message: str


# --- History ---


class AuditEntry(BaseModel):
    """A single audit trail entry."""

    id: str
    location_id: str
    action: Literal["update", "soft_delete", "restore", "create"]
    changed_fields: Optional[List[str]] = None
    previous_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    api_key_id: Optional[str] = None
    api_key_name: Optional[str] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    caller_context: Optional[Dict[str, Any]] = None
    created_at: datetime


class HistoryResponse(BaseModel):
    """Audit history for a location."""

    location_id: str
    entries: List[AuditEntry]
    total: int = Field(ge=0)
