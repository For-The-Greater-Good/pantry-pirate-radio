"""Comprehensive tests for API utilities to boost coverage."""

import pytest
from unittest.mock import Mock, MagicMock
from fastapi import Request
from datetime import datetime

from app.api.v1.utils import (
    create_pagination_links,
    calculate_pagination_metadata,
    validate_pagination_params,
    build_filter_dict,
    format_distance,
    create_error_response,
    extract_coordinates_from_query,
    create_metadata_response,
)


class TestCreatePaginationLinks:
    """Test pagination link creation."""

    def test_basic_pagination_links(self):
        """Test basic pagination link creation."""
        # Mock request
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/organizations"

        links = create_pagination_links(
            request=request, current_page=2, total_pages=5, per_page=25
        )

        assert (
            links["first"]
            == "http://localhost:8000/api/v1/organizations?page=1&per_page=25"
        )
        assert (
            links["last"]
            == "http://localhost:8000/api/v1/organizations?page=5&per_page=25"
        )
        assert (
            links["next"]
            == "http://localhost:8000/api/v1/organizations?page=3&per_page=25"
        )
        assert (
            links["prev"]
            == "http://localhost:8000/api/v1/organizations?page=1&per_page=25"
        )

    def test_pagination_links_with_extra_params(self):
        """Test pagination links with extra parameters."""
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/organizations"

        extra_params = {
            "name": "food bank",
            "include_services": True,
            "status": "active",
        }

        links = create_pagination_links(
            request=request,
            current_page=1,
            total_pages=3,
            per_page=10,
            extra_params=extra_params,
        )

        # Check that extra params are included
        assert "name=food+bank" in links["first"]
        assert "include_services=True" in links["first"]
        assert "status=active" in links["first"]

    def test_pagination_links_with_none_extra_params(self):
        """Test pagination links filtering out None values."""
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/locations"

        extra_params = {
            "organization_id": "123",
            "include_services": None,
            "status": "active",
            "location_type": None,
        }

        links = create_pagination_links(
            request=request,
            current_page=1,
            total_pages=2,
            per_page=25,
            extra_params=extra_params,
        )

        # Check that None values are filtered out
        assert "organization_id=123" in links["first"]
        assert "status=active" in links["first"]
        assert "include_services" not in links["first"]
        assert "location_type" not in links["first"]

    def test_pagination_links_first_page(self):
        """Test pagination links on first page."""
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/services"

        links = create_pagination_links(
            request=request, current_page=1, total_pages=5, per_page=25
        )

        assert links["prev"] is None  # No previous page
        assert links["next"] is not None

    def test_pagination_links_last_page(self):
        """Test pagination links on last page."""
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/services"

        links = create_pagination_links(
            request=request, current_page=5, total_pages=5, per_page=25
        )

        assert links["next"] is None  # No next page
        assert links["prev"] is not None

    def test_pagination_links_single_page(self):
        """Test pagination links with only one page."""
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/organizations"

        links = create_pagination_links(
            request=request, current_page=1, total_pages=1, per_page=25
        )

        assert links["prev"] is None
        assert links["next"] is None
        assert links["first"] == links["last"]

    def test_pagination_links_with_query_params_in_url(self):
        """Test pagination links when URL already has query parameters."""
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/organizations?existing=param"

        links = create_pagination_links(
            request=request, current_page=1, total_pages=2, per_page=25
        )

        # Should strip existing query params
        assert "existing=param" not in links["first"]
        assert "page=1" in links["first"]

    def test_pagination_links_none_extra_params(self):
        """Test pagination links with None extra_params."""
        request = Mock(spec=Request)
        request.url = "http://localhost:8000/api/v1/organizations"

        links = create_pagination_links(
            request=request,
            current_page=1,
            total_pages=2,
            per_page=25,
            extra_params=None,
        )

        assert "page=1" in links["first"]
        assert "per_page=25" in links["first"]


