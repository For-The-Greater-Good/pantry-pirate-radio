"""Base model for all HSDS models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HSDSBaseModel(BaseModel):
    """Base model for all HSDS models with common fields and configuration."""

    model_config = ConfigDict(
        from_attributes=True,  # Support ORM mode
        validate_assignment=True,  # Validate on attribute assignment
        extra="forbid",  # Forbid extra fields
        protected_namespaces=(),  # Allow field overrides in subclasses
        json_schema_extra={
            "example": {
                "id": "ac148810-d857-441c-9679-408f346de14b",
                "last_modified": "2023-03-15T10:30:45.123Z",
            }
        },
    )

    id: UUID = Field(
        ...,
        title="Identifier",
        description="Unique identifier for this record",
        examples=["ac148810-d857-441c-9679-408f346de14b"],
    )
    last_modified: datetime | None = Field(
        default=None,
        title="Last Modified",
        description="The datetime when this record was last modified",
        examples=["2023-03-15T10:30:45.123Z"],
    )
