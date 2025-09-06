"""SQLAlchemy models for HSDS entities."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

# Try to import GeoAlchemy2, use fallback if not available
try:
    from geoalchemy2 import Geometry

    HAS_GEOALCHEMY2 = True
except ImportError:
    HAS_GEOALCHEMY2 = False

from .base import Base


class OrganizationModel(Base):
    """Organization model for HSDS specification."""

    __tablename__ = "organization"

    id = Column(
        Text,
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    alternate_name = Column(Text, nullable=True)
    description = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    website = Column(Text, nullable=True)
    tax_status = Column(Text, nullable=True)
    tax_id = Column(Text, nullable=True)
    year_incorporated = Column(Numeric, nullable=True)
    legal_status = Column(Text, nullable=True)

    # Validation fields (Issue #362)
    confidence_score = Column(Integer, nullable=True, default=50)
    validation_notes = Column(JSONB, nullable=True)
    validation_status: Column[str] = Column(  # type: ignore[assignment]
        Enum(
            "verified",
            "needs_review",
            "rejected",
            name="organization_validation_status_enum",
        ),
        nullable=True,
    )

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    services = relationship("ServiceModel", back_populates="organization")
    locations = relationship("LocationModel", back_populates="organization")


class LocationModel(Base):
    """Location model for HSDS specification."""

    __tablename__ = "location"

    id = Column(
        Text,
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    organization_id = Column(
        Text,
        ForeignKey("organization.id"),
        nullable=True,
    )
    name = Column(Text, nullable=True)
    alternate_name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    transportation = Column(Text, nullable=True)
    latitude = Column(Numeric, nullable=True)
    longitude = Column(Numeric, nullable=True)
    external_identifier = Column(Text, nullable=True)
    external_identifier_type = Column(Text, nullable=True)

    # Location type enum
    location_type: Column[str] = Column(  # type: ignore[assignment]
        Enum("physical", "postal", "virtual", name="location_location_type_enum"),
        nullable=False,
        default="physical",
    )

    # Validation fields (Issue #362)
    confidence_score = Column(Integer, nullable=True, default=50)
    validation_notes = Column(JSONB, nullable=True)
    validation_status: Column[str] = Column(  # type: ignore[assignment]
        Enum(
            "verified",
            "needs_review",
            "rejected",
            name="location_validation_status_enum",
        ),
        nullable=True,
    )
    geocoding_source = Column(Text, nullable=True)

    # PostGIS geometry column for spatial queries (if GeoAlchemy2 is available)
    if HAS_GEOALCHEMY2:
        geometry: Optional[Geometry] = Column(
            Geometry("POINT", srid=4326),
            nullable=True,
        )
    else:
        # Fallback: use index on lat/lon columns for spatial queries
        pass

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    organization = relationship("OrganizationModel", back_populates="locations")
    services_at_location = relationship(
        "ServiceAtLocationModel", back_populates="location"
    )

    def __init__(self, **kwargs):
        """Initialize location with geometry from lat/lon."""
        super().__init__(**kwargs)
        if HAS_GEOALCHEMY2 and self.latitude is not None and self.longitude is not None:
            self.geometry = func.ST_SetSRID(
                func.ST_MakePoint(self.longitude, self.latitude), 4326
            )


class ServiceModel(Base):
    """Service model for HSDS specification."""

    __tablename__ = "service"

    id = Column(
        Text,
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    organization_id = Column(
        Text,
        ForeignKey("organization.id"),
        nullable=False,
    )
    program_id = Column(Text, nullable=True)
    name = Column(Text, nullable=False)
    alternate_name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    interpretation_services = Column(Text, nullable=True)
    application_process = Column(Text, nullable=True)
    fees_description = Column(Text, nullable=True)
    wait_time = Column(Text, nullable=True)
    fees = Column(Text, nullable=True)
    accreditations = Column(Text, nullable=True)
    eligibility_description = Column(Text, nullable=True)
    minimum_age = Column(Numeric, nullable=True)
    maximum_age = Column(Numeric, nullable=True)
    assured_date = Column(Date, nullable=True)
    assurer_email = Column(Text, nullable=True)

    # Service status enum
    status: Column[str] = Column(  # type: ignore[assignment]
        Enum(
            "active",
            "inactive",
            "defunct",
            "temporarily closed",
            name="service_status_enum",
        ),
        nullable=False,
        default="active",
    )

    # Validation fields (Issue #362)
    confidence_score = Column(Integer, nullable=True, default=50)
    validation_notes = Column(JSONB, nullable=True)
    validation_status: Column[str] = Column(  # type: ignore[assignment]
        Enum(
            "verified",
            "needs_review",
            "rejected",
            name="service_validation_status_enum",
        ),
        nullable=True,
    )

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    organization = relationship("OrganizationModel", back_populates="services")
    locations = relationship("ServiceAtLocationModel", back_populates="service")


class ServiceAtLocationModel(Base):
    """Service at location model for HSDS specification."""

    __tablename__ = "service_at_location"

    id = Column(
        Text,
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    service_id = Column(
        Text,
        ForeignKey("service.id"),
        nullable=False,
    )
    location_id = Column(
        Text,
        ForeignKey("location.id"),
        nullable=False,
    )
    description = Column(Text, nullable=True)

    # Relationships
    service = relationship("ServiceModel", back_populates="locations")
    location = relationship("LocationModel", back_populates="services_at_location")


class AddressModel(Base):
    """Address model for HSDS specification."""

    __tablename__ = "address"

    id = Column(
        Text,
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    location_id = Column(
        Text,
        ForeignKey("location.id"),
        nullable=False,
    )
    attention = Column(Text, nullable=True)
    address_1 = Column(Text, nullable=False)
    address_2 = Column(Text, nullable=True)
    city = Column(Text, nullable=False)
    region = Column(Text, nullable=True)
    state_province = Column(Text, nullable=False)
    postal_code = Column(Text, nullable=False)
    country = Column(Text, nullable=False)

    # Address type enum
    address_type: Column[str] = Column(  # type: ignore[assignment]
        Enum("physical", "postal", "virtual", name="address_address_type_enum"),
        nullable=False,
        default="physical",
    )

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    location = relationship("LocationModel")
