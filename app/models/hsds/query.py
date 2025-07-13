"""Query parameter models for HSDS API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PaginationParams(BaseModel):
    """Common pagination parameters."""

    page: int = Field(
        default=1,
        title="Page Number",
        description="Page number to retrieve",
        ge=1,
        examples=[1],
    )
    per_page: int = Field(
        default=25,
        title="Items Per Page",
        description="Number of items to return per page",
        ge=1,
        le=100,
        examples=[25],
    )


class GeoPoint(BaseModel):
    """Geographic point coordinates."""

    latitude: float = Field(
        ...,
        title="Latitude",
        description="Latitude coordinate",
        examples=[37.7749],
    )
    longitude: float = Field(
        ...,
        title="Longitude",
        description="Longitude coordinate",
        examples=[-122.4194],
    )

    @model_validator(mode="after")
    def validate_coordinates(self) -> "GeoPoint":
        """Validate coordinate ranges."""
        if not -90 <= self.latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if not -180 <= self.longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        return self


class GeoBoundingBox(BaseModel):
    """Geographic bounding box."""

    min_latitude: float = Field(
        ...,
        title="Minimum Latitude",
        description="Southern boundary of the box",
        examples=[37.7],
    )
    max_latitude: float = Field(
        ...,
        title="Maximum Latitude",
        description="Northern boundary of the box",
        examples=[37.8],
    )
    min_longitude: float = Field(
        ...,
        title="Minimum Longitude",
        description="Western boundary of the box",
        examples=[-122.5],
    )
    max_longitude: float = Field(
        ...,
        title="Maximum Longitude",
        description="Eastern boundary of the box",
        examples=[-122.3],
    )

    @model_validator(mode="after")
    def validate_coordinates(self) -> "GeoBoundingBox":
        """Validate coordinate ranges and relationships."""
        if not -90 <= self.min_latitude <= 90:
            raise ValueError("Minimum latitude must be between -90 and 90 degrees")
        if not -90 <= self.max_latitude <= 90:
            raise ValueError("Maximum latitude must be between -90 and 90 degrees")
        if not -180 <= self.min_longitude <= 180:
            raise ValueError("Minimum longitude must be between -180 and 180 degrees")
        if not -180 <= self.max_longitude <= 180:
            raise ValueError("Maximum longitude must be between -180 and 180 degrees")
        if self.min_latitude > self.max_latitude:
            raise ValueError("Minimum latitude cannot be greater than maximum latitude")
        if self.min_longitude > self.max_longitude:
            raise ValueError(
                "Minimum longitude cannot be greater than maximum longitude"
            )
        return self


class ServiceQueryParams(PaginationParams):
    """Query parameters for service endpoints."""

    organization_id: UUID | None = Field(
        default=None,
        title="Organization ID",
        description="Filter by organization ID",
    )
    status: str | None = Field(
        default=None,
        title="Status",
        description="Filter by service status",
        pattern="^(active|inactive|defunct|temporarily closed)$",
    )
    location: GeoPoint | None = Field(
        default=None,
        title="Location",
        description="Filter by geographic point and radius",
    )
    radius_miles: float | None = Field(
        default=None,
        title="Radius (Miles)",
        description="Radius in miles from location point",
        ge=0,
        le=100,
        examples=[5],
    )
    bbox: GeoBoundingBox | None = Field(
        default=None,
        title="Bounding Box",
        description="Filter by geographic bounding box",
    )
    updated_since: datetime | None = Field(
        default=None,
        title="Updated Since",
        description="Filter by last update timestamp",
    )
    include_locations: bool = Field(
        default=False,
        title="Include Locations",
        description="Include location details in response",
    )


class OrganizationQueryParams(PaginationParams):
    """Query parameters for organization endpoints."""

    name: str | None = Field(
        default=None,
        title="Name",
        description="Filter by organization name",
    )
    location: GeoPoint | None = Field(
        default=None,
        title="Location",
        description="Filter by geographic point and radius",
    )
    radius_miles: float | None = Field(
        default=None,
        title="Radius (Miles)",
        description="Radius in miles from location point",
        ge=0,
        le=100,
        examples=[5],
    )
    updated_since: datetime | None = Field(
        default=None,
        title="Updated Since",
        description="Filter by last update timestamp",
    )
    include_services: bool = Field(
        default=False,
        title="Include Services",
        description="Include service details in response",
    )


class LocationQueryParams(PaginationParams):
    """Query parameters for location endpoints."""

    organization_id: UUID | None = Field(
        default=None,
        title="Organization ID",
        description="Filter by organization ID",
    )
    service_id: UUID | None = Field(
        default=None,
        title="Service ID",
        description="Filter by service ID",
    )
    location: GeoPoint | None = Field(
        default=None,
        title="Location",
        description="Filter by geographic point and radius",
    )
    radius_miles: float | None = Field(
        default=None,
        title="Radius (Miles)",
        description="Radius in miles from location point",
        ge=0,
        le=100,
        examples=[5],
    )
    bbox: GeoBoundingBox | None = Field(
        default=None,
        title="Bounding Box",
        description="Filter by geographic bounding box",
    )
    updated_since: datetime | None = Field(
        default=None,
        title="Updated Since",
        description="Filter by last update timestamp",
    )
    include_services: bool = Field(
        default=False,
        title="Include Services",
        description="Include service details in response",
    )


class ServiceAtLocationQueryParams(PaginationParams):
    """Query parameters for service-at-location endpoints."""

    service_id: UUID | None = Field(
        default=None,
        title="Service ID",
        description="Filter by service ID",
    )
    location_id: UUID | None = Field(
        default=None,
        title="Location ID",
        description="Filter by location ID",
    )
    organization_id: UUID | None = Field(
        default=None,
        title="Organization ID",
        description="Filter by organization ID",
    )
    include_details: bool = Field(
        default=False,
        title="Include Details",
        description="Include service and location details in response",
    )
