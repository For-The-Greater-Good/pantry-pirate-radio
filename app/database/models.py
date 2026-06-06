"""SQLAlchemy models for HSDS entities."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
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

    # Canonical / soft-delete marker. The reconciler keeps one canonical
    # survivor per real-world location and flips merged-away duplicates to
    # is_canonical=FALSE. The DB column already existed; it was previously
    # unmapped on the ORM model, so the HSDS read repositories could not
    # filter on it and served duplicates. Public read paths default to
    # is_canonical=TRUE (see LocationRepository visibility filter).
    is_canonical = Column(Boolean, nullable=False, default=True)

    # Verification tracking (ppr-beacon quality gate)
    verified_by = Column(Text, nullable=True)  # 'auto', 'admin', 'source', 'claimed'
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # PostGIS geometry column for spatial queries (if GeoAlchemy2 is available)
    if HAS_GEOALCHEMY2:
        geometry: Optional[Geometry] = Column(
            Geometry("POINT", srid=4326),
            nullable=True,
        )
    else:
        # Fallback: use index on lat/lon columns for spatial queries
        pass

    # Submarine enrichment tracking
    submarine_last_crawled_at = Column(DateTime(timezone=True), nullable=True)
    submarine_last_status: Column[str] = Column(
        Enum(
            "success",
            "partial",
            "no_data",
            "error",
            "blocked",
            "staged",
            name="submarine_status_enum",
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
    organization = relationship("OrganizationModel", back_populates="locations")
    services_at_location = relationship(
        "ServiceAtLocationModel", back_populates="location"
    )
    schedules = relationship("ScheduleModel", back_populates="location")

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
    schedules = relationship("ScheduleModel", back_populates="service")


class ScheduleModel(Base):
    """Schedule model for HSDS specification."""

    __tablename__ = "schedule"

    id = Column(
        Text,
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    service_id = Column(Text, ForeignKey("service.id"), nullable=True)
    location_id = Column(Text, ForeignKey("location.id"), nullable=True)
    service_at_location_id = Column(
        Text, ForeignKey("service_at_location.id"), nullable=True
    )

    # Validity period
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)

    # Recurrence fields (iCalendar RRULE spec)
    dtstart = Column(Date, nullable=True)
    timezone = Column(Numeric, nullable=True)
    until = Column(Date, nullable=True)
    count = Column(Numeric, nullable=True)

    # Frequency enums
    wkst: Column[str | None] = Column(
        Enum("MO", "TU", "WE", "TH", "FR", "SA", "SU", name="schedule_wkst_enum"),
        nullable=True,
    )
    freq: Column[str | None] = Column(
        Enum("WEEKLY", "MONTHLY", name="schedule_freq_enum"),
        nullable=True,
    )

    interval = Column(Numeric, nullable=True)
    byday = Column(Text, nullable=True)
    byweekno = Column(Text, nullable=True)
    bymonthday = Column(Text, nullable=True)
    byyearday = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    # Opening hours
    opens_at = Column(Text, nullable=True)
    closes_at = Column(Text, nullable=True)
    schedule_link = Column(Text, nullable=True)
    attending_type = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    location = relationship("LocationModel", back_populates="schedules")
    service = relationship("ServiceModel", back_populates="schedules")
    service_at_location = relationship(
        "ServiceAtLocationModel", back_populates="schedules"
    )


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
    schedules = relationship("ScheduleModel", back_populates="service_at_location")


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


class FederationLogModel(Base):
    """Append-only verifiable federation log (design §6.2b).

    One row per published activity envelope. ``sequence`` is the dense, gapless
    Merkle leaf index — assigned under the §6.2b advisory lock scoped to ONLY
    ``SELECT MAX(sequence)+1 -> INSERT -> COMMIT`` (see ``app/federation/log.py``),
    never the reconciler's resource commit. ``leaf_hash`` is the ``sha256:``
    content address (the envelope ``id``) and the input to the RFC-6962 tree.
    ``preimage_canonical`` stores the EXACT JCS (RFC 8785) bytes that were hashed
    and signed, so the Merkle leaf is re-derived verbatim (a JSONB round-trip
    normalizes extreme-magnitude numbers and would break proofs);
    ``object_canonical`` retains the full envelope dict for queryability only.
    Append-only: rows are never updated or deleted (retention is archive-to-S3,
    never destruction — §6.2g).
    """

    __tablename__ = "federation_log"

    # The sha256: content address of the JCS-canonical envelope = the envelope
    # id and the Merkle leaf. Content-addressed primary key.
    leaf_hash = Column(Text, primary_key=True)

    # Dense, gapless leaf index (§6.2b). Assigned by the append helper, not a
    # SERIAL (a SERIAL gaps on rollback, which would break the Merkle tree).
    sequence = Column(BigInteger, nullable=False, unique=True, index=True)

    type = Column(Text, nullable=False)  # Update | Announce | Delete (§9)
    federation_id = Column(Text, nullable=False, index=True)  # history/{federation_id}
    object_canonical = Column(JSONB, nullable=False)  # the full §8.1 envelope dict
    # The EXACT canonical pre-image bytes that were hashed/signed at append time.
    # The Merkle leaf is re-derived from THESE bytes, never from object_canonical
    # (JSONB normalizes extreme-magnitude numbers, which would break proofs).
    preimage_canonical = Column(LargeBinary, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)  # RFC-3339 published
    origin_did = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
