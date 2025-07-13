"""Tests for grid generation functionality."""

import math
from pathlib import Path
from typing import Any, Dict, List

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.grid import GridGenerator
from app.models.geographic import BoundingBox, GridPoint, USBounds
from app.scraper.utils import ScraperUtils

# Set up fixtures directory path
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestBoundingBox:
    """Test suite for BoundingBox model."""

    def test_bounding_box_name(self) -> None:
        """Test bounding box name generation."""
        box = BoundingBox(north=42.0, south=41.0, east=-71.0, west=-72.0)
        assert "Area (41.00, -72.00) to (42.00, -71.00)" in box.name

    def test_from_geojson(self) -> None:
        """Test creating bounding box from GeoJSON."""
        geojson_path = FIXTURES_DIR / "test_area.geojson"
        bounds = BoundingBox.from_geojson(geojson_path)

        # Check bounds match our test area
        assert bounds.north == 42.0
        assert bounds.south == 41.0
        assert bounds.east == -71.0
        assert bounds.west == -72.0

        # Check name includes coordinates
        assert "(41.00, -72.00) to (42.00, -71.00)" in bounds.name

    def test_from_geojson_invalid_file(self) -> None:
        """Test error handling for invalid GeoJSON."""
        with pytest.raises(ValueError, match="Failed to extract bounds"):
            BoundingBox.from_geojson(FIXTURES_DIR / "nonexistent.geojson")

    def test_us_bounds_name(self) -> None:
        """Test US bounds name override."""
        bounds = USBounds(north=49.0, south=25.0, east=-67.0, west=-125.0)
        assert bounds.name == "Continental United States"


