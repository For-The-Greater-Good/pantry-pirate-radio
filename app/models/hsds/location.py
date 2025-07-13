"""Location model for HSDS specification."""

from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
)

from .base import HSDSBaseModel


class Location(HSDSBaseModel):
    """Location model with all required fields."""

    organization_id: UUID | None = Field(
        default=None,
        title="Organization Identifier",
        description="The identifier of the organization that operates at this location",
    )
    name: str | None = Field(
        default=None,
        title="Name",
        description="The name of the location",
        examples=["Main Office"],
    )
    alternate_name: str | None = Field(
        default=None,
        title="Alternate Name",
        description="An alternative name for the location",
    )
    description: str | None = Field(
        default=None,
        title="Description",
        description="A description of the location",
        examples=["Main office and service center"],
    )
    transportation: str | None = Field(
        default=None,
        title="Transportation",
        description="A description of how to get to the location using public transport",
    )
    latitude: float | None = Field(
        default=None,
        title="Latitude",
        description="The latitude of the location",
        examples=[42.3675294],
        ge=-90,
        le=90,
    )
    longitude: float | None = Field(
        default=None,
        title="Longitude",
        description="The longitude of the location",
        examples=[-71.186966],
        ge=-180,
        le=180,
    )
    url: AnyHttpUrl | None = Field(
        default=None,
        title="URL",
        description="If location_type is virtual, then this field represents the URL of a virtual location",
        examples=["http://example.com"],
    )
    external_identifier: str | None = Field(
        default=None,
        title="External Identifier",
        description="A third party identifier for the location",
        examples=["10092008082"],
    )
    external_identifier_type: str | None = Field(
        default=None,
        title="External Identifier Type",
        description="The scheme used for the location's external_identifier",
        examples=["UPRN"],
    )
    location_type: str = Field(
        ...,
        title="Location Type",
        description="The type of location",
        examples=["physical"],
        pattern="^(physical|postal|virtual)$",
    )


class LocationCreate(BaseModel):
    """Location creation model."""

    organization_id: UUID | None = Field(
        default=None,
        title="Organization Identifier",
        description="The identifier of the organization that operates at this location",
    )
    name: str | None = Field(
        default=None,
        title="Name",
        description="The name of the location",
        examples=["Main Office"],
    )
    alternate_name: str | None = Field(
        default=None,
        title="Alternate Name",
        description="An alternative name for the location",
    )
    description: str | None = Field(
        default=None,
        title="Description",
        description="A description of the location",
        examples=["Main office and service center"],
    )
    transportation: str | None = Field(
        default=None,
        title="Transportation",
        description="A description of how to get to the location using public transport",
    )
    latitude: float | None = Field(
        default=None,
        title="Latitude",
        description="The latitude of the location",
        examples=[42.3675294],
        ge=-90,
        le=90,
    )
    longitude: float | None = Field(
        default=None,
        title="Longitude",
        description="The longitude of the location",
        examples=[-71.186966],
        ge=-180,
        le=180,
    )

    url: AnyHttpUrl | None = Field(
        default=None,
        title="URL",
        description="If location_type is virtual, then this field represents the URL of a virtual location",
        examples=["http://example.com"],
    )
    external_identifier: str | None = Field(
        default=None,
        title="External Identifier",
        description="A third party identifier for the location",
        examples=["10092008082"],
    )
    external_identifier_type: str | None = Field(
        default=None,
        title="External Identifier Type",
        description="The scheme used for the location's external_identifier",
        examples=["UPRN"],
    )
    location_type: str = Field(
        ...,
        title="Location Type",
        description="The type of location",
        examples=["physical"],
        pattern="^(physical|postal|virtual)$",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Main Office",
                "description": "Main office and service center",
                "latitude": 42.3675294,
                "longitude": -71.186966,
            }
        },
    )


class LocationUpdate(BaseModel):
    """Location update model with all fields optional."""

    organization_id: UUID | None = None
    name: str | None = None
    alternate_name: str | None = None
    description: str | None = None
    transportation: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    url: AnyHttpUrl | None = Field(
        default=None,
        title="URL",
        description="If location_type is virtual, then this field represents the URL of a virtual location",
        examples=["http://example.com"],
    )
    external_identifier: str | None = Field(
        default=None,
        title="External Identifier",
        description="A third party identifier for the location",
        examples=["10092008082"],
    )
    external_identifier_type: str | None = Field(
        default=None,
        title="External Identifier Type",
        description="The scheme used for the location's external_identifier",
        examples=["UPRN"],
    )
    location_type: str = Field(
        ...,
        title="Location Type",
        description="The type of location",
        examples=["physical"],
        pattern="^(physical|postal|virtual)$",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Updated Office Name",
                "description": "Updated office description...",
                "latitude": 42.3675294,
                "longitude": -71.186966,
            }
        },
    )
