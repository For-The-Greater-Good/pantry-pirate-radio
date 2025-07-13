"""Service model for HSDS specification."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from .base import HSDSBaseModel


class Service(HSDSBaseModel):
    """Service model with all required fields."""

    organization_id: UUID = Field(
        ...,
        title="Organization Identifier",
        description="The identifier of the organization that provides this service",
        examples=["d9d5e0f5-d3ce-4f73-9a2f-4dd0ecc6c610"],
    )
    program_id: UUID | None = Field(
        default=None,
        title="Program Identifier",
        description="The identifier of the program this service is delivered under",
    )
    name: str = Field(
        ...,
        title="Name",
        description="The official or public name of the service",
        examples=["Community Counselling"],
    )
    alternate_name: str | None = Field(
        default=None,
        title="Alternate Name",
        description="An alternative name for this service",
    )
    description: str = Field(
        ...,
        title="Description",
        description="A free text description of the service",
        examples=["Counselling Services provided by trained professionals..."],
    )
    url: HttpUrl | None = Field(
        default=None,
        title="URL",
        description="URL of the service",
        examples=["http://example.com/counselling"],
    )
    email: EmailStr | None = Field(
        default=None,
        title="Email",
        description="Email address for contacting the service provider",
        examples=["email@example.com"],
    )
    status: str = Field(
        ...,
        title="Status",
        description="The current status of the service",
        examples=["active"],
        pattern="^(active|inactive|defunct|temporarily closed)$",
    )
    interpretation_services: str | None = Field(
        default=None,
        title="Interpretation Services",
        description="Description of interpretation services available",
    )
    application_process: str | None = Field(
        default=None,
        title="Application Process",
        description="Steps needed to access this service",
    )
    fees_description: str | None = Field(
        default=None,
        title="Fees Description",
        description="Description of any charges for service users",
    )
    accreditations: str | None = Field(
        default=None,
        title="Accreditations",
        description="Description of any accreditations",
    )
    eligibility_description: str | None = Field(
        default=None,
        title="Eligibility Description",
        description="Description of eligible service users",
        examples=["This service is intended for all people aged 12 and over..."],
    )
    minimum_age: int | None = Field(
        default=None,
        title="Minimum Age",
        description="Minimum age for eligibility",
        ge=0,
        examples=[12],
    )
    maximum_age: int | None = Field(
        default=None,
        title="Maximum Age",
        description="Maximum age for eligibility",
        ge=0,
        examples=[100],
    )
    assured_date: datetime | None = Field(
        default=None,
        title="Assured Date",
        description="Date the service information was last checked",
    )
    assurer_email: EmailStr | None = Field(
        default=None,
        title="Assurer Email",
        description="Contact email for person/org who last assured the service",
    )
    alert: str | None = Field(
        default=None,
        title="Alert",
        description="Short term alerts concerning the service",
    )
    licenses: str | None = Field(
        default=None,
        title="Licenses",
        description="DEPRECATED: An organization may have a license issued by a government entity to operate legally",
    )
    wait_time: str | None = Field(
        default=None,
        title="Wait Time",
        description="DEPRECATED: The time a client may expect to wait before receiving a service",
    )
    fees: str | None = Field(
        default=None,
        title="Fees",
        description="DEPRECATED: Details of any charges for service users to access this service",
    )


class ServiceCreate(BaseModel):
    """Service creation model with optional id."""

    organization_id: UUID = Field(
        ...,
        title="Organization Identifier",
        description="The identifier of the organization that provides this service",
        examples=["d9d5e0f5-d3ce-4f73-9a2f-4dd0ecc6c610"],
    )
    program_id: UUID | None = Field(
        default=None,
        title="Program Identifier",
        description="The identifier of the program this service is delivered under",
    )
    name: str = Field(
        ...,
        title="Name",
        description="The official or public name of the service",
        examples=["Community Counselling"],
    )
    alternate_name: str | None = Field(
        default=None,
        title="Alternate Name",
        description="An alternative name for this service",
    )
    description: str = Field(
        ...,
        title="Description",
        description="A free text description of the service",
        examples=["Counselling Services provided by trained professionals..."],
    )
    url: HttpUrl | None = Field(
        default=None,
        title="URL",
        description="URL of the service",
        examples=["http://example.com/counselling"],
    )
    email: EmailStr | None = Field(
        default=None,
        title="Email",
        description="Email address for contacting the service provider",
        examples=["email@example.com"],
    )
    status: str = Field(
        ...,
        title="Status",
        description="The current status of the service",
        examples=["active"],
        pattern="^(active|inactive|defunct|temporarily closed)$",
    )
    interpretation_services: str | None = Field(
        default=None,
        title="Interpretation Services",
        description="Description of interpretation services available",
    )
    application_process: str | None = Field(
        default=None,
        title="Application Process",
        description="Steps needed to access this service",
    )
    fees_description: str | None = Field(
        default=None,
        title="Fees Description",
        description="Description of any charges for service users",
    )
    accreditations: str | None = Field(
        default=None,
        title="Accreditations",
        description="Description of any accreditations",
    )
    eligibility_description: str | None = Field(
        default=None,
        title="Eligibility Description",
        description="Description of eligible service users",
        examples=["This service is intended for all people aged 12 and over..."],
    )
    minimum_age: int | None = Field(
        default=None,
        title="Minimum Age",
        description="Minimum age for eligibility",
        ge=0,
        examples=[12],
    )
    maximum_age: int | None = Field(
        default=None,
        title="Maximum Age",
        description="Maximum age for eligibility",
        ge=0,
        examples=[100],
    )
    assured_date: datetime | None = Field(
        default=None,
        title="Assured Date",
        description="Date the service information was last checked",
    )
    assurer_email: EmailStr | None = Field(
        default=None,
        title="Assurer Email",
        description="Contact email for person/org who last assured the service",
    )
    alert: str | None = Field(
        default=None,
        title="Alert",
        description="Short term alerts concerning the service",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "organization_id": "d9d5e0f5-d3ce-4f73-9a2f-4dd0ecc6c610",
                "name": "Community Counselling",
                "description": "Counselling Services provided by trained professionals...",
                "status": "active",
            }
        },
    )


class ServiceUpdate(BaseModel):
    """Service update model with all fields optional."""

    organization_id: UUID | None = None
    program_id: UUID | None = None
    name: str | None = None
    alternate_name: str | None = None
    description: str | None = None
    url: HttpUrl | None = None
    email: EmailStr | None = None
    status: str | None = Field(
        default=None,
        pattern="^(active|inactive|defunct|temporarily closed)$",
    )
    interpretation_services: str | None = None
    application_process: str | None = None
    fees_description: str | None = None
    accreditations: str | None = None
    eligibility_description: str | None = None
    minimum_age: int | None = Field(default=None, ge=0)
    maximum_age: int | None = Field(default=None, ge=0)
    assured_date: datetime | None = None
    assurer_email: EmailStr | None = None
    alert: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Updated Community Counselling",
                "description": "Updated counselling services description...",
                "status": "temporarily closed",
            }
        },
    )