class TestGridGenerator:
    """Test suite for GridGenerator."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.us_bounds = USBounds(north=49.0, south=25.0, east=-67.0, west=-125.0)
        self.generator = GridGenerator()
        self.custom_bounds = BoundingBox(
            north=42.0, south=41.0, east=-71.0, west=-72.0
        )  # Roughly covers part of Massachusetts
        self.custom_generator = GridGenerator(self.custom_bounds)

    def test_us_coverage(self) -> None:
        """Test that grid covers entire continental US."""
        grid = self.generator.generate_grid()

        # Should have reasonable number of points for coverage
        assert len(grid) > 100

        # Check bounds coverage
        assert any(p.latitude >= self.us_bounds.south for p in grid)
        assert any(p.latitude <= self.us_bounds.north for p in grid)
        assert any(p.longitude >= self.us_bounds.west for p in grid)
        assert any(p.longitude <= self.us_bounds.east for p in grid)

    def test_custom_area_coverage(self) -> None:
        """Test that grid covers custom bounding box."""
        grid = self.custom_generator.generate_grid()

        # Should have reasonable number of points for small area
        assert len(grid) >= 4

        # Check bounds coverage
        assert any(p.latitude >= self.custom_bounds.south for p in grid)
        assert any(p.latitude <= self.custom_bounds.north for p in grid)
        assert any(p.longitude >= self.custom_bounds.west for p in grid)
        assert any(p.longitude <= self.custom_bounds.east for p in grid)

        # Check point naming
        assert all(self.custom_bounds.name in p.name for p in grid)

    def test_proper_overlap(self) -> None:
        """Test that grid points have proper spacing and overlap."""
        grid = self.generator.generate_grid()

        # Get two adjacent points
        p1 = grid[0]
        p2 = grid[1]

        # Calculate distance between points
        lat_diff = abs(p1.latitude - p2.latitude)
        lon_diff = abs(p1.longitude - p2.longitude)

        # Spacing should be less than search radius (due to overlap)
        miles_between = math.sqrt(
            (lat_diff * 69.0) ** 2
            + (lon_diff * math.cos(math.radians(p1.latitude)) * 69.0) ** 2
        )
        assert miles_between <= self.generator.SEARCH_RADIUS_MILES

    def test_coordinate_rounding(self) -> None:
        """Test coordinate rounding functionality."""
        coord = 123.4567891234
        rounded = self.generator.round_coordinate(coord)  # Uses default precision=4
        assert len(str(rounded).split(".")[-1]) <= 4
        assert rounded == 123.4568  # Verifies rounding behavior

    def test_export_json(self, tmp_path: Path) -> None:
        """Test JSON export functionality."""
        import json
        import os

        # Change to temp directory for test
        os.chdir(tmp_path)

        # Test both US and custom area exports
        self.generator.export_grid("json")
        assert os.path.exists("coordinates.json")

        # Verify JSON structure
        with open("coordinates.json") as f:
            data = json.load(f)
            points: List[Dict[str, Any]] = data

        assert isinstance(points, list)
        for point in points:
            assert isinstance(point["latitude"], float)
            assert isinstance(point["longitude"], float)
            assert isinstance(point["name"], str)
            # Verify 4 decimal precision
            assert len(str(point["latitude"]).split(".")[-1]) <= 4
            assert len(str(point["longitude"]).split(".")[-1]) <= 4

    def test_export_csv(self, tmp_path: Path) -> None:
        """Test CSV export functionality."""
        import os

        # Change to temp directory for test
        os.chdir(tmp_path)

        # Test both US and custom area exports
        self.generator.export_grid("csv")
        assert os.path.exists("coordinates.csv")

        # Verify CSV structure
        with open("coordinates.csv") as f:
            lines = f.readlines()
        assert lines[0].strip() == "latitude,longitude,name"
        assert len(lines) > 1

        # Check data row format
        for line in lines[1:]:
            parts = line.strip().split(",")
            assert len(parts) == 3
            assert all(p.replace(".", "").replace("-", "").isdigit() for p in parts[:2])

    @given(
        st.floats(min_value=-85.0, max_value=85.0),  # Avoid polar regions
        st.floats(min_value=-180.0, max_value=180.0),
    )
    def test_coordinate_conversion_properties(self, lat: float, lon: float) -> None:
        """Property-based tests for coordinate conversions."""
        # Test latitude conversion (constant regardless of location)
        miles = 50.0
        lat_degrees = self.generator.miles_to_lat_degrees(miles)
        assert 0 < lat_degrees < 1  # Should be fraction of degree

        # Test longitude conversion (varies with latitude)
        lon_degrees = self.generator.miles_to_lon_degrees(miles, lat)
        # At equator: ~0.7 degrees per 50 miles
        # At 85 degrees: ~8 degrees per 50 miles
        assert 0 < lon_degrees < 10  # Allow for high latitudes

        # Verify longitude degrees increase with latitude
        lat1, lat2 = 25.0, 49.0  # Test with US bounds
        degrees1 = self.generator.miles_to_lon_degrees(miles, lat1)
        degrees2 = self.generator.miles_to_lon_degrees(miles, lat2)
        assert degrees2 > degrees1  # More degrees needed at higher latitudes


class TestScraperUtils:
    """Test suite for ScraperUtils grid functionality."""

    def test_get_us_grid_points(self) -> None:
        """Test getting US grid points."""
        points = ScraperUtils.get_us_grid_points()
        assert isinstance(points, list)
        assert all(isinstance(p, GridPoint) for p in points)
        assert len(points) > 100
        assert "Continental United States" in points[0].name

    def test_get_custom_grid_points(self) -> None:
        """Test getting grid points for custom area."""
        bounds = BoundingBox(north=42.0, south=41.0, east=-71.0, west=-72.0)
        points = ScraperUtils.get_grid_points(bounds)
        assert isinstance(points, list)
        assert all(isinstance(p, GridPoint) for p in points)
        assert len(points) >= 4
        assert bounds.name in points[0].name

    def test_get_grid_points_default(self) -> None:
        """Test that get_grid_points defaults to US coverage."""
        default_points = ScraperUtils.get_grid_points()
        us_points = ScraperUtils.get_us_grid_points()
        assert len(default_points) == len(us_points)
        assert all(
            d.latitude == u.latitude and d.longitude == u.longitude
            for d, u in zip(default_points, us_points, strict=False)
        )

    def test_get_grid_points_from_geojson(self) -> None:
        """Test generating grid points from GeoJSON file."""
        geojson_path = FIXTURES_DIR / "test_area.geojson"
        points = ScraperUtils.get_grid_points_from_geojson(geojson_path)

        # Should have reasonable number of points for this area
        assert len(points) >= 4

        # Points should be within bounds
        assert all(41.0 <= p.latitude <= 42.0 for p in points)
        assert all(-72.0 <= p.longitude <= -71.0 for p in points)

        # Check point naming includes area coordinates
        assert "(41.00, -72.00) to (42.00, -71.00)" in points[0].name

    def test_get_grid_points_from_geojson_invalid_file(self) -> None:
        """Test error handling for invalid GeoJSON."""
        with pytest.raises(ValueError, match="Failed to extract bounds"):
            ScraperUtils.get_grid_points_from_geojson(
                FIXTURES_DIR / "nonexistent.geojson"
            )

    def test_get_state_grid_points(self) -> None:
        """Test getting grid points for a state."""
        # Test with California
        points = ScraperUtils.get_state_grid_points("ca")
        assert isinstance(points, list)
        assert all(isinstance(p, GridPoint) for p in points)
        assert len(points) > 0

        # Points should be within California bounds (roughly)
        # CA latitude range
        assert all(32.0 <= p.latitude <= 42.1 for p in points)
        assert all(
            -125.0 <= p.longitude <= -114.0 for p in points
        )  # CA longitude range

    def test_get_state_grid_points_case_insensitive(self) -> None:
        """Test state code is case insensitive."""
        ca_points = ScraperUtils.get_state_grid_points("ca")
        CA_points = ScraperUtils.get_state_grid_points("CA")
        assert len(ca_points) == len(CA_points)
        assert all(
            p1.latitude == p2.latitude and p1.longitude == p2.longitude
            for p1, p2 in zip(ca_points, CA_points, strict=False)
        )

    def test_get_state_grid_points_invalid_state(self) -> None:
        """Test error handling for invalid state code."""
        with pytest.raises(ValueError, match="No GeoJSON file found for state code"):
            ScraperUtils.get_state_grid_points("xx")  # Invalid state code
