"""Tests for HSDS response models."""

from typing import Any, Dict
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.hsds.response import (
    LocationResponse,
    MetadataResponse,
    OrganizationResponse,
    Page,
    ServiceAtLocationResponse,
    ServiceResponse,
)


def test_page_model():
    """Test Page model validation."""
    data: Dict[str, Any] = {
        "count": 25,
        "total": 123,
        "per_page": 25,
        "current_page": 1,
        "page": 1,  # Add required page field
        "total_pages": 5,
        "links": {
            "first": "http://example.com/api/v1/services?page=1",
            "last": "http://example.com/api/v1/services?page=5",
            "next": "http://example.com/api/v1/services?page=2",
            "prev": None,
        },
        "data": [],
    }
    page = Page[ServiceResponse](**data)
    assert page.count == 25
    assert page.total == 123
    assert page.current_page == 1
    assert page.total_pages == 5
    assert page.links["next"] is not None
    assert page.links["prev"] is None

    # Test invalid values
    with pytest.raises(ValidationError) as exc_info:
        Page[ServiceResponse](
            count=-1,  # Invalid: must be >= 0
            total=123,
            per_page=25,
            current_page=1,
            page=1,
            total_pages=5,
            links={},
            data=[],
        )
    assert "Input should be greater than or equal to 0" in str(exc_info.value)


def test_metadata_response():
    """Test MetadataResponse model validation."""
    data: Dict[str, Any] = {
        "last_updated": "2024-02-06T20:46:26Z",
        "coverage_area": "San Francisco Bay Area",
        "data_source": "Community Food Bank API",
        "license": "CC BY-SA 4.0",
    }
    metadata = MetadataResponse(**data)
    assert metadata.last_updated == "2024-02-06T20:46:26Z"
    assert metadata.coverage_area == "San Francisco Bay Area"
    assert metadata.data_source == "Community Food Bank API"
    assert metadata.license == "CC BY-SA 4.0"


def test_service_response():
    """Test ServiceResponse model validation."""
    service_id = uuid4()
    org_id = uuid4()
    data: Dict[str, Any] = {
        "id": service_id,
        "organization_id": org_id,
        "name": "Food Pantry Service",
        "description": "Weekly food distribution",
        "url": "http://example.com/food-pantry",
        "email": "pantry@example.com",
        "status": "active",
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    service = ServiceResponse(**data)
    assert service.id == service_id
    assert service.organization_id == org_id
    assert service.name == "Food Pantry Service"
    assert service.status == "active"
    assert service.metadata is not None
    assert service.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_organization_response():
    """Test OrganizationResponse model validation."""
    org_id = uuid4()
    data: Dict[str, Any] = {
        "id": org_id,
        "name": "Community Food Bank",
        "description": "Local food bank serving the community",
        "url": "http://example.com/food-bank",
        "email": "info@example.com",
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    org = OrganizationResponse(**data)
    assert org.id == org_id
    assert org.name == "Community Food Bank"
    assert org.metadata is not None
    assert org.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_location_response():
    """Test LocationResponse model validation."""
    location_id = uuid4()
    data: Dict[str, Any] = {
        "id": location_id,
        "name": "Downtown Food Pantry",
        "description": "Main distribution center",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    location = LocationResponse(**data)
    assert location.id == location_id
    assert location.name == "Downtown Food Pantry"
    assert location.latitude == 37.7749
    assert location.longitude == -122.4194
    assert location.metadata is not None
    assert location.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_service_at_location_response():
    """Test ServiceAtLocationResponse model validation."""
    service_id = uuid4()
    location_id = uuid4()
    data: Dict[str, Any] = {
        "id": uuid4(),
        "service_id": service_id,
        "location_id": location_id,
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    sal = ServiceAtLocationResponse(**data)
    assert sal.service_id == service_id
    assert sal.location_id == location_id
    assert sal.metadata is not None
    assert sal.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_nested_relationships():
    """Test nested relationship handling in response models."""
    service_id = uuid4()
    org_id = uuid4()
    location_id = uuid4()

    # Create a service with a location
    service_data: Dict[str, Any] = {
        "id": service_id,
        "organization_id": org_id,
        "name": "Food Pantry Service",
        "description": "Weekly food distribution",
        "status": "active",
        "locations": [
            {
                "id": location_id,
                "name": "Downtown Location",
                "latitude": 37.7749,
                "longitude": -122.4194,
            }
        ],
    }
    service = ServiceResponse(**service_data)
    assert service.locations is not None
    assert len(service.locations) == 1
    assert service.locations[0].id == location_id
    assert service.locations[0].latitude == 37.7749

    # Create an organization with services
    org_data: Dict[str, Any] = {
        "id": org_id,
        "name": "Community Food Bank",
        "services": [service_data],
    }
    org = OrganizationResponse(**org_data)
    assert org.services is not None
    assert len(org.services) == 1
    assert org.services[0].id == service_id
    assert org.services[0].locations is not None
    assert len(org.services[0].locations) == 1
    assert org.services[0].locations[0].id == location_id


def test_response_model_defaults():
    """Test default values in response models."""
    service = ServiceResponse(
        id=uuid4(),
        organization_id=uuid4(),
        name="Test Service",
        description="Test Description",
        status="active",
    )
    assert service.url is None
    assert service.email is None
    assert service.locations is None
    assert service.metadata is None

    org = OrganizationResponse(
        id=uuid4(),
        name="Test Organization",
    )
    assert org.description is None
    assert org.url is None
    assert org.email is None
    assert org.services is None
    assert org.metadata is None

    location = LocationResponse(
        id=uuid4(),
        name="Test Location",
    )
    assert location.description is None
    assert location.latitude is None
    assert location.longitude is None
    assert location.services is None
    assert location.metadata is None
