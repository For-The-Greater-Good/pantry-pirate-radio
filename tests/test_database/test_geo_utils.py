"""Test geographic utility functions."""

import pytest
import math

# Import only the safe parts that don't require geoalchemy2
from app.models.hsds.query import GeoBoundingBox, GeoPoint

# Import the class directly to avoid module-level import issues
try:
    from app.database.geo_utils import GeoQueryBuilder
except ImportError:
    pytest.skip("GeoAlchemy2 not available", allow_module_level=True)


class TestGeoQueryBuilder:
    """Test GeoQueryBuilder utility functions."""

    def test_miles_to_meters(self):
        """Test miles to meters conversion."""
        assert GeoQueryBuilder.miles_to_meters(1.0) == pytest.approx(1609.34, rel=1e-3)
        assert GeoQueryBuilder.miles_to_meters(5.0) == pytest.approx(8046.7, rel=1e-3)
        assert GeoQueryBuilder.miles_to_meters(0.0) == 0.0

    def test_meters_to_miles(self):
        """Test meters to miles conversion."""
        assert GeoQueryBuilder.meters_to_miles(1609.34) == pytest.approx(1.0, rel=1e-3)
        assert GeoQueryBuilder.meters_to_miles(8046.7) == pytest.approx(5.0, rel=1e-3)
        assert GeoQueryBuilder.meters_to_miles(0.0) == 0.0

    def test_validate_coordinates(self):
        """Test coordinate validation."""
        # Valid coordinates
        is_valid, message = GeoQueryBuilder.validate_coordinates(40.7128, -74.0060)
        assert is_valid is True
        assert message == ""

        # Invalid latitude
        is_valid, message = GeoQueryBuilder.validate_coordinates(91.0, -74.0060)
        assert is_valid is False
        assert "Latitude must be between" in message

        is_valid, message = GeoQueryBuilder.validate_coordinates(-91.0, -74.0060)
        assert is_valid is False
        assert "Latitude must be between" in message

        # Invalid longitude
        is_valid, message = GeoQueryBuilder.validate_coordinates(40.7128, 181.0)
        assert is_valid is False
        assert "Longitude must be between" in message

        is_valid, message = GeoQueryBuilder.validate_coordinates(40.7128, -181.0)
        assert is_valid is False
        assert "Longitude must be between" in message

    def test_validate_us_bounds(self):
        """Test US bounds validation."""
        # Valid US coordinates
        is_valid, message = GeoQueryBuilder.validate_us_bounds(40.7128, -74.0060)
        assert is_valid is True
        assert message == ""

        # Outside US bounds - too far north
        is_valid, message = GeoQueryBuilder.validate_us_bounds(50.0, -74.0060)
        assert is_valid is False
        assert "Latitude must be between" in message

        # Outside US bounds - too far south
        is_valid, message = GeoQueryBuilder.validate_us_bounds(24.0, -74.0060)
        assert is_valid is False
        assert "Latitude must be between" in message

        # Outside US bounds - too far east
        is_valid, message = GeoQueryBuilder.validate_us_bounds(40.7128, -60.0)
        assert is_valid is False
        assert "Longitude must be between" in message

        # Outside US bounds - too far west
        is_valid, message = GeoQueryBuilder.validate_us_bounds(40.7128, -130.0)
        assert is_valid is False
        assert "Longitude must be between" in message

    def test_clamp_to_us_bounds(self):
        """Test clamping coordinates to US bounds."""
        # Coordinates already within bounds
        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(40.7128, -74.0060)
        assert lat == 40.7128
        assert lon == -74.0060

        # Latitude too high
        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(50.0, -74.0060)
        assert lat == 49.0  # Max US latitude
        assert lon == -74.0060

        # Latitude too low
        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(20.0, -74.0060)
        assert lat == 25.0  # Min US latitude
        assert lon == -74.0060

        # Longitude too high (too far east)
        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(40.7128, -60.0)
        assert lat == 40.7128
        assert lon == -67.0  # Max US longitude

        # Longitude too low (too far west)
        lat, lon = GeoQueryBuilder.clamp_to_us_bounds(40.7128, -130.0)
        assert lat == 40.7128
        assert lon == -125.0  # Min US longitude

    def test_calculate_bounding_box_from_point(self):
        """Test bounding box calculation from center point and radius."""
        center = GeoPoint(latitude=40.7128, longitude=-74.0060)
        radius_miles = 10.0

        bbox = GeoQueryBuilder.calculate_bounding_box_from_point(center, radius_miles)

        assert isinstance(bbox, GeoBoundingBox)
        assert bbox.min_latitude < center.latitude
        assert bbox.max_latitude > center.latitude
        assert bbox.min_longitude < center.longitude
        assert bbox.max_longitude > center.longitude

        # Check that the radius approximation is reasonable
        lat_delta = (bbox.max_latitude - bbox.min_latitude) / 2
        expected_lat_delta = radius_miles / 69.0
        assert lat_delta == pytest.approx(expected_lat_delta, rel=1e-3)

    def test_is_point_in_bbox(self):
        """Test point-in-bounding-box check."""
        bbox = GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=41.0,
            min_longitude=-75.0,
            max_longitude=-73.0,
        )

        # Point inside
        point_inside = GeoPoint(latitude=40.5, longitude=-74.0)
        assert GeoQueryBuilder.is_point_in_bbox(point_inside, bbox) is True

        # Point outside - latitude too low
        point_outside = GeoPoint(latitude=39.5, longitude=-74.0)
        assert GeoQueryBuilder.is_point_in_bbox(point_outside, bbox) is False

        # Point outside - latitude too high
        point_outside = GeoPoint(latitude=41.5, longitude=-74.0)
        assert GeoQueryBuilder.is_point_in_bbox(point_outside, bbox) is False

        # Point outside - longitude too low
        point_outside = GeoPoint(latitude=40.5, longitude=-76.0)
        assert GeoQueryBuilder.is_point_in_bbox(point_outside, bbox) is False

        # Point outside - longitude too high
        point_outside = GeoPoint(latitude=40.5, longitude=-72.0)
        assert GeoQueryBuilder.is_point_in_bbox(point_outside, bbox) is False

        # Point on boundary
        point_boundary = GeoPoint(latitude=40.0, longitude=-74.0)
        assert GeoQueryBuilder.is_point_in_bbox(point_boundary, bbox) is True

    def test_expand_bbox_by_percentage(self):
        """Test bounding box expansion."""
        original_bbox = GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=41.0,
            min_longitude=-75.0,
            max_longitude=-73.0,
        )

        expanded_bbox = GeoQueryBuilder.expand_bbox_by_percentage(original_bbox, 10.0)

        # Original range: 1.0 degrees latitude, 2.0 degrees longitude
        # 10% expansion should add 0.1 degrees to each side of latitude
        # and 0.2 degrees to each side of longitude
        assert expanded_bbox.min_latitude == pytest.approx(39.9, rel=1e-3)
        assert expanded_bbox.max_latitude == pytest.approx(41.1, rel=1e-3)
        assert expanded_bbox.min_longitude == pytest.approx(-75.2, rel=1e-3)
        assert expanded_bbox.max_longitude == pytest.approx(-72.8, rel=1e-3)

    def test_calculate_bbox_center(self):
        """Test bounding box center calculation."""
        bbox = GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=42.0,
            min_longitude=-76.0,
            max_longitude=-72.0,
        )

        center = GeoQueryBuilder.calculate_bbox_center(bbox)

        assert center.latitude == 41.0  # (40 + 42) / 2
        assert center.longitude == -74.0  # (-76 + -72) / 2

    def test_get_state_bounding_box(self):
        """Test state bounding box lookup."""
        # Test known states
        nj_bbox = GeoQueryBuilder.get_state_bounding_box("NJ")
        assert nj_bbox is not None
        assert isinstance(nj_bbox, GeoBoundingBox)
        assert nj_bbox.min_latitude > 0
        assert nj_bbox.max_latitude > nj_bbox.min_latitude

        # Test case insensitive
        ny_bbox = GeoQueryBuilder.get_state_bounding_box("ny")
        assert ny_bbox is not None
        assert isinstance(ny_bbox, GeoBoundingBox)

        # Test unknown state
        unknown_bbox = GeoQueryBuilder.get_state_bounding_box("ZZ")
        assert unknown_bbox is None

    def test_create_point_from_coordinates(self):
        """Test PostGIS point creation (mocked)."""
        # This tests the interface, but PostGIS functions won't work without a real DB
        point = GeoQueryBuilder.create_point_from_coordinates(-74.0060, 40.7128)
        # Just verify it returns something (the actual SQL function)
        assert point is not None

    def test_create_bounding_box(self):
        """Test PostGIS bounding box creation (mocked)."""
        bbox = GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=41.0,
            min_longitude=-75.0,
            max_longitude=-73.0,
        )
        bbox_geom = GeoQueryBuilder.create_bounding_box(bbox)
        # Just verify it returns something (the actual SQL function)
        assert bbox_geom is not None
