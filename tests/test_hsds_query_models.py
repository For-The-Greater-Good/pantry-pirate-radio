"""Tests for HSDS query parameter models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.hsds.query import (
    GeoBoundingBox,
    GeoPoint,
    LocationQueryParams,
    OrganizationQueryParams,
    PaginationParams,
    ServiceAtLocationQueryParams,
    ServiceQueryParams,
)


def test_pagination_params():
    """Test PaginationParams validation."""
    # Test defaults
    params = PaginationParams()
    assert params.page == 1
    assert params.per_page == 25

    # Test custom values
    params = PaginationParams(page=2, per_page=50)
    assert params.page == 2
    assert params.per_page == 50

    # Test invalid values
    with pytest.raises(ValidationError) as exc_info:
        PaginationParams(page=0)  # Invalid: must be >= 1
    assert "Input should be greater than or equal to 1" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        PaginationParams(per_page=0)  # Invalid: must be >= 1
    assert "Input should be greater than or equal to 1" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        PaginationParams(per_page=101)  # Invalid: must be <= 100
    assert "Input should be less than or equal to 100" in str(exc_info.value)


def test_geo_point():
    """Test GeoPoint validation."""
    # Test valid coordinates
    point = GeoPoint(latitude=37.7749, longitude=-122.4194)
    assert point.latitude == 37.7749
    assert point.longitude == -122.4194

    # Test invalid coordinates
    with pytest.raises(ValidationError) as exc_info:
        GeoPoint(latitude=91, longitude=0)  # Invalid latitude
    assert "Latitude must be between -90 and 90 degrees" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        GeoPoint(latitude=0, longitude=181)  # Invalid longitude
    assert "Longitude must be between -180 and 180 degrees" in str(exc_info.value)


def test_geo_bounding_box():
    """Test GeoBoundingBox validation."""
    # Test valid bounding box
    bbox = GeoBoundingBox(
        min_latitude=37.7,
        max_latitude=37.8,
        min_longitude=-122.5,
        max_longitude=-122.3,
    )
    assert bbox.min_latitude == 37.7
    assert bbox.max_latitude == 37.8
    assert bbox.min_longitude == -122.5
    assert bbox.max_longitude == -122.3

    # Test invalid coordinates
    with pytest.raises(ValidationError) as exc_info:
        GeoBoundingBox(
            min_latitude=91,  # Invalid
            max_latitude=37.8,
            min_longitude=-122.5,
            max_longitude=-122.3,
        )
    assert "Minimum latitude must be between -90 and 90 degrees" in str(exc_info.value)

    # Test invalid relationships
    with pytest.raises(ValidationError) as exc_info:
        GeoBoundingBox(
            min_latitude=38.0,  # Greater than max_latitude
            max_latitude=37.8,
            min_longitude=-122.5,
            max_longitude=-122.3,
        )
    assert "Minimum latitude cannot be greater than maximum latitude" in str(
        exc_info.value
    )

    with pytest.raises(ValidationError) as exc_info:
        GeoBoundingBox(
            min_latitude=37.7,
            max_latitude=37.8,
            min_longitude=-122.2,  # Greater than max_longitude
            max_longitude=-122.3,
        )
    assert "Minimum longitude cannot be greater than maximum longitude" in str(
        exc_info.value
    )


def test_service_query_params():
    """Test ServiceQueryParams validation."""
    org_id = uuid4()
    now = datetime.now(UTC)

    # Test all parameters
    params = ServiceQueryParams(
        page=1,
        per_page=25,
        organization_id=org_id,
        status="active",
        location=GeoPoint(latitude=37.7749, longitude=-122.4194),
        radius_miles=5.0,
        bbox=GeoBoundingBox(
            min_latitude=37.7,
            max_latitude=37.8,
            min_longitude=-122.5,
            max_longitude=-122.3,
        ),
        updated_since=now,
        include_locations=True,
    )
    assert params.organization_id == org_id
    assert params.status == "active"
    assert params.location is not None
    assert params.location.latitude == 37.7749
    assert params.radius_miles == 5.0
    assert params.updated_since == now
    assert params.include_locations is True

    # Test invalid status
    with pytest.raises(ValidationError) as exc_info:
        ServiceQueryParams(status="invalid")  # Invalid status
    assert "String should match pattern" in str(exc_info.value)

    # Test invalid radius
    with pytest.raises(ValidationError) as exc_info:
        ServiceQueryParams(radius_miles=-1)  # Invalid: must be >= 0
    assert "Input should be greater than or equal to 0" in str(exc_info.value)


def test_organization_query_params():
    """Test OrganizationQueryParams validation."""
    now = datetime.now(UTC)

    # Test all parameters
    params = OrganizationQueryParams(
        page=1,
        per_page=25,
        name="Food Bank",
        location=GeoPoint(latitude=37.7749, longitude=-122.4194),
        radius_miles=5.0,
        updated_since=now,
        include_services=True,
    )
    assert params.name == "Food Bank"
    assert params.location is not None
    assert params.location.latitude == 37.7749
    assert params.radius_miles == 5.0
    assert params.updated_since == now
    assert params.include_services is True


def test_location_query_params():
    """Test LocationQueryParams validation."""
    org_id = uuid4()
    service_id = uuid4()
    now = datetime.now(UTC)

    # Test all parameters
    params = LocationQueryParams(
        page=1,
        per_page=25,
        organization_id=org_id,
        service_id=service_id,
        location=GeoPoint(latitude=37.7749, longitude=-122.4194),
        radius_miles=5.0,
        bbox=GeoBoundingBox(
            min_latitude=37.7,
            max_latitude=37.8,
            min_longitude=-122.5,
            max_longitude=-122.3,
        ),
        updated_since=now,
        include_services=True,
    )
    assert params.organization_id == org_id
    assert params.service_id == service_id
    assert params.location is not None
    assert params.location.latitude == 37.7749
    assert params.radius_miles == 5.0
    assert params.updated_since == now
    assert params.include_services is True


def test_service_at_location_query_params():
    """Test ServiceAtLocationQueryParams validation."""
    service_id = uuid4()
    location_id = uuid4()
    org_id = uuid4()

    # Test all parameters
    params = ServiceAtLocationQueryParams(
        page=1,
        per_page=25,
        service_id=service_id,
        location_id=location_id,
        organization_id=org_id,
        include_details=True,
    )
    assert params.service_id == service_id
    assert params.location_id == location_id
    assert params.organization_id == org_id
    assert params.include_details is True


def test_query_params_defaults():
    """Test default values for query parameters."""
    # Test ServiceQueryParams defaults
    service_params = ServiceQueryParams()
    assert service_params.page == 1
    assert service_params.per_page == 25
    assert service_params.organization_id is None
    assert service_params.status is None
    assert service_params.location is None
    assert service_params.radius_miles is None
    assert service_params.bbox is None
    assert service_params.updated_since is None
    assert service_params.include_locations is False

    # Test OrganizationQueryParams defaults
    org_params = OrganizationQueryParams()
    assert org_params.page == 1
    assert org_params.per_page == 25
    assert org_params.name is None
    assert org_params.location is None
    assert org_params.radius_miles is None
    assert org_params.updated_since is None
    assert org_params.include_services is False

    # Test LocationQueryParams defaults
    location_params = LocationQueryParams()
    assert location_params.page == 1
    assert location_params.per_page == 25
    assert location_params.organization_id is None
    assert location_params.service_id is None
    assert location_params.location is None
    assert location_params.radius_miles is None
    assert location_params.bbox is None
    assert location_params.updated_since is None
    assert location_params.include_services is False

    # Test ServiceAtLocationQueryParams defaults
    sal_params = ServiceAtLocationQueryParams()
    assert sal_params.page == 1
    assert sal_params.per_page == 25
    assert sal_params.service_id is None
    assert sal_params.location_id is None
    assert sal_params.organization_id is None
    assert sal_params.include_details is False
