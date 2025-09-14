"""Response models for HSDS API endpoints."""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .base import HSDSBaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Generic pagination model for all paginated responses."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "count": 25,
                "total": 123,
                "per_page": 25,
                "current_page": 1,
                "total_pages": 5,
                "links": {
                    "first": "/api/v1/services?page=1",
                    "last": "/api/v1/services?page=5",
                    "next": "/api/v1/services?page=2",
                    "prev": None,
                },
                "data": [],
            }
        },
    )

    count: int = Field(
        ...,
        title="Count",
        description="Number of items in current page",
        ge=0,
        examples=[25],
    )
    total: int = Field(
        ...,
        title="Total",
        description="Total number of items across all pages",
        ge=0,
        examples=[123],
    )
    per_page: int = Field(
        ...,
        title="Per Page",
        description="Number of items per page",
        ge=1,
        examples=[25],
    )
    current_page: int = Field(
        ...,
        title="Current Page",
        description="Current page number",
        ge=1,
        examples=[1],
    )
    page: int = Field(
        ...,
        title="Page",
        description="Current page number (alias for current_page)",
        ge=1,
        examples=[1],
    )
    total_pages: int = Field(
        ...,
        title="Total Pages",
        description="Total number of pages",
        ge=1,
        examples=[5],
    )
    links: dict[str, HttpUrl | None] = Field(
        ...,
        title="Links",
        description="Navigation links for pagination",
    )
    data: list[T] = Field(
        ...,
        title="Data",
        description="List of items in current page",
    )


class MetadataResponse(BaseModel):
    """Common metadata for all responses."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "last_updated": "2024-02-06T20:46:26Z",
                "coverage_area": "San Francisco Bay Area",
                "data_source": "Community Food Bank API",
                "license": "CC BY-SA 4.0",
            }
        },
    )

    last_updated: str | None = Field(
        default=None,
        title="Last Updated",
        description="Timestamp of when the data was last updated",
    )
    coverage_area: str | None = Field(
        default=None,
        title="Coverage Area",
        description="Geographic area covered by this data",
    )
    data_source: str | None = Field(
        default=None,
        title="Data Source",
        description="Source of the data",
    )
    license: str | None = Field(
        default=None,
        title="License",
        description="License under which the data is provided",
    )


class BaseResponse(HSDSBaseModel):
    """Base response model with common fields."""

    metadata: MetadataResponse | None = Field(
        default=None,
        title="Metadata",
        description="Additional metadata about the response",
    )


class ScheduleInfo(BaseModel):
    """Schedule information for a location or service."""

    opens_at: str | None = Field(None, description="Opening time (e.g., '09:00')")
    closes_at: str | None = Field(None, description="Closing time (e.g., '17:00')")
    byday: str | None = Field(None, description="Days of week (e.g., 'MO,TU,WE,TH,FR')")
    freq: str | None = Field(None, description="Frequency (WEEKLY, MONTHLY)")
    description: str | None = Field(None, description="Schedule description")
    valid_from: str | None = Field(None, description="Start date of validity")
    valid_to: str | None = Field(None, description="End date of validity")
    notes: str | None = Field(None, description="Additional notes")

    model_config = ConfigDict(from_attributes=True)


class SourceInfo(BaseModel):
    """Information about a source that provided location data."""

    scraper: str = Field(..., description="Scraper/source identifier")
    name: str | None = Field(None, description="Location name from this source")
    phone: str | None = Field(None, description="Phone number from this source")
    email: str | None = Field(None, description="Email from this source")
    website: str | None = Field(None, description="Website from this source")
    address: str | None = Field(None, description="Address from this source")
    confidence_score: int = Field(50, description="Confidence score (0-100)")
    last_updated: str | None = Field(None, description="Last update timestamp")
    first_seen: str | None = Field(None, description="First seen timestamp")

    model_config = ConfigDict(from_attributes=True)


class ServiceResponse(BaseResponse):
    """Response model for Service endpoints."""

    organization_id: UUID
    name: str
    description: str | None = None
    url: HttpUrl | None = None
    email: str | None = None
    status: str = "active"
    alternate_name: str | None = None
    interpretation_services: str | None = None
    application_process: str | None = None
    fees_description: str | None = None
    wait_time: str | None = None
    schedules: list[ScheduleInfo] = Field(default_factory=list)
    locations: list["LocationResponse"] | None = None

    model_config = ConfigDict(from_attributes=True)


class OrganizationResponse(BaseResponse):
    """Response model for Organization endpoints."""

    name: str
    description: str | None = None
    url: HttpUrl | None = Field(None, alias="website")
    email: str | None = None
    alternate_name: str | None = None
    tax_status: str | None = None
    tax_id: str | None = None
    year_incorporated: int | None = None
    legal_status: str | None = None
    services: list[ServiceResponse] | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LocationResponse(BaseResponse):
    """Response model for Location endpoints."""

    name: str | None = None
    alternate_name: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    transportation: str | None = None
    external_identifier: str | None = None
    external_identifier_type: str | None = None
    location_type: str | None = None
    services: list[ServiceResponse] | None = None
    distance: str | None = None  # For radius search results
    sources: list[SourceInfo] | None = None  # Source-specific data
    source_count: int = Field(1, description="Number of sources for this location")
    schedules: list[ScheduleInfo] | None = None  # Schedule information

    model_config = ConfigDict(from_attributes=True)


class ServiceAtLocationResponse(BaseResponse):
    """Response model for ServiceAtLocation endpoints."""

    service_id: UUID
    location_id: UUID
    description: str | None = None  # Add description field
    service: ServiceResponse | None = None
    location: LocationResponse | None = None

    model_config = ConfigDict(from_attributes=True)


# Update forward references
ServiceResponse.model_rebuild()
OrganizationResponse.model_rebuild()
LocationResponse.model_rebuild()
ServiceAtLocationResponse.model_rebuild()
