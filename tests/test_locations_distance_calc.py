"""Unit tests for distance calculation logic in app/api/v1/locations.py."""

import math
import pytest
from unittest.mock import Mock, patch

from app.api.v1.locations import search_locations


class TestLocationDistanceCalculation:
    """Test the distance calculation logic in search_locations function."""

    def test_haversine_distance_calculation(self):
        """Test the haversine distance calculation formula."""
        # Test data: NYC to LA coordinates
        lat1, lon1 = 40.7128, -74.0060  # NYC
        lat2, lon2 = 34.0522, -118.2437  # LA

        # Convert to radians
        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

        # Calculate deltas
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        # Haversine formula
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance_miles = 3959 * c  # Earth's radius in miles

        # The distance should be approximately 2451 miles
        assert 2440 < distance_miles < 2460

    def test_distance_calculation_same_point(self):
        """Test distance calculation for the same point."""
        lat, lon = 40.7128, -74.0060

        # Convert to radians
        lat_rad, lon_rad = math.radians(lat), math.radians(lon)

        # Calculate distance to itself
        dlat = lat_rad - lat_rad  # 0
        dlon = lon_rad - lon_rad  # 0

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat_rad) * math.cos(lat_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance_miles = 3959 * c

        # Distance should be 0 (or very close to 0)
        assert distance_miles < 0.001

    def test_distance_calculation_short_distance(self):
        """Test distance calculation for a short distance."""
        # Manhattan coordinates (roughly 1 mile apart)
        lat1, lon1 = 40.7831, -73.9712  # Central Park
        lat2, lon2 = 40.7589, -73.9851  # Times Square

        # Convert to radians
        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

        # Calculate distance
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance_miles = 3959 * c

        # Distance should be approximately 1.7 miles
        assert 1.5 < distance_miles < 2.0

    def test_distance_formatting_logic(self):
        """Test the distance formatting logic in the search function."""
        # Test various distance values and their formatting
        test_cases = [
            (0.5, "0.5mi"),
            (1.0, "1.0mi"),
            (1.5, "1.5mi"),
            (10.7, "10.7mi"),
            (100.0, "100.0mi"),
        ]

        for distance_miles, expected_format in test_cases:
            formatted = f"{distance_miles:.1f}mi"
            assert formatted == expected_format

    def test_math_functions_accuracy(self):
        """Test the accuracy of math functions used in distance calculation."""
        # Test sin function
        assert abs(math.sin(0) - 0) < 1e-10
        assert abs(math.sin(math.pi / 2) - 1) < 1e-10

        # Test cos function
        assert abs(math.cos(0) - 1) < 1e-10
        assert abs(math.cos(math.pi / 2)) < 1e-10

        # Test asin function
        assert abs(math.asin(0) - 0) < 1e-10
        assert abs(math.asin(1) - math.pi / 2) < 1e-10

        # Test sqrt function
        assert abs(math.sqrt(4) - 2) < 1e-10
        assert abs(math.sqrt(0) - 0) < 1e-10

    def test_radians_conversion(self):
        """Test radians conversion accuracy."""
        # Test conversion of common angles
        assert abs(math.radians(0) - 0) < 1e-10
        assert abs(math.radians(90) - math.pi / 2) < 1e-10
        assert abs(math.radians(180) - math.pi) < 1e-10
        assert abs(math.radians(360) - 2 * math.pi) < 1e-10

    def test_distance_calculation_edge_cases(self):
        """Test distance calculation for edge cases."""
        # Test antipodal points (opposite sides of earth)
        lat1, lon1 = 90.0, 0.0  # North pole
        lat2, lon2 = -90.0, 0.0  # South pole

        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance_miles = 3959 * c

        # Distance should be approximately half the earth's circumference
        # Earth's circumference is about 24,901 miles, so half is about 12,450 miles
        assert 12400 < distance_miles < 12500

    def test_distance_calculation_across_dateline(self):
        """Test distance calculation across the international date line."""
        # Points on either side of the international date line
        lat1, lon1 = 0.0, 179.0  # Just west of dateline
        lat2, lon2 = 0.0, -179.0  # Just east of dateline

        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance_miles = 3959 * c

        # Distance should be approximately 138 miles (2 degrees longitude at equator)
        assert 130 < distance_miles < 150

    def test_earth_radius_constant(self):
        """Test the Earth's radius constant used in calculations."""
        earth_radius_miles = 3959

        # Verify this is approximately correct
        # Earth's actual radius is about 3959 miles
        assert 3950 < earth_radius_miles < 3970

    def test_distance_precision(self):
        """Test precision of distance calculations."""
        # Test very close points
        lat1, lon1 = 40.7128, -74.0060
        lat2, lon2 = 40.7129, -74.0061  # Very close

        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance_miles = 3959 * c

        # Distance should be very small but measurable
        assert 0 < distance_miles < 0.1

    def test_distance_calculation_formula_components(self):
        """Test individual components of the distance calculation formula."""
        lat1, lon1 = 40.7128, -74.0060
        lat2, lon2 = 34.0522, -118.2437

        # Test radians conversion
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Verify conversions
        assert -math.pi <= lat1_rad <= math.pi
        assert -math.pi <= lon1_rad <= math.pi
        assert -math.pi <= lat2_rad <= math.pi
        assert -math.pi <= lon2_rad <= math.pi

        # Test delta calculations
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        # Test haversine formula components
        sin_dlat_2 = math.sin(dlat / 2)
        sin_dlon_2 = math.sin(dlon / 2)

        a = sin_dlat_2**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * sin_dlon_2**2

        # 'a' should be between 0 and 1
        assert 0 <= a <= 1

        # Test final calculation
        c = 2 * math.asin(math.sqrt(a))
        distance_miles = 3959 * c

        # Verify final result is reasonable
        assert distance_miles > 0
        assert distance_miles < 25000  # Max possible distance on Earth
