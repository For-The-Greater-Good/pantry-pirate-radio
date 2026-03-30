"""Pydantic models for template rendering context."""

from __future__ import annotations

from pydantic import BaseModel


class Schedule(BaseModel):
    """Location schedule entry."""

    opens_at: str | None = None
    closes_at: str | None = None
    byday: str | None = None
    freq: str | None = None
    description: str | None = None
    notes: str | None = None


class Phone(BaseModel):
    """Phone number."""

    number: str
    type: str | None = None
    extension: str | None = None


class Language(BaseModel):
    """Supported language."""

    name: str
    code: str | None = None


class Accessibility(BaseModel):
    """Accessibility information."""

    description: str | None = None
    details: str | None = None
    url: str | None = None


class LocationDetail(BaseModel):
    """Full location data for rendering a location page."""

    id: str
    name: str
    organization_name: str | None = None
    organization_id: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    description: str | None = None
    transportation: str | None = None
    confidence_score: int = 0
    validation_status: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    schedules: list[Schedule] = []
    phones: list[Phone] = []
    languages: list[Language] = []
    accessibility: Accessibility | None = None
    slug: str = ""
    url: str = ""


class LocationSummary(BaseModel):
    """Compact location for listing pages."""

    id: str
    name: str
    organization_name: str | None = None
    address_1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    slug: str = ""
    url: str = ""
    confidence_score: int = 0
    verified_by: str | None = None


class StateSummary(BaseModel):
    """State-level aggregation for the homepage."""

    state: str
    state_full: str
    slug: str
    location_count: int
    city_count: int


class CitySummary(BaseModel):
    """City-level aggregation for state pages."""

    city: str
    state: str
    slug: str
    location_count: int


class OrgDetail(BaseModel):
    """Organization with its locations."""

    id: str
    name: str
    description: str | None = None
    email: str | None = None
    website: str | None = None
    slug: str = ""
    url: str = ""
    locations: list[LocationSummary] = []