class TestCalculatePaginationMetadata:
    """Test pagination metadata calculation."""

    def test_basic_pagination_metadata(self):
        """Test basic pagination metadata calculation."""
        metadata = calculate_pagination_metadata(
            total_items=100, current_page=2, per_page=25
        )

        assert metadata["total_pages"] == 4
        assert metadata["skip"] == 25
        assert metadata["current_page"] == 2
        assert metadata["per_page"] == 25
        assert metadata["total_items"] == 100

    def test_pagination_metadata_uneven_division(self):
        """Test pagination metadata with uneven division."""
        metadata = calculate_pagination_metadata(
            total_items=23, current_page=1, per_page=10
        )

        assert metadata["total_pages"] == 3  # ceil(23/10)
        assert metadata["skip"] == 0

    def test_pagination_metadata_zero_items(self):
        """Test pagination metadata with zero items."""
        metadata = calculate_pagination_metadata(
            total_items=0, current_page=1, per_page=25
        )

        assert metadata["total_pages"] == 1  # Always at least 1 page
        assert metadata["skip"] == 0

    def test_pagination_metadata_exact_division(self):
        """Test pagination metadata with exact division."""
        metadata = calculate_pagination_metadata(
            total_items=100, current_page=3, per_page=25
        )

        assert metadata["total_pages"] == 4
        assert metadata["skip"] == 50


class TestValidatePaginationParams:
    """Test pagination parameter validation."""

    def test_valid_pagination_params(self):
        """Test valid pagination parameters."""
        # Should not raise any exception
        validate_pagination_params(1, 25)
        validate_pagination_params(10, 100)
        validate_pagination_params(1, 1)

    def test_invalid_page_number(self):
        """Test invalid page numbers."""
        with pytest.raises(ValueError, match="Page number must be greater than 0"):
            validate_pagination_params(0, 25)

        with pytest.raises(ValueError, match="Page number must be greater than 0"):
            validate_pagination_params(-1, 25)

    def test_invalid_per_page_too_small(self):
        """Test invalid per_page too small."""
        with pytest.raises(ValueError, match="Items per page must be greater than 0"):
            validate_pagination_params(1, 0)

        with pytest.raises(ValueError, match="Items per page must be greater than 0"):
            validate_pagination_params(1, -1)

    def test_invalid_per_page_too_large(self):
        """Test invalid per_page too large."""
        with pytest.raises(ValueError, match="Items per page cannot exceed 100"):
            validate_pagination_params(1, 101)

        with pytest.raises(ValueError, match="Items per page cannot exceed 100"):
            validate_pagination_params(1, 1000)

    def test_boundary_values(self):
        """Test boundary values."""
        # Should not raise exceptions
        validate_pagination_params(1, 100)  # Max allowed per_page
        validate_pagination_params(1, 1)  # Min allowed per_page


class TestBuildFilterDict:
    """Test filter dictionary building."""

    def test_build_filter_dict_all_none(self):
        """Test building filter dict with all None values."""
        filters = build_filter_dict()
        assert filters == {}

    def test_build_filter_dict_basic_params(self):
        """Test building filter dict with basic parameters."""
        filters = build_filter_dict(
            organization_id="123", status="active", location_type="physical"
        )

        assert filters["organization_id"] == "123"
        assert filters["status"] == "active"
        assert filters["location_type"] == "physical"

    def test_build_filter_dict_mixed_none(self):
        """Test building filter dict with mixed None values."""
        filters = build_filter_dict(
            organization_id="123", status=None, location_type="physical"
        )

        assert filters["organization_id"] == "123"
        assert filters["location_type"] == "physical"
        assert "status" not in filters

    def test_build_filter_dict_with_kwargs(self):
        """Test building filter dict with additional kwargs."""
        filters = build_filter_dict(
            organization_id="123", custom_field="value", another_filter=42
        )

        assert filters["organization_id"] == "123"
        assert filters["custom_field"] == "value"
        assert filters["another_filter"] == 42

    def test_build_filter_dict_kwargs_with_none(self):
        """Test building filter dict with None kwargs."""
        filters = build_filter_dict(
            organization_id="123",
            custom_field="value",
            none_field=None,
            another_field="test",
        )

        assert filters["organization_id"] == "123"
        assert filters["custom_field"] == "value"
        assert filters["another_field"] == "test"
        assert "none_field" not in filters


class TestFormatDistance:
    """Test distance formatting."""

    def test_format_distance_meters(self):
        """Test formatting distance in meters."""
        assert format_distance(500) == "500m"
        assert format_distance(999) == "999m"
        assert format_distance(0) == "0m"
        assert format_distance(1) == "1m"

    def test_format_distance_kilometers(self):
        """Test formatting distance in kilometers."""
        assert format_distance(1000) == "1.0km"
        assert format_distance(1500) == "1.5km"
        assert format_distance(1609) == "1.6km"  # Just under 1 mile

    def test_format_distance_miles(self):
        """Test formatting distance in miles."""
        assert format_distance(1609.34) == "1.0mi"  # Exactly 1 mile
        assert format_distance(3218.68) == "2.0mi"  # 2 miles
        assert format_distance(8046.7) == "5.0mi"  # 5 miles

    def test_format_distance_edge_cases(self):
        """Test edge cases for distance formatting."""
        # Just under 1km
        assert format_distance(999.9) == "1000m"

        # Just over 1 mile
        assert format_distance(1610) == "1.0mi"


