"""Tests for geographic utility functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.sql import Select

from app.database.geo_utils import GeoQueryBuilder, HAS_GEOALCHEMY2
from app.models.hsds.query import GeoPoint, GeoBoundingBox


class TestGeoQueryBuilder:
    """Test GeoQueryBuilder methods."""

    def test_miles_to_meters(self):
        """Test miles to meters conversion."""
        result = GeoQueryBuilder.miles_to_meters(1.0)
        assert abs(result - 1609.34) < 0.01

    def test_meters_to_miles(self):
        """Test meters to miles conversion."""
        result = GeoQueryBuilder.meters_to_miles(1609.34)
        assert abs(result - 1.0) < 0.01

    def test_create_point_from_coordinates(self):
        """Test point creation from coordinates."""
        # This should work even without GeoAlchemy2 (uses SQLAlchemy func)
        point = GeoQueryBuilder.create_point_from_coordinates(-74.0060, 40.7128)
        assert point is not None

    def test_create_bounding_box(self):
        """Test bounding box creation."""
        bbox = GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=41.0,
            min_longitude=-75.0,
            max_longitude=-74.0,
        )
        # This should work even without GeoAlchemy2 (uses SQLAlchemy func)
        bbox_geom = GeoQueryBuilder.create_bounding_box(bbox)
        assert bbox_geom is not None

    def test_add_radius_filter_without_geoalchemy(self):
        """Test radius filter when GeoAlchemy2 not available."""
        mock_query = MagicMock(spec=Select)
        center = GeoPoint(latitude=40.7128, longitude=-74.0060)

        # When GeoAlchemy2 is not available, should return original query
        if not HAS_GEOALCHEMY2:
            result = GeoQueryBuilder.add_radius_filter(mock_query, None, center, 10.0)
            assert result == mock_query

    def test_add_bbox_filter_without_geoalchemy(self):
        """Test bbox filter when GeoAlchemy2 not available."""
        mock_query = MagicMock(spec=Select)
        bbox = GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=41.0,
            min_longitude=-75.0,
            max_longitude=-74.0,
        )

        # When GeoAlchemy2 is not available, should return original query
        if not HAS_GEOALCHEMY2:
            result = GeoQueryBuilder.add_bbox_filter(mock_query, None, bbox)
            assert result == mock_query

    def test_add_distance_order_without_geoalchemy(self):
        """Test distance ordering when GeoAlchemy2 not available."""
        mock_query = MagicMock(spec=Select)
        reference_point = GeoPoint(latitude=40.7128, longitude=-74.0060)

        # When GeoAlchemy2 is not available, should return original query
        if not HAS_GEOALCHEMY2:
            result = GeoQueryBuilder.add_distance_order(
                mock_query, None, reference_point
            )
            assert result == mock_query

    def test_calculate_distance_miles_without_geoalchemy(self):
        """Test distance calculation when GeoAlchemy2 not available."""
        reference_point = GeoPoint(latitude=40.7128, longitude=-74.0060)

        # When GeoAlchemy2 is not available, should return 0.0
        if not HAS_GEOALCHEMY2:
            result = GeoQueryBuilder.calculate_distance_miles(None, reference_point)
            assert result == 0.0

    def test_validate_coordinates_valid(self):
        """Test coordinate validation for valid coordinates."""
        valid, message = GeoQueryBuilder.validate_coordinates(40.7128, -74.0060)
        assert valid is True
        assert message == ""

        valid, message = GeoQueryBuilder.validate_coordinates(0.0, 0.0)
        assert valid is True
        assert message == ""

    def test_validate_coordinates_invalid_latitude(self):
        """Test coordinate validation for invalid latitude."""
        valid, message = GeoQueryBuilder.validate_coordinates(91.0, 0.0)
        assert valid is False
        assert "Latitude" in message

        valid, message = GeoQueryBuilder.validate_coordinates(-91.0, 0.0)
        assert valid is False
        assert "Latitude" in message

    def test_validate_coordinates_invalid_longitude(self):
        """Test coordinate validation for invalid longitude."""
        valid, message = GeoQueryBuilder.validate_coordinates(0.0, 181.0)
        assert valid is False
        assert "Longitude" in message

        valid, message = GeoQueryBuilder.validate_coordinates(0.0, -181.0)
        assert valid is False
        assert "Longitude" in message

    def test_validate_us_bounds_valid(self):
        """Test US bounds validation for valid coordinates."""
        # NYC should be valid
        valid, message = GeoQueryBuilder.validate_us_bounds(40.7128, -74.0060)
        assert valid is True
        assert message == ""

        # Los Angeles should be valid
        valid, message = GeoQueryBuilder.validate_us_bounds(34.0522, -118.2437)
        assert valid is True
        assert message == ""

    def test_validate_us_bounds_invalid(self):
        """Test US bounds validation for invalid coordinates."""
        # London should be invalid
        valid, message = GeoQueryBuilder.validate_us_bounds(51.5074, -0.1278)
        assert valid is False
        assert "continental US" in message

        # Tokyo should be invalid
        valid, message = GeoQueryBuilder.validate_us_bounds(35.6762, 139.6503)
        assert valid is False
        assert "continental US" in message

    def test_clamp_to_us_bounds(self):
        """Test clamping coordinates to US bounds."""
        # Test coordinates that need clamping
        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(60.0, -80.0)  # Too far north
        assert lat <= 49.0  # Should be clamped to max US latitude

        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(20.0, -80.0)  # Too far south
        assert lat >= 25.0  # Should be clamped to min US latitude

        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(40.0, -60.0)  # Too far east
        assert lon <= -67.0  # Should be clamped to max US longitude

        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(40.0, -130.0)  # Too far west
        assert lon >= -125.0  # Should be clamped to min US longitude

    def test_clamp_to_us_bounds_no_change(self):
        """Test clamping coordinates that don't need clamping."""
        # NYC coordinates should not change
        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(40.7128, -74.0060)
        assert abs(lat - 40.7128) < 0.0001
        assert abs(lon - (-74.0060)) < 0.0001


