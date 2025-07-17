"""Unit tests for app/api/v1/utils.py functions."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from urllib.parse import urlencode

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
    """Test create_pagination_links function."""

    def test_create_pagination_links_basic(self):
        """Test basic pagination link creation."""
        request = Mock()
        request.url = "http://example.com/api/locations"

        links = create_pagination_links(
            request=request, current_page=2, total_pages=5, per_page=25
        )

        assert "first" in links
        assert "last" in links
        assert "next" in links
        assert "prev" in links
        assert "page=1" in links["first"]
        assert "page=5" in links["last"]
        assert "page=3" in links["next"]
        assert "page=1" in links["prev"]
        assert "per_page=25" in links["first"]

    def test_create_pagination_links_with_extra_params(self):
        """Test pagination links with extra parameters."""
        request = Mock()
        request.url = "http://example.com/api/locations"

        extra_params = {"organization_id": "123", "status": "active"}
        links = create_pagination_links(
            request=request,
            current_page=1,
            total_pages=3,
            per_page=10,
            extra_params=extra_params,
        )

        assert "organization_id=123" in links["first"]
        assert "status=active" in links["first"]

    def test_create_pagination_links_filters_none_values(self):
        """Test that None values are filtered from extra_params."""
        request = Mock()
        request.url = "http://example.com/api/locations"

        extra_params = {"organization_id": "123", "status": None, "type": "food"}
        links = create_pagination_links(
            request=request,
            current_page=1,
            total_pages=2,
            per_page=10,
            extra_params=extra_params,
        )

        assert "organization_id=123" in links["first"]
        assert "type=food" in links["first"]
        assert "status=" not in links["first"]

    def test_create_pagination_links_first_page(self):
        """Test pagination links on first page."""
        request = Mock()
        request.url = "http://example.com/api/locations"

        links = create_pagination_links(
            request=request, current_page=1, total_pages=5, per_page=25
        )

        assert links["prev"] is None
        assert links["next"] is not None
        assert "page=2" in links["next"]

    def test_create_pagination_links_last_page(self):
        """Test pagination links on last page."""
        request = Mock()
        request.url = "http://example.com/api/locations"

        links = create_pagination_links(
            request=request, current_page=5, total_pages=5, per_page=25
        )

        assert links["next"] is None
        assert links["prev"] is not None
        assert "page=4" in links["prev"]

    def test_create_pagination_links_single_page(self):
        """Test pagination links with single page."""
        request = Mock()
        request.url = "http://example.com/api/locations"

        links = create_pagination_links(
            request=request, current_page=1, total_pages=1, per_page=25
        )

        assert links["next"] is None
        assert links["prev"] is None
        assert "page=1" in links["first"]
        assert "page=1" in links["last"]

    def test_create_pagination_links_with_query_params(self):
        """Test pagination links with existing query parameters."""
        request = Mock()
        request.url = "http://example.com/api/locations?existing=param"

        links = create_pagination_links(
            request=request, current_page=1, total_pages=2, per_page=10
        )

        # Should remove existing query params and add new ones
        assert "existing=param" not in links["first"]
        assert "page=1" in links["first"]
        assert "per_page=10" in links["first"]


class TestCalculatePaginationMetadata:
    """Test calculate_pagination_metadata function."""

    def test_calculate_pagination_metadata_basic(self):
        """Test basic pagination metadata calculation."""
        metadata = calculate_pagination_metadata(
            total_items=100, current_page=2, per_page=25
        )

        assert metadata["total_pages"] == 4
        assert metadata["skip"] == 25
        assert metadata["current_page"] == 2
        assert metadata["per_page"] == 25
        assert metadata["total_items"] == 100

    def test_calculate_pagination_metadata_partial_page(self):
        """Test pagination metadata with partial last page."""
        metadata = calculate_pagination_metadata(
            total_items=23, current_page=1, per_page=10
        )

        assert metadata["total_pages"] == 3
        assert metadata["skip"] == 0

    def test_calculate_pagination_metadata_zero_items(self):
        """Test pagination metadata with zero items."""
        metadata = calculate_pagination_metadata(
            total_items=0, current_page=1, per_page=10
        )

        assert metadata["total_pages"] == 1
        assert metadata["skip"] == 0

    def test_calculate_pagination_metadata_exact_pages(self):
        """Test pagination metadata with exact page divisions."""
        metadata = calculate_pagination_metadata(
            total_items=100, current_page=3, per_page=20
        )

        assert metadata["total_pages"] == 5
        assert metadata["skip"] == 40


class TestValidatePaginationParams:
    """Test validate_pagination_params function."""

    def test_validate_pagination_params_valid(self):
        """Test validation with valid parameters."""
        # Should not raise any exception
        validate_pagination_params(1, 25)
        validate_pagination_params(10, 100)
        validate_pagination_params(5, 50)

    def test_validate_pagination_params_invalid_page(self):
        """Test validation with invalid page number."""
        with pytest.raises(ValueError, match="Page number must be greater than 0"):
            validate_pagination_params(0, 25)

        with pytest.raises(ValueError, match="Page number must be greater than 0"):
            validate_pagination_params(-1, 25)

    def test_validate_pagination_params_invalid_per_page(self):
        """Test validation with invalid per_page."""
        with pytest.raises(ValueError, match="Items per page must be greater than 0"):
            validate_pagination_params(1, 0)

        with pytest.raises(ValueError, match="Items per page must be greater than 0"):
            validate_pagination_params(1, -1)

    def test_validate_pagination_params_per_page_too_large(self):
        """Test validation with per_page exceeding limit."""
        with pytest.raises(ValueError, match="Items per page cannot exceed 100"):
            validate_pagination_params(1, 101)

        with pytest.raises(ValueError, match="Items per page cannot exceed 100"):
            validate_pagination_params(1, 1000)


class TestBuildFilterDict:
    """Test build_filter_dict function."""

    def test_build_filter_dict_basic(self):
        """Test basic filter dictionary building."""
        filters = build_filter_dict(
            organization_id="123", status="active", location_type="food_bank"
        )

        assert filters["organization_id"] == "123"
        assert filters["status"] == "active"
        assert filters["location_type"] == "food_bank"

    def test_build_filter_dict_with_none_values(self):
        """Test filter dictionary with None values."""
        filters = build_filter_dict(
            organization_id="123", status=None, location_type="food_bank"
        )

        assert filters["organization_id"] == "123"
        assert filters["location_type"] == "food_bank"
        assert "status" not in filters

    def test_build_filter_dict_with_kwargs(self):
        """Test filter dictionary with additional kwargs."""
        filters = build_filter_dict(
            organization_id="123", custom_field="value", another_field="another_value"
        )

        assert filters["organization_id"] == "123"
        assert filters["custom_field"] == "value"
        assert filters["another_field"] == "another_value"

    def test_build_filter_dict_kwargs_filter_none(self):
        """Test that kwargs with None values are filtered out."""
        filters = build_filter_dict(
            organization_id="123", custom_field="value", empty_field=None
        )

        assert filters["organization_id"] == "123"
        assert filters["custom_field"] == "value"
        assert "empty_field" not in filters

    def test_build_filter_dict_empty(self):
        """Test filter dictionary with all None values."""
        filters = build_filter_dict(
            organization_id=None, status=None, location_type=None
        )

        assert filters == {}


class TestFormatDistance:
    """Test format_distance function."""

    def test_format_distance_meters(self):
        """Test distance formatting in meters."""
        assert format_distance(500) == "500m"
        assert format_distance(999) == "999m"
        assert format_distance(1) == "1m"

    def test_format_distance_kilometers(self):
        """Test distance formatting in kilometers."""
        assert format_distance(1000) == "1.0km"
        assert format_distance(1500) == "1.5km"
        assert format_distance(1600) == "1.6km"  # Still less than 1 mile

    def test_format_distance_miles(self):
        """Test distance formatting in miles."""
        assert format_distance(1609.34) == "1.0mi"  # Exactly 1 mile
        assert format_distance(3218.68) == "2.0mi"  # Exactly 2 miles
        assert format_distance(2414.01) == "1.5mi"  # 1.5 miles

    def test_format_distance_edge_cases(self):
        """Test distance formatting edge cases."""
        assert format_distance(0) == "0m"
        assert format_distance(999.9) == "1000m"
        assert format_distance(1609.33) == "1.6km"  # Just under 1 mile
        assert format_distance(1609.35) == "1.0mi"  # Just over 1 mile


class TestCreateErrorResponse:
    """Test create_error_response function."""

    def test_create_error_response_basic(self):
        """Test basic error response creation."""
        response = create_error_response("Something went wrong")

        assert response["error"] == "Something went wrong"
        assert "error_code" not in response
        assert "details" not in response

    def test_create_error_response_with_code(self):
        """Test error response with error code."""
        response = create_error_response("Invalid input", error_code="INVALID_INPUT")

        assert response["error"] == "Invalid input"
        assert response["error_code"] == "INVALID_INPUT"
        assert "details" not in response

    def test_create_error_response_with_details(self):
        """Test error response with details."""
        details = {"field": "email", "value": "invalid@"}
        response = create_error_response("Validation error", details=details)

        assert response["error"] == "Validation error"
        assert response["details"] == details
        assert "error_code" not in response

    def test_create_error_response_complete(self):
        """Test error response with all parameters."""
        details = {"field": "email", "value": "invalid@"}
        response = create_error_response(
            "Validation error", error_code="VALIDATION_ERROR", details=details
        )

        assert response["error"] == "Validation error"
        assert response["error_code"] == "VALIDATION_ERROR"
        assert response["details"] == details


class TestExtractCoordinatesFromQuery:
    """Test extract_coordinates_from_query function."""

    def test_extract_coordinates_valid(self):
        """Test extracting valid coordinates."""
        coords = extract_coordinates_from_query(40.7128, -74.0060)
        assert coords == (40.7128, -74.0060)

    def test_extract_coordinates_none_values(self):
        """Test extracting coordinates with None values."""
        assert extract_coordinates_from_query(None, -74.0060) is None
        assert extract_coordinates_from_query(40.7128, None) is None
        assert extract_coordinates_from_query(None, None) is None

    def test_extract_coordinates_edge_cases(self):
        """Test extracting coordinates at valid edges."""
        assert extract_coordinates_from_query(90.0, 180.0) == (90.0, 180.0)
        assert extract_coordinates_from_query(-90.0, -180.0) == (-90.0, -180.0)
        assert extract_coordinates_from_query(0.0, 0.0) == (0.0, 0.0)

    def test_extract_coordinates_invalid_latitude(self):
        """Test extracting coordinates with invalid latitude."""
        with pytest.raises(
            ValueError, match="Latitude must be between -90 and 90 degrees"
        ):
            extract_coordinates_from_query(91.0, 0.0)

        with pytest.raises(
            ValueError, match="Latitude must be between -90 and 90 degrees"
        ):
            extract_coordinates_from_query(-91.0, 0.0)

    def test_extract_coordinates_invalid_longitude(self):
        """Test extracting coordinates with invalid longitude."""
        with pytest.raises(
            ValueError, match="Longitude must be between -180 and 180 degrees"
        ):
            extract_coordinates_from_query(0.0, 181.0)

        with pytest.raises(
            ValueError, match="Longitude must be between -180 and 180 degrees"
        ):
            extract_coordinates_from_query(0.0, -181.0)


class TestCreateMetadataResponse:
    """Test create_metadata_response function."""

    def test_create_metadata_response_defaults(self):
        """Test metadata response with default values."""
        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2023, 1, 1, 12, 0, 0)

            metadata = create_metadata_response()

            assert metadata["data_source"] == "Pantry Pirate Radio"
            assert metadata["coverage_area"] == "Continental United States"
            assert metadata["license"] == "CC BY-SA 4.0"
            assert metadata["last_updated"] == "2023-01-01T12:00:00Z"

    def test_create_metadata_response_custom_values(self):
        """Test metadata response with custom values."""
        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2023, 6, 15, 8, 30, 0)

            metadata = create_metadata_response(
                data_source="Custom Source", coverage_area="Test Area", license="MIT"
            )

            assert metadata["data_source"] == "Custom Source"
            assert metadata["coverage_area"] == "Test Area"
            assert metadata["license"] == "MIT"
            assert metadata["last_updated"] == "2023-06-15T08:30:00Z"

    def test_create_metadata_response_timestamp_format(self):
        """Test that timestamp is properly formatted."""
        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2023, 12, 25, 23, 59, 59)

            metadata = create_metadata_response()

            assert metadata["last_updated"] == "2023-12-25T23:59:59Z"
            assert metadata["last_updated"].endswith("Z")
            assert "T" in metadata["last_updated"]
