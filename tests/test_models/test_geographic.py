"""Tests for geographic models."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.models.geographic import BoundingBox, GridPoint, USBounds


class TestBoundingBox:
    """Tests for BoundingBox model."""

    def test_bounding_box_creation(self):
        """Test basic BoundingBox creation."""
        bbox = BoundingBox(north=40.0, south=35.0, east=-70.0, west=-75.0)
        assert bbox.north == 40.0
        assert bbox.south == 35.0
        assert bbox.east == -70.0
        assert bbox.west == -75.0

    def test_bounding_box_immutable(self):
        """Test that BoundingBox is immutable."""
        bbox = BoundingBox(north=40.0, south=35.0, east=-70.0, west=-75.0)
        with pytest.raises(ValueError, match="is frozen"):
            bbox.north = 45.0

    def test_bounding_box_name_property(self):
        """Test BoundingBox name property."""
        bbox = BoundingBox(north=40.5, south=35.25, east=-70.75, west=-75.5)
        expected_name = "Area (35.25, -75.50) to (40.50, -70.75)"
        assert bbox.name == expected_name

    @patch("app.models.geographic.gpd.read_file")
    def test_from_geojson_success(self, mock_read_file):
        """Test successful creation from GeoJSON file."""
        # Mock geopandas GeoDataFrame
        mock_gdf = MagicMock()
        mock_gdf.total_bounds = [-75.0, 35.0, -70.0, 40.0]  # [minx, miny, maxx, maxy]
        mock_read_file.return_value = mock_gdf

        test_file = Path("/test/file.geojson")
        bbox = BoundingBox.from_geojson(test_file)

        assert bbox.north == 40.0  # maxy
        assert bbox.south == 35.0  # miny
        assert bbox.east == -70.0  # maxx
        assert bbox.west == -75.0  # minx
        mock_read_file.assert_called_once_with(test_file)

    @patch("app.models.geographic.gpd.read_file")
    def test_from_geojson_read_error(self, mock_read_file):
        """Test GeoJSON read error handling."""
        mock_read_file.side_effect = Exception("File not found")

        test_file = Path("/nonexistent/file.geojson")
        with pytest.raises(ValueError, match="Failed to extract bounds from GeoJSON"):
            BoundingBox.from_geojson(test_file)

    @patch("app.models.geographic.gpd.read_file")
    def test_from_geojson_invalid_bounds(self, mock_read_file):
        """Test GeoJSON with invalid bounds."""
        # Mock geopandas GeoDataFrame with problematic bounds
        mock_gdf = MagicMock()
        mock_gdf.total_bounds = None  # This will cause an error when casting
        mock_read_file.return_value = mock_gdf

        test_file = Path("/test/invalid.geojson")
        with pytest.raises(ValueError, match="Failed to extract bounds from GeoJSON"):
            BoundingBox.from_geojson(test_file)

    def test_from_geojson_with_real_file(self):
        """Test from_geojson with a real temporary GeoJSON file."""
        # Create a simple GeoJSON file
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-72.5, 37.5]},
                    "properties": {"name": "test"},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False
        ) as f:
            json.dump(geojson_data, f)
            temp_path = Path(f.name)

        try:
            # This test will work if geopandas is available
            bbox = BoundingBox.from_geojson(temp_path)
            # Point should create a bounding box where all coordinates are the same
            assert bbox.north == bbox.south == 37.5
            assert bbox.east == bbox.west == -72.5
        except ImportError:
            # Skip if geopandas not available
            pytest.skip("geopandas not available")
        finally:
            temp_path.unlink()


class TestGridPoint:
    """Tests for GridPoint model."""

    def test_grid_point_creation(self):
        """Test basic GridPoint creation."""
        point = GridPoint(latitude=37.5, longitude=-72.5, name="test_point")
        assert point.latitude == 37.5
        assert point.longitude == -72.5
        assert point.name == "test_point"

    def test_grid_point_immutable(self):
        """Test that GridPoint is immutable."""
        point = GridPoint(latitude=37.5, longitude=-72.5, name="test_point")
        with pytest.raises(ValueError, match="is frozen"):
            point.latitude = 38.0

    def test_grid_point_validation(self):
        """Test GridPoint field validation."""
        # Test valid point
        point = GridPoint(latitude=0.0, longitude=0.0, name="origin")
        assert point.latitude == 0.0

        # Test with extreme but valid coordinates
        extreme_point = GridPoint(latitude=90.0, longitude=-180.0, name="extreme")
        assert extreme_point.latitude == 90.0
        assert extreme_point.longitude == -180.0


class TestUSBounds:
    """Tests for USBounds model."""

    def test_us_bounds_creation(self):
        """Test USBounds creation with default values."""
        us_bounds = USBounds()
        assert us_bounds.north == 49.0
        assert us_bounds.south == 25.0
        assert us_bounds.east == -67.0
        assert us_bounds.west == -125.0

    def test_us_bounds_name_property(self):
        """Test USBounds name property."""
        us_bounds = USBounds()
        assert us_bounds.name == "Continental United States"

    def test_us_bounds_immutable(self):
        """Test that USBounds is immutable."""
        us_bounds = USBounds()
        with pytest.raises(ValueError, match="is frozen"):
            us_bounds.north = 50.0

    def test_us_bounds_inheritance(self):
        """Test that USBounds inherits from BoundingBox."""
        us_bounds = USBounds()
        assert isinstance(us_bounds, BoundingBox)

        # Test that it has the inherited name functionality but overrides it
        assert us_bounds.name == "Continental United States"
        # The parent class name would be different
        parent_name = super(USBounds, us_bounds).name
        assert parent_name != us_bounds.name

    def test_us_bounds_custom_values(self):
        """Test USBounds with custom values."""
        # USBounds allows override of default values
        custom_bounds = USBounds(north=50.0, south=24.0, east=-66.0, west=-126.0)
        assert custom_bounds.north == 50.0
        assert custom_bounds.south == 24.0
        assert custom_bounds.east == -66.0
        assert custom_bounds.west == -126.0
        # Name should still be overridden
        assert custom_bounds.name == "Continental United States"