class TestCreateErrorResponse:
    """Test error response creation."""

    def test_create_error_response_basic(self):
        """Test basic error response creation."""
        response = create_error_response("Something went wrong")

        assert response["error"] == "Something went wrong"
        assert "error_code" not in response
        assert "details" not in response

    def test_create_error_response_with_code(self):
        """Test error response with error code."""
        response = create_error_response("Resource not found", error_code="NOT_FOUND")

        assert response["error"] == "Resource not found"
        assert response["error_code"] == "NOT_FOUND"
        assert "details" not in response

    def test_create_error_response_with_details(self):
        """Test error response with details."""
        details = {"resource_type": "organization", "resource_id": "123"}
        response = create_error_response("Resource not found", details=details)

        assert response["error"] == "Resource not found"
        assert response["details"] == details
        assert "error_code" not in response

    def test_create_error_response_complete(self):
        """Test error response with all fields."""
        details = {"field": "value", "validation": "failed"}
        response = create_error_response(
            "Validation failed", error_code="VALIDATION_ERROR", details=details
        )

        assert response["error"] == "Validation failed"
        assert response["error_code"] == "VALIDATION_ERROR"
        assert response["details"] == details


class TestExtractCoordinatesFromQuery:
    """Test coordinate extraction from query parameters."""

    def test_extract_coordinates_valid(self):
        """Test extracting valid coordinates."""
        coords = extract_coordinates_from_query(40.7128, -74.0060)
        assert coords == (40.7128, -74.0060)

    def test_extract_coordinates_none_latitude(self):
        """Test extracting coordinates with None latitude."""
        coords = extract_coordinates_from_query(None, -74.0060)
        assert coords is None

    def test_extract_coordinates_none_longitude(self):
        """Test extracting coordinates with None longitude."""
        coords = extract_coordinates_from_query(40.7128, None)
        assert coords is None

    def test_extract_coordinates_both_none(self):
        """Test extracting coordinates with both None."""
        coords = extract_coordinates_from_query(None, None)
        assert coords is None

    def test_extract_coordinates_invalid_latitude(self):
        """Test invalid latitude values."""
        with pytest.raises(
            ValueError, match="Latitude must be between -90 and 90 degrees"
        ):
            extract_coordinates_from_query(91, -74.0060)

        with pytest.raises(
            ValueError, match="Latitude must be between -90 and 90 degrees"
        ):
            extract_coordinates_from_query(-91, -74.0060)

    def test_extract_coordinates_invalid_longitude(self):
        """Test invalid longitude values."""
        with pytest.raises(
            ValueError, match="Longitude must be between -180 and 180 degrees"
        ):
            extract_coordinates_from_query(40.7128, 181)

        with pytest.raises(
            ValueError, match="Longitude must be between -180 and 180 degrees"
        ):
            extract_coordinates_from_query(40.7128, -181)

    def test_extract_coordinates_boundary_values(self):
        """Test boundary coordinate values."""
        # Valid boundary values
        coords = extract_coordinates_from_query(90, 180)
        assert coords == (90, 180)

        coords = extract_coordinates_from_query(-90, -180)
        assert coords == (-90, -180)

        coords = extract_coordinates_from_query(0, 0)
        assert coords == (0, 0)


class TestCreateMetadataResponse:
    """Test metadata response creation."""

    def test_create_metadata_response_defaults(self):
        """Test metadata response with default values."""
        response = create_metadata_response()

        assert response["data_source"] == "Pantry Pirate Radio"
        assert response["coverage_area"] == "Continental United States"
        assert response["license"] == "CC BY-SA 4.0"
        assert "last_updated" in response
        assert response["last_updated"].endswith("Z")

    def test_create_metadata_response_custom(self):
        """Test metadata response with custom values."""
        response = create_metadata_response(
            data_source="Custom Source", coverage_area="Custom Area", license="MIT"
        )

        assert response["data_source"] == "Custom Source"
        assert response["coverage_area"] == "Custom Area"
        assert response["license"] == "MIT"
        assert "last_updated" in response

    def test_create_metadata_response_timestamp_format(self):
        """Test metadata response timestamp format."""
        response = create_metadata_response()

        # Verify ISO format with Z suffix
        timestamp = response["last_updated"]
        assert timestamp.endswith("Z")

        # Verify it's a valid ISO timestamp
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail("Invalid ISO timestamp format")
