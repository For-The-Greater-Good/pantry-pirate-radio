"""ServiceAtLocation model for HSDS specification."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .base import HSDSBaseModel


class ServiceAtLocation(HSDSBaseModel):
    """ServiceAtLocation model with all required fields."""

    service_id: UUID = Field(
        ...,
        title="Service Identifier",
        description="The identifier of the service delivered at this location",
    )
    location_id: UUID = Field(
        ...,
        title="Location Identifier",
        description="The identifier of the location where the service is delivered",
    )
    description: str | None = Field(
        default=None,
        title="Description",
        description="Description of the service at this specific location",
    )


class ServiceAtLocationCreate(BaseModel):
    """ServiceAtLocation creation model."""

    service_id: UUID = Field(
        ...,
        title="Service Identifier",
        description="The identifier of the service delivered at this location",
    )
    location_id: UUID = Field(
        ...,
        title="Location Identifier",
        description="The identifier of the location where the service is delivered",
    )
    description: str | None = Field(
        default=None,
        title="Description",
        description="Description of the service at this specific location",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "service_id": "ac148810-d857-441c-9679-408f346de14b",
                "location_id": "b6f88961-4a68-4bf9-9b12-86b2e6f677f1",
                "description": "Primary location for this service",
            }
        },
    )


class ServiceAtLocationUpdate(BaseModel):
    """ServiceAtLocation update model with all fields optional."""

    service_id: UUID | None = None
    location_id: UUID | None = None
    description: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "description": "Updated service location description",
            }
        },
    )
