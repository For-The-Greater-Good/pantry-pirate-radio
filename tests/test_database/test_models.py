"""Test database models."""

import pytest
from datetime import datetime
from uuid import uuid4

from app.database.models import (
    OrganizationModel,
    LocationModel,
    ServiceModel,
    ServiceAtLocationModel,
    AddressModel,
)


class TestOrganizationModel:
    """Test OrganizationModel."""

    def test_organization_model_creation(self):
        """Test basic organization model creation."""
        org = OrganizationModel(
            id=uuid4(),
            name="Test Organization",
            description="Test Description",
            email="test@example.com",
            website="https://example.com",
        )

        assert org.name == "Test Organization"
        assert org.description == "Test Description"
        assert org.email == "test@example.com"
        assert org.website == "https://example.com"
        assert org.__tablename__ == "organization"

    def test_organization_model_defaults(self):
        """Test organization model with defaults."""
        org = OrganizationModel(
            name="Test Organization",
            description="Test Description",
        )

        assert org.name == "Test Organization"
        assert org.description == "Test Description"
        assert org.email is None
        assert org.website is None
        assert org.alternate_name is None


class TestLocationModel:
    """Test LocationModel."""

    def test_location_model_creation(self):
        """Test basic location model creation."""
        location = LocationModel(
            id=uuid4(),
            name="Test Location",
            description="Test Location Description",
            latitude=40.7128,
            longitude=-74.0060,
            location_type="physical",
        )

        assert location.name == "Test Location"
        assert location.description == "Test Location Description"
        assert location.latitude == 40.7128
        assert location.longitude == -74.0060
        assert location.location_type == "physical"
        assert location.__tablename__ == "location"

    def test_location_model_defaults(self):
        """Test location model with defaults."""
        location = LocationModel(
            name="Test Location",
        )

        assert location.name == "Test Location"
        # Note: default values are SQL defaults, not Python defaults
        # So they'll be None until inserted into database
        assert location.latitude is None
        assert location.longitude is None

    def test_location_model_init_with_coordinates(self):
        """Test location model initialization with coordinates."""
        # This tests the __init__ method, but we can't test PostGIS functions without a real DB
        location = LocationModel(
            name="Test Location",
            latitude=40.7128,
            longitude=-74.0060,
        )

        assert location.latitude == 40.7128
        assert location.longitude == -74.0060


class TestServiceModel:
    """Test ServiceModel."""

    def test_service_model_creation(self):
        """Test basic service model creation."""
        org_id = uuid4()
        service = ServiceModel(
            id=uuid4(),
            organization_id=org_id,
            name="Test Service",
            description="Test Service Description",
            status="active",
        )

        assert service.name == "Test Service"
        assert service.description == "Test Service Description"
        assert service.organization_id == org_id
        assert service.status == "active"
        assert service.__tablename__ == "service"

    def test_service_model_defaults(self):
        """Test service model with defaults."""
        org_id = uuid4()
        service = ServiceModel(
            organization_id=org_id,
            name="Test Service",
        )

        assert service.name == "Test Service"
        assert service.organization_id == org_id
        # Note: default values are SQL defaults, not Python defaults
        assert service.description is None


class TestServiceAtLocationModel:
    """Test ServiceAtLocationModel."""

    def test_service_at_location_model_creation(self):
        """Test basic service at location model creation."""
        service_id = uuid4()
        location_id = uuid4()
        sal = ServiceAtLocationModel(
            id=uuid4(),
            service_id=service_id,
            location_id=location_id,
            description="Service available at this location",
        )

        assert sal.service_id == service_id
        assert sal.location_id == location_id
        assert sal.description == "Service available at this location"
        assert sal.__tablename__ == "service_at_location"

    def test_service_at_location_model_minimal(self):
        """Test service at location model with minimal fields."""
        service_id = uuid4()
        location_id = uuid4()
        sal = ServiceAtLocationModel(
            service_id=service_id,
            location_id=location_id,
        )

        assert sal.service_id == service_id
        assert sal.location_id == location_id
        assert sal.description is None


class TestAddressModel:
    """Test AddressModel."""

    def test_address_model_creation(self):
        """Test basic address model creation."""
        location_id = uuid4()
        address = AddressModel(
            id=uuid4(),
            location_id=location_id,
            address_1="123 Main St",
            city="Anytown",
            state_province="NY",
            postal_code="12345",
            country="US",
            address_type="physical",
        )

        assert address.location_id == location_id
        assert address.address_1 == "123 Main St"
        assert address.city == "Anytown"
        assert address.state_province == "NY"
        assert address.postal_code == "12345"
        assert address.country == "US"
        assert address.address_type == "physical"
        assert address.__tablename__ == "address"

    def test_address_model_defaults(self):
        """Test address model with defaults."""
        location_id = uuid4()
        address = AddressModel(
            location_id=location_id,
            address_1="123 Main St",
            city="Anytown",
            state_province="NY",
            postal_code="12345",
            country="US",
        )

        # Note: default values are SQL defaults, not Python defaults
        assert address.attention is None
        assert address.address_2 is None
        assert address.region is None


class TestModelRelationships:
    """Test model relationships and table names."""

    def test_table_names(self):
        """Test that all models have correct table names."""
        assert OrganizationModel.__tablename__ == "organization"
        assert LocationModel.__tablename__ == "location"
        assert ServiceModel.__tablename__ == "service"
        assert ServiceAtLocationModel.__tablename__ == "service_at_location"
        assert AddressModel.__tablename__ == "address"

    def test_model_inheritance(self):
        """Test that models inherit from Base correctly."""
        from app.database.base import Base

        assert issubclass(OrganizationModel, Base)
        assert issubclass(LocationModel, Base)
        assert issubclass(ServiceModel, Base)
        assert issubclass(ServiceAtLocationModel, Base)
        assert issubclass(AddressModel, Base)
