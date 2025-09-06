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


class ServiceResponse(BaseResponse):
    """Response model for Service endpoints."""

    organization_id: UUID
    name: str
    description: str | None = None
    url: HttpUrl | None = None
    email: str | None = None
    status: str
    locations: list["LocationResponse"] | None = None

    model_config = ConfigDict(from_attributes=True)


class OrganizationResponse(BaseResponse):
    """Response model for Organization endpoints."""

    name: str
    description: str | None = None
    url: HttpUrl | None = Field(None, alias="website")
    email: str | None = None
    services: list[ServiceResponse] | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LocationResponse(BaseResponse):
    """Response model for Location endpoints."""

    name: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    services: list[ServiceResponse] | None = None
    distance: str | None = None  # For radius search results

    model_config = ConfigDict(from_attributes=True)


class ServiceAtLocationResponse(BaseResponse):
    """Response model for ServiceAtLocation endpoints."""

    service_id: UUID
    location_id: UUID
    service: ServiceResponse | None = None
    location: LocationResponse | None = None

    model_config = ConfigDict(from_attributes=True)


# Update forward references
ServiceResponse.model_rebuild()
OrganizationResponse.model_rebuild()
LocationResponse.model_rebuild()
ServiceAtLocationResponse.model_rebuild()