class TestGeoUtilsIntegration:
    """Test integration scenarios for geo utilities."""

    def test_conversion_round_trip(self):
        """Test round-trip conversion between miles and meters."""
        original_miles = 10.5
        meters = GeoQueryBuilder.miles_to_meters(original_miles)
        converted_miles = GeoQueryBuilder.meters_to_miles(meters)

        assert abs(original_miles - converted_miles) < 0.0001

    def test_coordinate_validation_edge_cases(self):
        """Test coordinate validation edge cases."""
        # Test exact boundaries
        valid, _ = GeoQueryBuilder.validate_coordinates(90.0, 180.0)
        assert valid is True

        valid, _ = GeoQueryBuilder.validate_coordinates(-90.0, -180.0)
        assert valid is True

        # Test just over boundaries
        valid, _ = GeoQueryBuilder.validate_coordinates(90.1, 0.0)
        assert valid is False

        valid, _ = GeoQueryBuilder.validate_coordinates(0.0, 180.1)
        assert valid is False

    def test_us_bounds_edge_cases(self):
        """Test US bounds validation edge cases."""
        # Test exact US boundaries
        valid, _ = GeoQueryBuilder.validate_us_bounds(25.0, -125.0)  # Southwest corner
        assert valid is True

        valid, _ = GeoQueryBuilder.validate_us_bounds(49.0, -67.0)  # Northeast corner
        assert valid is True

        # Test just outside US boundaries
        valid, _ = GeoQueryBuilder.validate_us_bounds(24.9, -125.0)
        assert valid is False

        valid, _ = GeoQueryBuilder.validate_us_bounds(49.1, -67.0)
        assert valid is False
