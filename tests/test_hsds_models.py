"""Tests for HSDS models."""

import uuid
from datetime import UTC, datetime
from typing import Any, Dict

import pytest
from pydantic import ValidationError

from app.models import (
    Location,
    LocationCreate,
    Organization,
    OrganizationCreate,
    Service,
    ServiceAtLocation,
    ServiceAtLocationCreate,
    ServiceCreate,
)


def test_create_organization():
    """Test creating an organization."""
    org_id = uuid.uuid4()
    org_data: Dict[str, Any] = {
        "id": org_id,
        "name": "Food Bank Example",
        "description": "A food bank serving the community",
        "email": "contact@foodbank.example.org",
        "url": "https://foodbank.example.org",
        "tax_status": "501c3",
        "year_incorporated": 1990,
    }
    org = Organization(**org_data)
    assert org.name == org_data["name"]
    assert org.description == org_data["description"]
    assert org.tax_status == "501c3"


def test_create_service():
    """Test creating a service."""
    service_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service_data: Dict[str, Any] = {
        "id": service_id,
        "organization_id": org_id,
        "name": "Food Distribution",
        "description": "Weekly food distribution service",
        "status": "active",
        "url": "https://foodbank.example.org/services/distribution",
        "email": "distribution@foodbank.example.org",
        "minimum_age": 18,
    }
    service = Service(**service_data)
    assert service.name == service_data["name"]
    assert service.status == "active"
    assert service.minimum_age == 18


def test_create_location():
    """Test creating a location."""
    location_id = uuid.uuid4()
    location_data: Dict[str, Any] = {
        "id": location_id,
        "name": "Main Distribution Center",
        "description": "Primary food distribution location",
        "latitude": 42.3675294,
        "longitude": -71.186966,
        "transportation": "Bus routes 51, 52, and 53 stop directly in front",
        "location_type": "physical",  # Added required field
    }
    location = Location(**location_data)
    assert location.name == location_data["name"]
    assert location.latitude == 42.3675294
    assert location.longitude == -71.186966


def test_create_service_at_location():
    """Test linking a service to a location."""
    sal_id = uuid.uuid4()
    service_id = uuid.uuid4()
    location_id = uuid.uuid4()
    sal_data: Dict[str, Any] = {
        "id": sal_id,
        "service_id": service_id,
        "location_id": location_id,
        "description": "Main service location",
    }
    sal = ServiceAtLocation(**sal_data)
    assert sal.service_id == service_id
    assert sal.location_id == location_id


def test_invalid_coordinates():
    """Test validation of geographic coordinates."""
    with pytest.raises(ValidationError):
        Location(
            id=uuid.uuid4(),
            name="Invalid Location",
            latitude=100,  # Invalid: must be <= 90
            longitude=0,
            location_type="physical",  # Added required field
        )

    with pytest.raises(ValidationError):
        Location(
            id=uuid.uuid4(),
            name="Invalid Location",
            latitude=0,
            longitude=200,  # Invalid: must be <= 180
            location_type="physical",  # Added required field
        )


def test_invalid_service_status():
    """Test validation of service status."""
    with pytest.raises(ValidationError):
        Service(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            name="Test Service",
            description="Test description",
            status="invalid_status",  # Invalid: must be one of the allowed values
        )


def test_create_models():
    """Test create model variants."""
    # Organization
    org_create = OrganizationCreate(
        name="New Food Bank",
        description="A new food bank serving the community",
    )
    assert org_create.name == "New Food Bank"

    # Location
    loc_create = LocationCreate(
        name="New Location",
        latitude=42.0,
        longitude=-71.0,
        location_type="physical",  # Added required field
    )
    assert loc_create.latitude == 42.0

    # Service
    service_create = ServiceCreate(
        organization_id=uuid.uuid4(),
        name="New Service",
        description="A new service",
        status="active",
    )
    assert service_create.status == "active"

    # ServiceAtLocation
    sal_create = ServiceAtLocationCreate(
        service_id=uuid.uuid4(),
        location_id=uuid.uuid4(),
    )
    assert isinstance(sal_create.service_id, uuid.UUID)


def test_last_modified_tracking():
    """Test last_modified field handling."""
    now = datetime.now(UTC)
    org = Organization(
        id=uuid.uuid4(),
        name="Test Org",
        description="Test description",
        last_modified=now,
    )
    assert org.last_modified == now
