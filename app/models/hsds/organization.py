"""Organization model for HSDS specification."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from .base import HSDSBaseModel


class Organization(HSDSBaseModel):
    """Organization model with all required fields."""

    name: str = Field(
        ...,
        title="Name",
        description="The official or public name of the organization",
        examples=["Example Community Services"],
    )
    alternate_name: str | None = Field(
        default=None,
        title="Alternate Name",
        description="Alternative or commonly used name for the organization",
    )
    description: str = Field(
        ...,
        title="Description",
        description="A free text description of the organization",
        examples=["A community organization providing various support services..."],
    )
    email: EmailStr | None = Field(
        default=None,
        title="Email",
        description="The organization's primary email address",
        examples=["contact@example.org"],
    )
    url: HttpUrl | None = Field(
        default=None,
        title="URL",
        description="The organization's primary website",
        examples=["https://example.org"],
    )
    tax_status: str | None = Field(
        default=None,
        title="Tax Status",
        description="The organization's tax exempt status",
        examples=["501c3"],
    )
    tax_id: str | None = Field(
        default=None,
        title="Tax ID",
        description="The organization's tax identifier",
        examples=["12-3456789"],
    )
    year_incorporated: int | None = Field(
        default=None,
        title="Year Incorporated",
        description="The year the organization was legally incorporated",
        ge=1800,
        le=2100,
        examples=[1990],
    )
    legal_status: str | None = Field(
        default=None,
        title="Legal Status",
        description="The organization's legal status or structure",
        examples=["Registered Charity"],
    )
    logo: str | None = Field(
        default=None,
        title="Logo",
        description="A URL to an image associated with the organization",
        examples=[
            "https://openreferral.org/wp-content/uploads/2018/02/OpenReferral_Logo_Green-4-1.png"
        ],
    )
    uri: str | None = Field(
        default=None,
        title="URI",
        description="A persistent identifier to uniquely identify the organization",
        examples=["http://example.com"],
    )
    website: HttpUrl | None = Field(
        default=None,
        title="Website",
        description="The organization's primary website",
        examples=["https://example.org"],
    )
    parent_organization_id: UUID | None = Field(
        default=None,
        title="Parent Organization Identifier",
        description="The identifier of the organization's parent organization",
        examples=["cd09a387-91f4-4555-94ec-e799c35344cd"],
    )


class OrganizationCreate(BaseModel):
    """Organization creation model."""

    name: str = Field(
        ...,
        title="Name",
        description="The official or public name of the organization",
        examples=["Example Community Services"],
    )
    alternate_name: str | None = Field(
        default=None,
        title="Alternate Name",
        description="Alternative or commonly used name for the organization",
    )
    description: str = Field(
        ...,
        title="Description",
        description="A free text description of the organization",
        examples=["A community organization providing various support services..."],
    )
    email: EmailStr | None = Field(
        default=None,
        title="Email",
        description="The organization's primary email address",
        examples=["contact@example.org"],
    )
    url: HttpUrl | None = Field(
        default=None,
        title="URL",
        description="The organization's primary website",
        examples=["https://example.org"],
    )
    tax_status: str | None = Field(
        default=None,
        title="Tax Status",
        description="The organization's tax exempt status",
        examples=["501c3"],
    )
    tax_id: str | None = Field(
        default=None,
        title="Tax ID",
        description="The organization's tax identifier",
        examples=["12-3456789"],
    )
    year_incorporated: int | None = Field(
        default=None,
        title="Year Incorporated",
        description="The year the organization was legally incorporated",
        ge=1800,
        le=2100,
        examples=[1990],
    )
    legal_status: str | None = Field(
        default=None,
        title="Legal Status",
        description="The organization's legal status or structure",
        examples=["Registered Charity"],
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Example Community Services",
                "description": "A community organization providing various support services...",
                "email": "contact@example.org",
                "url": "https://example.org",
            }
        },
    )


class OrganizationUpdate(BaseModel):
    """Organization update model with all fields optional."""

    name: str | None = None
    alternate_name: str | None = None
    description: str | None = None
    email: EmailStr | None = None
    url: HttpUrl | None = None
    tax_status: str | None = None
    tax_id: str | None = None
    year_incorporated: int | None = Field(
        default=None,
        ge=1800,
        le=2100,
    )
    legal_status: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Updated Organization Name",
                "description": "Updated organization description...",
                "email": "new.contact@example.org",
            }
        },
    )
